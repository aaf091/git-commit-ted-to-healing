"""
ABI Wound-Care Eligibility Radar — FastAPI entrypoint.

Pipeline: PointClickCare API -> extract wounds -> route for Part B billing ->
evidence-backed biller dashboard.

Run:  uvicorn main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DASHBOARD, FACILITIES, ROUTING
from app.routers import eligibility, patients, sync

app = FastAPI(title=DASHBOARD["app_name"], version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.include_router(sync.router, tags=["sync"])
app.include_router(patients.router, tags=["patients"])
app.include_router(eligibility.router, tags=["eligibility"])


@app.get("/")
def health() -> dict:
    return {"status": "ok", "app": DASHBOARD["app_name"]}


@app.get("/meta")
def meta() -> dict:
    """Frontend reads this to label the UI and render facility/decision options."""
    return {
        "dashboard": DASHBOARD,
        "facilities": [{"id": f, "name": n} for f, n in FACILITIES.items()],
        "decisions": [{"key": k, "label": v["label"], "desc": v["desc"]}
                      for k, v in ROUTING.items()],
    }
