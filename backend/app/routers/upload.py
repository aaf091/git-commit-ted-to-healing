"""
POST /upload       — ingest a CSV/JSON file, clean it, stash it in the store.
POST /load-sample  — load the bundled synthetic dataset server-side (one-click demo).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas import UploadResponse
from app.services import cleaning, flagging, ingestion
from app.store import store

router = APIRouter()

_SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data",
                            "synthetic_patients.csv")


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(400, "Empty file.")

    try:
        raw_df = ingestion.read_bytes(file.filename or "upload", raw_bytes)
    except Exception as e:  # noqa: BLE001 - surface parse errors to the user
        raise HTTPException(400, f"Could not parse file: {e}")

    if raw_df.empty:
        raise HTTPException(400, "File parsed but contained no rows.")

    column_map, unmapped = ingestion.map_columns(raw_df)
    canonical = ingestion.to_canonical(raw_df, column_map)
    clean_df = cleaning.clean(canonical)

    store.set_dataset(file.filename or "dataset", raw_df, clean_df, column_map)

    return _response(clean_df, column_map, unmapped)


@router.post("/load-sample", response_model=UploadResponse)
def load_sample() -> UploadResponse:
    """One-click demo: ingest the bundled synthetic CSV without a file picker."""
    if not os.path.exists(_SAMPLE_PATH):
        raise HTTPException(
            500, "Sample data not found. Run `python generate_data.py` first.")
    with open(_SAMPLE_PATH, "rb") as fh:
        raw_df = ingestion.read_bytes("synthetic_patients.csv", fh.read())

    column_map, unmapped = ingestion.map_columns(raw_df)
    canonical = ingestion.to_canonical(raw_df, column_map)
    clean_df = cleaning.clean(canonical)
    store.set_dataset("synthetic_patients.csv", raw_df, clean_df, column_map)

    # Run the pipeline immediately so the dashboard is populated on first paint.
    store.flags, store.dupe_clusters = flagging.build_flags(store.records())
    store.apply_status(store.flags)

    return _response(clean_df, column_map, unmapped)


def _response(clean_df, column_map, unmapped) -> UploadResponse:
    preview = clean_df.head(20).where(clean_df.notna(), None).to_dict("records")
    return UploadResponse(
        dataset_name=store.dataset_name,
        row_count=len(clean_df),
        columns=list(clean_df.columns),
        column_map=column_map,
        unmapped_columns=unmapped,
        preview=preview,
    )
