"""
Ingestion: turn an uploaded CSV/JSON byte blob into a DataFrame, then map its
messy columns onto the canonical SCHEMA from config.

Reusable for ANY problem — only config.SCHEMA changes at kickoff.
"""
from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd

from app.config import SCHEMA


def read_bytes(filename: str, raw: bytes) -> pd.DataFrame:
    """Parse CSV or JSON bytes into a DataFrame. Tolerant of common encodings."""
    name = (filename or "").lower()
    if name.endswith(".json") or _looks_like_json(raw):
        data = json.loads(raw.decode("utf-8-sig", errors="replace"))
        # Accept either a list of records or {"records": [...]} / {"data": [...]}.
        if isinstance(data, dict):
            for key in ("records", "data", "rows", "patients"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
            else:
                data = [data]
        return pd.DataFrame(data)

    # Default: CSV. utf-8-sig strips BOM; fall back to latin-1 for odd exports.
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc,
                               keep_default_na=True, skipinitialspace=True)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise ValueError("Could not parse file as CSV or JSON.")


def _looks_like_json(raw: bytes) -> bool:
    head = raw.lstrip()[:1]
    return head in (b"{", b"[")


def map_columns(df: pd.DataFrame) -> tuple[dict[str, str], list[str]]:
    """
    Build {canonical_field -> actual_source_column} using SCHEMA candidates.
    Matching is case/space/underscore-insensitive. Returns the map plus the
    list of source columns that didn't map to anything (shown in the UI so you
    can spot fields worth adding to SCHEMA at kickoff).
    """
    normalized = {_norm_col(c): c for c in df.columns}
    column_map: dict[str, str] = {}
    used_sources: set[str] = set()

    for canonical, candidates in SCHEMA.items():
        for cand in candidates:
            key = _norm_col(cand)
            if key in normalized:
                src = normalized[key]
                column_map[canonical] = src
                used_sources.add(src)
                break

    unmapped = [c for c in df.columns if c not in used_sources]
    return column_map, unmapped


def to_canonical(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    """
    Produce a DataFrame with canonical column names + a stable _row_id.
    Unmapped canonical fields are created as empty so downstream code can rely
    on every canonical column existing.
    """
    out = pd.DataFrame()
    out["_row_id"] = [f"r{i}" for i in range(len(df))]
    for canonical in SCHEMA:
        src = column_map.get(canonical)
        out[canonical] = df[src].values if src is not None else None
    return out


def _norm_col(name: Any) -> str:
    return "".join(str(name).lower().split()).replace("_", "").replace("-", "")
