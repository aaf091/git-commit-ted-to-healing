"""
POST /sync  — pull from the PointClickCare API, extract wounds, route, store.
GET  /sync/status — what's currently loaded + API call stats.

This is the pipeline entrypoint. It fetches a facility (optionally capped for a
fast demo), runs extraction + eligibility, and caches the result. `since` enables
incremental sync. The API rate-limits ~30% of calls; the client retries with
backoff so a sync never loses data — the stats show how many 429s we absorbed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException

from app.config import FACILITIES
from app.services import db_source, eligibility
from app.services.pcc_client import PCCClient
from app.store import store

router = APIRouter()


@router.post("/sync")
def sync(body: dict = Body(default={})) -> dict:
    facility_ids = body.get("facility_ids") or [body.get("facility_id", 101)]
    facility_ids = [int(f) for f in facility_ids if int(f) in FACILITIES]
    if not facility_ids:
        raise HTTPException(400, f"facility_id must be one of {list(FACILITIES)}.")
    limit = body.get("limit")            # cap patients per facility (None = all)
    since = body.get("since")            # ISO 8601 for incremental sync

    client = PCCClient()
    health = client.health()
    if not isinstance(health, dict) or health.get("status") != "healthy":
        raise HTTPException(502, "PointClickCare API is not reachable.")

    bundles: list[dict] = []
    for fid in facility_ids:
        bundles.extend(client.fetch_facility(fid, limit=limit, since=since))

    rows = eligibility.assess_all(bundles)
    ts = datetime.now(timezone.utc).isoformat()
    store.set_results(bundles, rows, facility_ids, client.stats, ts)

    return {
        "synced_facilities": [{"id": f, "name": FACILITIES[f]} for f in facility_ids],
        "patient_count": len(rows),
        "api_stats": client.stats,
        "stats": eligibility.compute_stats(rows),
        "last_sync": ts,
    }


@router.post("/load-db")
def load_db(body: dict = Body(default={})) -> dict:
    """
    Run the pipeline off the Stage-1 SQLite database instead of the live API.
    Faster, no rate-limits, and the durable/queryable source the deliverable asks
    for. Optionally filter by facility / cap patients.
    """
    if not db_source.db_exists():
        raise HTTPException(404, "No pcc_data.db found. Run the Stage-1 ingester "
                                 "or set PCC_DB_PATH.")
    facility_ids = body.get("facility_ids")
    if facility_ids:
        facility_ids = [int(f) for f in facility_ids if int(f) in FACILITIES]
    limit = body.get("limit")

    bundles = db_source.load_bundles(facility_ids=facility_ids, limit=limit)
    if not bundles:
        raise HTTPException(404, "Database has no patients for that filter.")

    rows = eligibility.assess_all(bundles)
    ts = datetime.now(timezone.utc).isoformat()
    facilities = sorted({b["patient"].get("facility_id") for b in bundles})
    counts = db_source.table_counts()
    store.set_results(bundles, rows, facilities, {"source": "database", **counts}, ts)

    return {
        "source": "database",
        "db_counts": counts,
        "synced_facilities": [{"id": f, "name": FACILITIES.get(f)} for f in facilities],
        "patient_count": len(rows),
        "api_stats": {"source": "database", **counts},
        "stats": eligibility.compute_stats(rows),
        "last_sync": ts,
    }


@router.get("/sync/status")
def sync_status() -> dict:
    db_available = db_source.db_exists()
    return {
        "has_data": store.has_data(),
        "patient_count": len(store.rows),
        "facilities_synced": [{"id": f, "name": FACILITIES.get(f)} for f in store.facilities_synced],
        "api_stats": store.api_stats,
        "last_sync": store.last_sync,
        "db_available": db_available,
        "db_counts": db_source.table_counts() if db_available else {},
    }
