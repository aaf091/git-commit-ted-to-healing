"""
Read raw PCC records from the Stage-1 SQLite database (`pcc_data.db`, built by
the ingestion pipeline) and assemble them into the same per-patient bundles the
eligibility engine consumes from the live API.

This is the team seam: Stage 1 ingests API -> SQLite (queryable, durable,
resumable); Stage 2 (this app) reads the DB -> extracts -> routes -> dashboards.
Reading from the DB decouples analysis from ingestion and removes any live-API
dependency once data has been synced.

Join note: the DB mirrors the API's id quirk — diagnoses/coverage key on the
TEXT patient_id ("FA-001"), while progress_notes/assessments key on the INTEGER
patient id. We bridge both via the patients table.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from app.config import DB_PATH


def db_exists(path: str | None = None) -> bool:
    return os.path.exists(path or DB_PATH)


def table_counts(path: str | None = None) -> dict[str, int]:
    with _connect(path) as conn:
        out = {}
        for t in ("patients", "diagnoses", "coverage", "progress_notes", "assessments"):
            try:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                out[t] = 0
        return out


def load_bundles(path: str | None = None, facility_ids: list[int] | None = None,
                 limit: int | None = None) -> list[dict[str, Any]]:
    """Return [{patient, diagnoses, coverage, notes, assessments}] from the DB."""
    with _connect(path) as conn:
        where, params = "", []
        if facility_ids:
            where = " WHERE facility_id IN (%s)" % ",".join("?" * len(facility_ids))
            params = list(facility_ids)
        sql = "SELECT * FROM patients" + where + " ORDER BY id"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        patients = [dict(r) for r in conn.execute(sql, params)]

        # Group child tables once (avoid N+1).
        diagnoses = _group(conn, "diagnoses", "patient_id")     # keyed by TEXT patient_id
        coverage = _group(conn, "coverage", "patient_id")       # keyed by TEXT patient_id
        notes = _group(conn, "progress_notes", "patient_id")    # keyed by INT id
        assessments = _group(conn, "assessments", "patient_id")  # keyed by INT id

        bundles = []
        for p in patients:
            pid_str = str(p.get("patient_id"))
            pid_int = p.get("id")
            bundles.append({
                "patient": p,
                "diagnoses": diagnoses.get(pid_str, []),
                "coverage": coverage.get(pid_str, []),
                "notes": notes.get(pid_int, []),
                "assessments": assessments.get(pid_int, []),
            })
        return bundles


def _group(conn: sqlite3.Connection, table: str, key: str) -> dict[Any, list[dict]]:
    out: dict[Any, list[dict]] = {}
    for r in conn.execute(f"SELECT * FROM {table}"):
        row = dict(r)
        out.setdefault(row.get(key), []).append(row)
    return out


def _connect(path: str | None) -> sqlite3.Connection:
    p = path or DB_PATH
    if not os.path.exists(p):
        raise FileNotFoundError(
            f"Database not found at {p}. Run the Stage-1 ingester to build it, "
            f"or set PCC_DB_PATH.")
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn
