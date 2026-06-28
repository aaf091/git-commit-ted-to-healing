"""
GET /patients          — list cleaned records (the data table)
GET /patients/{row_id} — one record + every flag attached to it (detail page)

Named /patients to match the plan, but it serves whatever the canonical record
is for the actual problem (claims, encounters, facilities...).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services import flagging
from app.store import store

router = APIRouter()


@router.get("/patients")
def list_records(limit: int = Query(500, ge=1, le=10000),
                 offset: int = Query(0, ge=0)) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    records = store.records()
    return {
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "records": records[offset:offset + limit],
    }


@router.get("/patients/{row_id}")
def get_record(row_id: str) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    record = store.record_by_id(row_id)
    if record is None:
        raise HTTPException(404, f"No record with id {row_id}.")

    # Attach flags. Use cached flags if a run has happened; else compute live.
    if not store.flags:
        store.flags, store.dupe_clusters = flagging.build_flags(store.records())
    store.apply_status(store.flags)
    mine = [f for f in store.flags if f["row_id"] == row_id]
    return {"record": record, "flags": mine}
