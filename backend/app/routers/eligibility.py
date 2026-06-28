"""
GET  /eligibility                 — routing queue, filterable (the work list).
GET  /eligibility/stats           — headline numbers for the dashboard cards.
GET  /eligibility/export.csv      — the biller output table as CSV.
POST /eligibility/{row_id}/status — mark a patient billed / dismissed / open.
POST /eligibility/{row_id}/explain — AI narrative for the routing decision.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.services import ai
from app.services import eligibility as elig
from app.store import VALID_STATUSES, store

router = APIRouter()


@router.get("/eligibility")
def list_eligibility(
    decision: str | None = Query(None),
    facility_id: int | None = Query(None),
    status: str | None = Query(None),
    min_confidence: float = Query(0.0, ge=0, le=100),
) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No data synced yet. POST /sync first.")
    rows = store.rows
    if decision:
        rows = [r for r in rows if r["decision"] == decision]
    if facility_id:
        rows = [r for r in rows if r["facility_id"] == facility_id]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if min_confidence:
        rows = [r for r in rows if r["confidence"] >= min_confidence]
    return {"total": len(rows), "rows": rows}


@router.get("/eligibility/stats")
def stats() -> dict:
    if not store.has_data():
        raise HTTPException(404, "No data synced yet.")
    return elig.compute_stats(store.rows)


@router.get("/eligibility/export.csv")
def export_csv(decision: str | None = Query(None)) -> StreamingResponse:
    if not store.has_data():
        raise HTTPException(404, "No data synced yet.")
    rows = store.rows
    if decision:
        rows = [r for r in rows if r["decision"] == decision]

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "patient_id", "name", "facility_id", "decision", "status", "confidence",
        "primary_payer", "part_b_active", "wound_type", "stage", "location",
        "length_cm", "width_cm", "depth_cm", "drainage_amount", "drainage_type",
        "measurements_complete", "drainage_documented", "reasoning",
    ])
    for r in rows:
        wd = r["wound"]
        w.writerow([
            r["patient_id"], r["name"], r["facility_id"], r["decision"], r["status"],
            r["confidence"], r["primary_payer_code"], r["part_b_active"],
            wd.get("wound_type"), wd.get("stage"), wd.get("location"),
            wd.get("length_cm"), wd.get("width_cm"), wd.get("depth_cm"),
            wd.get("drainage_amount"), wd.get("drainage_type"),
            r["measurements_complete"], r["drainage_documented"], r["reasoning"],
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=wound_billing_worklist.csv"},
    )


@router.post("/eligibility/{row_id}/status")
def set_status(row_id: str, body: dict = Body(...)) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No data synced yet.")
    status = body.get("status")
    if status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}.")
    if store.record_by_id(row_id) is None:
        raise HTTPException(404, f"No patient {row_id}.")
    store.set_status(row_id, status, body.get("note"))
    return {"row_id": row_id, "status": status, "note": body.get("note")}


@router.post("/eligibility/{row_id}/explain")
def explain(row_id: str) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No data synced yet.")
    row = store.record_by_id(row_id)
    if row is None:
        raise HTTPException(404, f"No patient {row_id}.")
    return ai.explain_decision(row)
