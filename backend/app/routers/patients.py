"""
GET /patients          — the eligibility output table (one row per patient).
GET /patients/{row_id} — full biller detail: decision + reasoning + extracted
                         wound + the raw source data (coverage, diagnoses, notes,
                         assessments) that backs every field.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.store import store

router = APIRouter()


@router.get("/patients")
def list_patients(limit: int = Query(1000, ge=1, le=5000),
                  offset: int = Query(0, ge=0)) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No data synced yet. POST /sync first.")
    rows = store.rows
    return {"total": len(rows), "rows": rows[offset:offset + limit]}


@router.get("/patients/{row_id}")
def get_patient(row_id: str) -> dict:
    if not store.has_data():
        raise HTTPException(404, "No data synced yet.")
    row = store.record_by_id(row_id)
    if row is None:
        raise HTTPException(404, f"No patient {row_id}.")
    bundle = store.bundle_by_id(row_id) or {}
    return {
        "decision": row,
        "diagnoses": bundle.get("diagnoses", []),
        "coverage": bundle.get("coverage", []),
        "notes": bundle.get("notes", []),
        "assessments": bundle.get("assessments", []),
    }
