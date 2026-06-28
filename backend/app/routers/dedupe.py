"""POST /dedupe — run fuzzy matching, return duplicate clusters."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import matching
from app.store import store

router = APIRouter()


@router.post("/dedupe")
def run_dedupe() -> dict:
    if not store.has_data():
        raise HTTPException(404, "No dataset uploaded yet.")
    clusters = matching.find_duplicates(store.records())
    store.dupe_clusters = clusters
    return {
        "cluster_count": len(clusters),
        "duplicate_records": sum(len(c["members"]) for c in clusters),
        "clusters": clusters,
    }


@router.get("/dedupe")
def get_dedupe() -> dict:
    return {"cluster_count": len(store.dupe_clusters),
            "clusters": store.dupe_clusters}
