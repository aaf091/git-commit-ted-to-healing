"""WoundScope API + web server.

Serves the eligibility results as JSON and hosts the static frontend (web/).
Run:  python api.py   ->  http://localhost:8000
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from woundscope import ai
from woundscope.db import DB_PATH

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

app = FastAPI(title="WoundScope API")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_patient(r: sqlite3.Row) -> dict:
    def _load(col, default):
        try:
            return json.loads(r[col]) if r[col] else default
        except Exception:
            return default
    sources = _load("sources", {})
    sources.pop("_scores", None)
    evidence = _load("evidence", {})
    wounds = _load("wounds", [])
    measurements_complete = all(
        r[k] is not None for k in ("length_cm", "width_cm", "depth_cm"))
    drainage = r["drainage"] if r["drainage"] not in (None, "None", "") else None
    return {
        "patient_id": r["patient_id"],
        "name": r["name"],
        "facility_id": r["facility_id"],
        "decision": r["decision"],
        "confidence": r["confidence"],
        "has_active_wound": bool(r["has_active_wound"]),
        "has_active_mcb": bool(r["has_active_mcb"]),
        "wound_type": r["wound_type"],
        "wound_stage": r["wound_stage"],
        "wound_location": r["wound_location"],
        "length_cm": r["length_cm"],
        "width_cm": r["width_cm"],
        "depth_cm": r["depth_cm"],
        "drainage": drainage,
        "measurements_complete": measurements_complete,
        "sources": sources,
        "evidence": evidence,
        "wound_count": r["wound_count"] or (1 if wounds else 0),
        "wounds": wounds,
        "reasoning": r["reasoning"],
    }


@app.get("/api/summary")
def summary() -> JSONResponse:
    conn = _conn()
    rows = conn.execute("SELECT decision, COUNT(*) n FROM results GROUP BY decision").fetchall()
    by = {r["decision"]: r["n"] for r in rows}
    total = conn.execute("SELECT COUNT(*) n FROM results").fetchone()["n"]
    facilities = [r["facility_id"] for r in conn.execute(
        "SELECT DISTINCT facility_id FROM results ORDER BY facility_id").fetchall()]
    conn.close()
    return JSONResponse({
        "total": total,
        "auto_accept": by.get("auto_accept", 0),
        "flag_for_review": by.get("flag_for_review", 0),
        "reject": by.get("reject", 0),
        "facilities": facilities,
    })


@app.get("/api/results")
def results() -> JSONResponse:
    conn = _conn()
    order = ("CASE decision WHEN 'auto_accept' THEN 0 "
             "WHEN 'flag_for_review' THEN 1 ELSE 2 END, confidence DESC")
    rows = conn.execute(f"SELECT * FROM results ORDER BY {order}").fetchall()
    conn.close()
    return JSONResponse([_row_to_patient(r) for r in rows])


@app.get("/api/patient/{patient_id}")
def patient(patient_id: str) -> JSONResponse:
    conn = _conn()
    r = conn.execute("SELECT * FROM results WHERE patient_id=?", (patient_id,)).fetchone()
    conn.close()
    if not r:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(_row_to_patient(r))


@app.post("/api/patient/{patient_id}/explain")
def explain(patient_id: str) -> JSONResponse:
    """AI-drafted, biller-facing narrative for the decision (deterministic fallback)."""
    conn = _conn()
    r = conn.execute("SELECT * FROM results WHERE patient_id=?", (patient_id,)).fetchone()
    conn.close()
    if not r:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(ai.explain_decision(_row_to_patient(r)))


# static frontend (mounted last so /api/* wins)
if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
