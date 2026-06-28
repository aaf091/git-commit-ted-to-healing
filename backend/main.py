"""
ABI Ops Radar — FastAPI entrypoint.

Run:  uvicorn main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DASHBOARD, RULES, SCHEMA
from app.routers import dedupe, flagged, patients, rules, upload

app = FastAPI(title=DASHBOARD["app_name"], version="0.1.0")

# Wide-open CORS — it's a local hackathon demo, not production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, tags=["upload"])
app.include_router(patients.router, tags=["records"])
app.include_router(dedupe.router, tags=["dedupe"])
app.include_router(rules.router, tags=["rules"])
app.include_router(flagged.router, tags=["flagged"])


@app.get("/")
def health() -> dict:
    return {"status": "ok", "app": DASHBOARD["app_name"]}


@app.get("/meta")
def meta() -> dict:
    """Frontend reads this to label the UI and render the rule list."""
    return {
        "dashboard": DASHBOARD,
        "schema_fields": list(SCHEMA.keys()),
        "rules": [
            {k: r[k] for k in ("id", "label", "category", "severity", "explain")}
            for r in RULES
        ],
    }
