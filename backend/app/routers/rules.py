"""
GET  /rules          — list the configured rules (for the UI rules panel)
POST /rules/evaluate — run only the rules engine, return rule flags
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import RULES
from app.services import rules_engine
from app.store import store

router = APIRouter()


@router.get("/rules")
def list_rules() -> dict:
    return {"rules": RULES}


@router.post("/rules/evaluate")
def evaluate_rules() -> dict:
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    flags = rules_engine.evaluate(store.records())
    return {"flag_count": len(flags), "flags": flags}
