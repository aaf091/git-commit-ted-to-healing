# Stage 1 — Data Ingestion Pipeline

Fetches patients, diagnoses, coverage, progress notes, and assessments from
the PCC mock API (`https://hackathon.prod.pulsefoundry.ai`) across all 3
facilities, handles the documented 30%-random-429 rate limiting, and lands
everything in a queryable SQLite database.

## Run it

```bash
pip install -r requirements.txt
python3 ingest.py
```

This writes `pcc_data.db` (SQLite) and `sync_state.json` (incremental sync
bookmarks) into the current directory. Override defaults via env vars:

```bash
PCC_API_BASE_URL=https://hackathon.prod.pulsefoundry.ai \
PCC_DB_PATH=pcc_data.db \
python3 ingest.py
```

For incremental runs (only fetch patients modified since the last run, per
the API's `since` parameter), call `run_ingestion(incremental=True)` from
`ingest.py` instead of the default `__main__` block, or adapt as needed.

## Files

| File | Role |
|---|---|
| `config.py` | All tunables: base URL, facility IDs, AIMD bounds, retry budget params |
| `scheduler.py` | The core engine: AIMD concurrency gate, analytically-provisioned retry budget, breadth-first priority queue, race-free task accounting |
| `api_client.py` | Thin HTTP layer — one call per function, translates HTTP responses into scheduler signals (success / `RateLimited` / `PermanentError`) |
| `storage.py` | SQLite schema + idempotent upserts, called as results stream in |
| `ingest.py` | Orchestrator — wires the patient → {diagnoses, coverage, notes, assessments} dependency DAG into the scheduler |
| `mock_server.py` | Local FastAPI server replicating the documented API contract (30% random 429, same schemas) — **dev/test only**, used to validate the scheduler without needing the real host |

## Design notes

**Why not a simple retry-with-backoff loop.** The 30% failure rate is
per-request, independent, and memoryless — backing off longer doesn't
improve your odds on the next attempt, it only burns wall-clock time. The
actual lever that matters is how many requests you admit at once. The
scheduler runs an AIMD (additive-increase / multiplicative-decrease) loop —
the same control scheme TCP uses for congestion control — so concurrency
self-tunes to whatever throughput is actually sustainable, rather than a
hardcoded worker count.

**Why breadth-first.** Patients → diagnoses/coverage/notes/assessments forms
a dependency DAG (notes/assessments need the internal integer `id`, only
known after the patient list call). Tasks are prioritized by DAG depth, not
by patient, so an interrupted run has partial coverage spread across the
whole population instead of 100% on the first few patients and nothing on
the rest — much better for a partial/demo run.

**Why a shared, analytically-sized retry budget.** Expected retries per task
at failure rate `p` is `p/(1-p)` ≈ 0.43 at `p=0.3`. The budget is provisioned
from that formula (with a safety multiplier) once at the start and shared
globally across all tasks, rather than capping retries per-call — so one
unlucky task can't loop forever in isolation, and the budget is sized from
the actual documented failure rate instead of a guessed constant.

**Why streaming upserts, not collect-then-write.** Every successful task
result is upserted into SQLite immediately inside the scheduler's
`on_result` callback. Combined with `ON CONFLICT` upserts keyed on natural
identity (patient_id, record id), this makes the whole run resumable: kill
it at any point and whatever already landed is durable, and rerunning won't
duplicate rows.

## What was tested (see conversation for full detail)

- 5×40-task and 1×50-task synthetic runs against `mock_server.py`, all
  passing with 100% of tasks eventually landing despite ~30-50% of calls
  hitting simulated 429s.
- Full DAG run (3 facilities × 40 mock patients × 4 child calls = 483 leaf
  calls): 0 permanent failures, all data landed with correct referential
  integrity (0 orphaned notes/coverage rows).
- Idempotency: two full runs against the same DB produced identical row
  counts (no duplication) once a mock-server hash-seed artifact was fixed.
- Two real concurrency bugs were found and fixed during testing:
  1. `asyncio.Semaphore` has no non-blocking shrink primitive — the AIMD
     gate now uses a `Condition`-based design that supports dynamic resize.
  2. A race between `queue.task_done()` and the retry requeue path could
     let `queue.join()` return before all retries had actually completed —
     fixed with an explicit `_pending_retries` counter.

## Running the mock server yourself (optional, for offline testing)

```bash
pip install fastapi uvicorn
python3 -m uvicorn mock_server:app --port 8000 &
PCC_API_BASE_URL=http://127.0.0.1:8000 python3 ingest.py
```
