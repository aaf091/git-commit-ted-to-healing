"""
Stage 1 orchestrator. Wires the dependency DAG:

    patients (priority 0, known upfront: 3 facilities)
        |
        ├──> diagnoses  (priority 1, keyed on patient_id string)
        └──> coverage   (priority 1, keyed on patient_id string)
        |
        └──> [after patient lands, internal id is known]
              ├──> notes        (priority 2, keyed on internal id)
              └──> assessments  (priority 2, keyed on internal id)

into the AIMD scheduler, with breadth-first priorities so a cut-short run
has partial coverage spread across the whole population rather than 100%
on the first few patients. Results stream straight into SQLite as they
land (see on_result), so the run is resumable at any point.
"""
import asyncio
import time

import httpx

import config
import storage
from api_client import fetch
from scheduler import Scheduler


def estimate_task_count() -> int:
    # 3 patient-list calls, then for an assumed ~100 patients/facility:
    # diagnoses + coverage + notes + assessments = 4 calls/patient.
    # This is just the seed for the analytic retry-budget provisioning;
    # top_up_budget() corrects it once real patient counts are known.
    return len(config.FACILITY_IDS) + len(config.FACILITY_IDS) * 100 * 4


def on_result(task, result, sched: Scheduler):
    with storage.connect() as conn:
        if task.kind == "patients":
            for p in result:
                storage.upsert_patient(conn, p)
            # Fan-out: now that patients are known, enqueue their children.
            # This is also where breadth-first matters -- ALL patients
            # across ALL facilities get their diagnoses/coverage enqueued
            # at priority 1 before anything proceeds to priority 2.
            sched.top_up_budget(len(result) * 4)
            for p in result:
                sched.enqueue(1, "diagnoses", {"patient_id": p["patient_id"]})
                sched.enqueue(1, "coverage", {"patient_id": p["patient_id"]})
                sched.enqueue(2, "notes", {"patient_id": p["id"]})
                sched.enqueue(2, "assessments", {"patient_id": p["id"]})

        elif task.kind == "diagnoses":
            for d in result:
                storage.upsert_diagnosis(conn, d)

        elif task.kind == "coverage":
            for c in result:
                storage.upsert_coverage(conn, c)

        elif task.kind == "notes":
            for n in result:
                storage.upsert_note(conn, n)

        elif task.kind == "assessments":
            for a in result:
                storage.upsert_assessment(conn, a)


async def run_ingestion(incremental: bool = False):
    storage.init_db()
    sync_state = storage.get_sync_state() if incremental else {}

    sched = Scheduler(handler=fetch, on_result=on_result, expected_task_count=estimate_task_count())

    # Seed level 0: one call per facility. `since` enables incremental
    # fetch on reruns -- only patients/notes/assessments support it per
    # the API doc, diagnoses/coverage don't, so those stay full-refresh.
    for fid in config.FACILITY_IDS:
        params = {"facility_id": fid}
        since = sync_state.get(f"patients:{fid}")
        if since:
            params["since"] = since
        sched.enqueue(0, "patients", params)

    run_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    limits = httpx.Limits(max_connections=config.MAX_CONCURRENCY, max_keepalive_connections=config.MAX_CONCURRENCY)
    async with httpx.AsyncClient(limits=limits) as client:
        await sched.run(client, num_workers=config.MAX_CONCURRENCY)

    if incremental:
        for fid in config.FACILITY_IDS:
            sync_state[f"patients:{fid}"] = run_started_at
        storage.set_sync_state(sync_state)

    report = sched.stats.report()
    report["final_concurrency_limit"] = sched.gate.current_limit
    report["retry_budget_used"] = sched.budget.total - sched.budget.remaining
    report["retry_budget_total"] = sched.budget.total
    return report


if __name__ == "__main__":
    result = asyncio.run(run_ingestion(incremental=False))
    print("\n=== Ingestion run report ===")
    for k, v in result.items():
        print(f"  {k}: {v}")