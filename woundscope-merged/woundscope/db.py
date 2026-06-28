"""SQLite storage layer for WoundScope.

One file DB (woundscope.db). Raw API payloads are stored verbatim in JSON
columns so extraction can be re-run without re-hitting the (rate-limited) API.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "woundscope.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id              INTEGER PRIMARY KEY,      -- internal int id (notes/assessments)
    patient_id      TEXT UNIQUE,              -- external string id (FA-001)
    facility_id     INTEGER,
    first_name      TEXT,
    last_name       TEXT,
    birth_date      TEXT,
    gender          TEXT,
    primary_payer_code TEXT,
    is_new_admission   INTEGER,
    last_modified_at   TEXT,
    raw             TEXT
);

CREATE TABLE IF NOT EXISTS diagnoses (
    pk              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT,                     -- external id
    icd10_code      TEXT,
    icd10_description TEXT,
    clinical_status TEXT,
    onset_date      TEXT,
    raw             TEXT
);

CREATE TABLE IF NOT EXISTS coverage (
    pk              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT,                     -- external id
    payer_name      TEXT,
    payer_code      TEXT,
    payer_type      TEXT,
    effective_from  TEXT,
    effective_to    TEXT,
    raw             TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    pk              INTEGER PRIMARY KEY AUTOINCREMENT,
    int_id          INTEGER,                  -- internal int id
    note_type       TEXT,
    effective_date  TEXT,
    note_text       TEXT,
    is_current      INTEGER,
    raw             TEXT
);

CREATE TABLE IF NOT EXISTS assessments (
    pk              INTEGER PRIMARY KEY AUTOINCREMENT,
    int_id          INTEGER,                  -- internal int id
    assessment_type TEXT,
    status          TEXT,
    assessment_date TEXT,
    raw_json        TEXT,
    is_current      INTEGER,
    raw             TEXT
);

CREATE TABLE IF NOT EXISTS results (
    patient_id      TEXT PRIMARY KEY,
    int_id          INTEGER,
    name            TEXT,
    facility_id     INTEGER,
    decision        TEXT,
    confidence      REAL,
    has_active_wound    INTEGER,
    has_active_mcb      INTEGER,
    wound_type      TEXT,
    wound_stage     TEXT,
    wound_location  TEXT,
    length_cm       REAL,
    width_cm        REAL,
    depth_cm        REAL,
    drainage        TEXT,
    sources         TEXT,    -- provenance JSON
    evidence        TEXT,    -- per-field source snippet JSON
    wound_count     INTEGER,
    wounds          TEXT,    -- all wounds JSON (multi-wound)
    reasoning       TEXT,
    raw             TEXT
);
"""


def reset_results() -> None:
    """Drop + recreate just the results table (keeps ingested raw data)."""
    conn = connect()
    conn.execute("DROP TABLE IF EXISTS results")
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
