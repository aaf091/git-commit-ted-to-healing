"""
POST /flagged-events/run            — run the FULL pipeline (rules + dedupe)
GET  /flagged-events                — the unified issue queue, filterable
GET  /flagged-events/stats          — headline numbers for the dashboard cards
POST /flagged-events/{flag_id}/status   — resolve / dismiss / confirm a flag
POST /flagged-events/{flag_id}/explain  — AI-drafted explanation + next action

This is the endpoint the demo leans on: one prioritized, explainable queue with
a real review workflow (status) and an assistive AI layer on top.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.services import ai, flagging
from app.store import VALID_STATUSES, store

router = APIRouter()


def _ensure_flags() -> None:
    if not store.flags:
        store.flags, store.dupe_clusters = flagging.build_flags(store.records())
    store.apply_status(store.flags)


@router.post("/flagged-events/run")
def run_pipeline() -> dict:
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    records = store.records()
    flags, clusters = flagging.build_flags(records)
    store.flags = flags
    store.dupe_clusters = clusters
    store.apply_status(flags)
    stats = flagging.compute_stats(records, flags, clusters)
    return {"stats": stats, "flag_count": len(flags)}


@router.get("/flagged-events")
def list_flags(
    severity: str | None = Query(None),
    category: str | None = Query(None),
    type: str | None = Query(None),
    status: str | None = Query(None),
    min_confidence: float = Query(0.0, ge=0, le=100),
) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    _ensure_flags()

    flags = store.flags
    if severity:
        flags = [f for f in flags if f["severity"] == severity]
    if category:
        flags = [f for f in flags if f["category"] == category]
    if type:
        flags = [f for f in flags if f["type"] == type]
    if status:
        flags = [f for f in flags if f["status"] == status]
    if min_confidence:
        flags = [f for f in flags if f["confidence"] >= min_confidence]

    return {"total": len(flags), "flags": flags}


@router.get("/flagged-events/stats")
def stats() -> dict:
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    _ensure_flags()
    return flagging.compute_stats(store.records(), store.flags, store.dupe_clusters)


@router.get("/flagged-events/export.csv")
def export_csv(status: str | None = Query(None)) -> StreamingResponse:
    """Download the (optionally filtered) worklist as CSV — the closing-demo artifact."""
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    _ensure_flags()

    flags = store.flags
    if status:
        flags = [f for f in flags if f["status"] == status]

    by_id = {r["_row_id"]: r for r in store.records()}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "flag_id", "status", "severity", "category", "type", "confidence",
        "patient_id", "patient_name", "label", "explanation", "evidence",
    ])
    for f in flags:
        rec = by_id.get(f["row_id"], {})
        name = f"{rec.get('first_name','')} {rec.get('last_name','')}".strip()
        evidence = "; ".join(f"{e['field']}={e['value']}" for e in f.get("evidence", []))
        writer.writerow([
            f["flag_id"], f.get("status", "open"), f["severity"], f["category"],
            f["type"], f["confidence"], rec.get("patient_id", ""), name,
            f["label"], f["explanation"], evidence,
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=abi_worklist.csv"},
    )


@router.post("/flagged-events/{flag_id}/status")
def set_status(flag_id: str, body: dict = Body(...)) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    status = body.get("status")
    if status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}.")
    _ensure_flags()
    if not any(f["flag_id"] == flag_id for f in store.flags):
        raise HTTPException(404, f"No flag with id {flag_id}.")
    store.set_status(flag_id, status, body.get("note"))
    return {"flag_id": flag_id, "status": status, "note": body.get("note")}


@router.post("/flagged-events/{flag_id}/explain")
def explain(flag_id: str) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    _ensure_flags()
    flag = next((f for f in store.flags if f["flag_id"] == flag_id), None)
    if flag is None:
        raise HTTPException(404, f"No flag with id {flag_id}.")
    record = store.record_by_id(flag["row_id"]) or {}
    return ai.explain_flag(flag, record)
