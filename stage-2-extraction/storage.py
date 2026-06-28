"""
SQLite storage layer. Every write is an upsert keyed on natural identity,
called immediately as results stream in from the scheduler -- not batched
at the end. This is what makes the run resumable: kill it at any point and
whatever landed is already durable and queryable.
"""
import json
import sqlite3
from contextlib import contextmanager
from typing import Optional

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY,
    facility_id INTEGER,
    patient_id TEXT UNIQUE,
    first_name TEXT,
    last_name TEXT,
    birth_date TEXT,
    gender TEXT,
    primary_payer_code TEXT,
    last_modified_at TEXT,
    is_new_admission INTEGER,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS diagnoses (
    id INTEGER PRIMARY KEY,
    patient_id TEXT,
    icd10_code TEXT,
    icd10_description TEXT,
    clinical_status TEXT,
    onset_date TEXT,
    last_modified_at TEXT,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS coverage (
    id INTEGER PRIMARY KEY,
    patient_id TEXT,
    payer_name TEXT,
    payer_code TEXT,
    payer_type TEXT,
    effective_from TEXT,
    effective_to TEXT,
    last_modified_at TEXT,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS progress_notes (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER,
    org_id TEXT,
    pcc_note_id INTEGER,
    note_type TEXT,
    effective_date TEXT,
    note_text TEXT,
    created_by TEXT,
    note_label TEXT,
    sync_version INTEGER,
    is_current INTEGER,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER,
    org_id TEXT,
    pcc_assessment_id INTEGER,
    assessment_type TEXT,
    status TEXT,
    assessment_date TEXT,
    completion_date TEXT,
    template_id INTEGER,
    assessment_type_description TEXT,
    raw_json TEXT,
    sync_version INTEGER,
    is_current INTEGER,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_diag_patient ON diagnoses(patient_id);
CREATE INDEX IF NOT EXISTS idx_cov_patient ON coverage(patient_id);
CREATE INDEX IF NOT EXISTS idx_notes_patient ON progress_notes(patient_id);
CREATE INDEX IF NOT EXISTS idx_assess_patient ON assessments(patient_id);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")  # allows concurrent reads while writes stream in
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


def upsert_patient(conn: sqlite3.Connection, p: dict):
    conn.execute(
        """INSERT INTO patients (id, facility_id, patient_id, first_name, last_name,
               birth_date, gender, primary_payer_code, last_modified_at, is_new_admission)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(patient_id) DO UPDATE SET
               facility_id=excluded.facility_id, first_name=excluded.first_name,
               last_name=excluded.last_name, birth_date=excluded.birth_date,
               gender=excluded.gender, primary_payer_code=excluded.primary_payer_code,
               last_modified_at=excluded.last_modified_at, is_new_admission=excluded.is_new_admission""",
        (p["id"], p["facility_id"], p["patient_id"], p.get("first_name"), p.get("last_name"),
         p.get("birth_date"), p.get("gender"), p.get("primary_payer_code"),
         p.get("last_modified_at"), int(p.get("is_new_admission", False))),
    )


def upsert_diagnosis(conn: sqlite3.Connection, d: dict):
    conn.execute(
        """INSERT INTO diagnoses (id, patient_id, icd10_code, icd10_description,
               clinical_status, onset_date, last_modified_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               icd10_code=excluded.icd10_code, icd10_description=excluded.icd10_description,
               clinical_status=excluded.clinical_status, onset_date=excluded.onset_date,
               last_modified_at=excluded.last_modified_at""",
        (d["id"], d["patient_id"], d.get("icd10_code"), d.get("icd10_description"),
         d.get("clinical_status"), d.get("onset_date"), d.get("last_modified_at")),
    )


def upsert_coverage(conn: sqlite3.Connection, c: dict):
    conn.execute(
        """INSERT INTO coverage (id, patient_id, payer_name, payer_code, payer_type,
               effective_from, effective_to, last_modified_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               payer_name=excluded.payer_name, payer_code=excluded.payer_code,
               payer_type=excluded.payer_type, effective_from=excluded.effective_from,
               effective_to=excluded.effective_to, last_modified_at=excluded.last_modified_at""",
        (c["id"], c["patient_id"], c.get("payer_name"), c.get("payer_code"), c.get("payer_type"),
         c.get("effective_from"), c.get("effective_to"), c.get("last_modified_at")),
    )


def upsert_note(conn: sqlite3.Connection, n: dict):
    conn.execute(
        """INSERT INTO progress_notes (id, patient_id, org_id, pcc_note_id, note_type,
               effective_date, note_text, created_by, note_label, sync_version, is_current)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               note_type=excluded.note_type, effective_date=excluded.effective_date,
               note_text=excluded.note_text, created_by=excluded.created_by,
               note_label=excluded.note_label, sync_version=excluded.sync_version,
               is_current=excluded.is_current""",
        (n["id"], n["patient_id"], n.get("org_id"), n.get("pcc_note_id"), n.get("note_type"),
         n.get("effective_date"), n.get("note_text"), n.get("created_by"), n.get("note_label"),
         n.get("sync_version"), int(n.get("is_current", True))),
    )


def upsert_assessment(conn: sqlite3.Connection, a: dict):
    conn.execute(
        """INSERT INTO assessments (id, patient_id, org_id, pcc_assessment_id, assessment_type,
               status, assessment_date, completion_date, template_id,
               assessment_type_description, raw_json, sync_version, is_current)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               assessment_type=excluded.assessment_type, status=excluded.status,
               assessment_date=excluded.assessment_date, completion_date=excluded.completion_date,
               template_id=excluded.template_id,
               assessment_type_description=excluded.assessment_type_description,
               raw_json=excluded.raw_json, sync_version=excluded.sync_version,
               is_current=excluded.is_current""",
        (a["id"], a["patient_id"], a.get("org_id"), a.get("pcc_assessment_id"),
         a.get("assessment_type"), a.get("status"), a.get("assessment_date"),
         a.get("completion_date"), a.get("template_id"), a.get("assessment_type_description"),
         a.get("raw_json"), a.get("sync_version"), int(a.get("is_current", True))),
    )


def get_sync_state() -> dict:
    try:
        with open(config.SYNC_STATE_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def set_sync_state(state: dict):
    with open(config.SYNC_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)