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
from app.services import eligibility
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


@router.get("/sync/status")
def sync_status() -> dict:
    return {
        "has_data": store.has_data(),
        "patient_count": len(store.rows),
        "facilities_synced": [{"id": f, "name": FACILITIES.get(f)} for f in store.facilities_synced],
        "api_stats": store.api_stats,
        "last_sync": store.last_sync,
    }
