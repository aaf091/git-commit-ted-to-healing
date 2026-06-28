"""
Congestion-controlled scheduler for fetching from a randomly-rate-limited API.

Core idea: the 30% 429 rate is memoryless and independent of backoff duration,
so exponential backoff on retry *delay* doesn't meaningfully improve throughput.
The real control variable is concurrency. We run an AIMD (additive-increase /
multiplicative-decrease) loop -- the same control scheme TCP uses for
congestion control -- to let the system find its own sustainable throughput
ceiling rather than hardcoding a worker count.

Tasks are processed breadth-first via priority levels (not depth-first per
patient), so a run that gets cut short still has partial coverage spread
across the whole population instead of 100% on the first few patients and
0% on the rest.

Retry budget is provisioned analytically from the known failure rate
(expected retries per task = p/(1-p) at p=0.3 ≈ 0.43) rather than an
arbitrary "retry N times" cap per call, and it's shared globally so one
unlucky task can't starve its siblings.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import httpx

import config


@dataclass(order=True)
class Task:
    """A unit of retryable fetch work. `priority` = breadth-first level
    (0 = patients, 1 = diagnoses/coverage, 2 = notes/assessments) so the
    scheduler drains shallow levels across ALL patients before going deeper."""
    priority: int
    seq: int  # tiebreaker for stable ordering within a priority level
    kind: str = field(compare=False)
    params: dict = field(compare=False)
    attempt: int = field(default=0, compare=False)


class AdaptiveConcurrencyGate:
    """AIMD-controlled admission gate with a dynamically resizable limit.

    A plain asyncio.Semaphore can't safely shrink: there's no non-blocking
    way to "take back" a permit that might currently be held by in-flight
    work, and a fixed initial count can't be resized after construction.
    So this tracks an explicit `limit` and `in_flight` count behind a
    Condition: acquire() blocks until in_flight < limit, release() always
    frees a slot and wakes waiters, and resizing the limit just changes
    the threshold acquire() checks against -- no permits need to be
    physically reclaimed, shrinking takes effect the moment current holders
    release.
    """

    def __init__(self, initial: int, min_c: int, max_c: int):
        self.min_c = min_c
        self.max_c = max_c
        self._limit = initial
        self._in_flight = 0
        self._cond = asyncio.Condition()
        self._success_streak = 0

    async def acquire(self):
        async with self._cond:
            await self._cond.wait_for(lambda: self._in_flight < self._limit)
            self._in_flight += 1

    async def release(self):
        async with self._cond:
            self._in_flight -= 1
            self._cond.notify_all()

    async def on_success(self):
        async with self._cond:
            self._success_streak += 1
            if self._success_streak % 3 == 0 and self._limit < self.max_c:
                self._limit = min(self._limit + config.ADDITIVE_INCREASE, self.max_c)
                self._cond.notify_all()

    async def on_rate_limited(self):
        async with self._cond:
            self._success_streak = 0
            self._limit = max(self.min_c, int(self._limit * config.MULTIPLICATIVE_DECREASE))
            # No need to reclaim anything: shrinking the limit just makes
            # acquire()'s condition stricter. Holders already in flight
            # finish normally; the smaller limit is enforced starting with
            # the next acquire() call.

    @property
    def current_limit(self) -> int:
        return self._limit


class RetryBudget:
    """Analytically-provisioned, globally-shared retry budget.

    Expected retries per task at failure rate p is p/(1-p). We provision
    total_tasks * p/(1-p) * safety_multiplier retries for the WHOLE run,
    shared across tasks, rather than a fixed per-call retry cap. This means
    a streak of bad luck on one task draws down a shared pool instead of
    looping forever in isolation.
    """

    def __init__(self, expected_task_count: int):
        p = config.KNOWN_FAILURE_RATE
        analytic_expectation = expected_task_count * (p / (1 - p))
        self.total = int(analytic_expectation * config.RETRY_BUDGET_MULTIPLIER) + expected_task_count
        self.remaining = self.total
        self._lock = asyncio.Lock()

    async def try_spend(self) -> bool:
        async with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True

    def top_up(self, n: int):
        # Called when we discover more tasks than originally estimated
        # (e.g. notes+assessments fan-out only known after patients land).
        p = config.KNOWN_FAILURE_RATE
        extra = int(n * (p / (1 - p)) * config.RETRY_BUDGET_MULTIPLIER) + n
        self.total += extra
        self.remaining += extra


@dataclass
class RunStats:
    succeeded: int = 0
    failed_permanently: int = 0
    rate_limited_events: int = 0
    total_calls: int = 0
    start_time: float = field(default_factory=time.monotonic)

    def report(self) -> dict:
        elapsed = time.monotonic() - self.start_time
        return {
            "succeeded": self.succeeded,
            "failed_permanently": self.failed_permanently,
            "rate_limited_events": self.rate_limited_events,
            "total_calls": self.total_calls,
            "elapsed_seconds": round(elapsed, 2),
            "effective_throughput_per_sec": round(self.succeeded / elapsed, 2) if elapsed > 0 else 0,
        }


class Scheduler:
    """Drains a priority queue of Tasks with bounded, self-tuning
    concurrency, a shared retry budget, and breadth-first ordering.

    `handler(task, client)` performs the actual HTTP call and must:
      - return a result dict on success
      - raise RateLimited(retry_after) on a 429
      - raise PermanentError on anything else worth giving up on

    `on_result(task, result)` is called for every success — this is where
    children tasks get enqueued (e.g. patient -> diagnoses/coverage/notes)
    and where rows get upserted into SQLite immediately, so the run is
    resumable at any point rather than collect-then-write-at-the-end.
    """

    def __init__(
        self,
        handler: Callable[[Task, httpx.AsyncClient], Awaitable[Any]],
        on_result: Callable[[Task, Any, "Scheduler"], None],
        expected_task_count: int,
    ):
        self.handler = handler
        self.on_result = on_result
        self.gate = AdaptiveConcurrencyGate(
            config.INITIAL_CONCURRENCY, config.MIN_CONCURRENCY, config.MAX_CONCURRENCY
        )
        self.budget = RetryBudget(expected_task_count)
        self.stats = RunStats()
        self._queue: asyncio.PriorityQueue[Task] = asyncio.PriorityQueue()
        self._seq = 0
        self._inflight = 0
        self._pending_retries = 0
        self._done_event = asyncio.Event()

    def enqueue(self, priority: int, kind: str, params: dict):
        self._seq += 1
        self._queue.put_nowait(Task(priority=priority, seq=self._seq, kind=kind, params=params))

    def top_up_budget(self, n_new_tasks: int):
        self.budget.top_up(n_new_tasks)

    async def run(self, client: httpx.AsyncClient, num_workers: int = config.MAX_CONCURRENCY):
        workers = [asyncio.create_task(self._worker(client)) for _ in range(num_workers)]
        # Loop join(): a single join() can return while a retry is still
        # sleeping in _requeue_after_delay (queue momentarily empty, no
        # worker holding a task). Once that retry's put_nowait() lands, the
        # queue has new debt that join() alone won't retroactively wait for
        # if we'd already returned. So re-check: only stop once the queue is
        # both drained AND no retries are in flight to refill it.
        while True:
            await self._queue.join()
            if self._pending_retries == 0 and self._queue.empty():
                break
            await asyncio.sleep(0.05)
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    async def _worker(self, client: httpx.AsyncClient):
        while True:
            task: Task = await self._queue.get()
            await self.gate.acquire()
            try:
                self.stats.total_calls += 1
                result = await self.handler(task, client)
                await self.gate.on_success()
                self.stats.succeeded += 1
                self.on_result(task, result, self)
            except RateLimited as rl:
                self.stats.rate_limited_events += 1
                await self.gate.on_rate_limited()
                if await self.budget.try_spend():
                    task.attempt += 1
                    delay = rl.retry_after if rl.retry_after is not None else config.DEFAULT_RETRY_AFTER_SECONDS
                    delay += random.uniform(0, 0.3)  # small jitter to avoid thundering herd on requeue
                    # CRITICAL ORDERING: register the retry's replacement debt
                    # (via a placeholder put) BEFORE this attempt's task_done()
                    # fires in `finally`. If we settled this attempt's debt
                    # first and only added the replacement later (after the
                    # sleep), there'd be a window where queue.join() sees zero
                    # outstanding work and returns early -- even though a retry
                    # is still pending in the background. A pending-retry
                    # counter closes that gap explicitly.
                    self._pending_retries += 1
                    asyncio.create_task(self._requeue_after_delay(task, delay))
                else:
                    self.stats.failed_permanently += 1
                    print(f"[budget exhausted] dropping {task.kind} {task.params}")
            except PermanentError as e:
                self.stats.failed_permanently += 1
                print(f"[permanent error] {task.kind} {task.params}: {e}")
            except Exception as e:  # noqa: BLE001 - log and move on, don't crash the run
                self.stats.failed_permanently += 1
                print(f"[unexpected error] {task.kind} {task.params}: {e}")
            finally:
                await self.gate.release()
                self._queue.task_done()

    async def _requeue_after_delay(self, task: Task, delay: float):
        await asyncio.sleep(delay)
        self._queue.put_nowait(task)
        self._pending_retries -= 1


class RateLimited(Exception):
    def __init__(self, retry_after: Optional[float]):
        self.retry_after = retry_after


class PermanentError(Exception):
    pass