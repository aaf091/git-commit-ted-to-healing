"""
Storage for Stage 2 output. Two tables:

  extracted_wounds  -- one row per source record (every note/assessment that
                       produced a wound extraction), keyed by (source_table,
                       source_record_id) so reruns are idempotent.

  wounds             -- one row per DISTINCT WOUND, derived by grouping
                       extracted_wounds by (patient_id, location). Each
                       wound's fields come from its most recent, highest-
                       confidence source record -- not just the latest one
                       chronologically, since a later narrative note
                       shouldn't override an earlier structured assessment.

This two-table split keeps full traceability (every extraction is kept,
nothing is overwritten) while giving Stage 3 a clean one-row-per-wound view
to roll up into the per-patient eligibility table.
"""
import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS extracted_wounds (
    source_table TEXT NOT NULL,
    source_record_id INTEGER NOT NULL,
    wound_index INTEGER NOT NULL DEFAULT 0,
    patient_id INTEGER NOT NULL,
    source_type TEXT,
    confidence TEXT,
    record_date TEXT,
    wound_type TEXT,
    stage INTEGER,
    location TEXT,
    length_cm REAL,
    width_cm REAL,
    depth_cm REAL,
    drainage_amount TEXT,
    drainage_raw TEXT,
    treatment_note TEXT,
    flagged_for_review INTEGER,
    flag_reason TEXT,
    extracted_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (source_table, source_record_id, wound_index)
);

CREATE TABLE IF NOT EXISTS wounds (
    wound_id TEXT PRIMARY KEY,           -- patient_id + ':' + normalized location
    patient_id INTEGER NOT NULL,
    location TEXT,
    wound_type TEXT,
    stage INTEGER,
    length_cm REAL,
    width_cm REAL,
    depth_cm REAL,
    drainage_amount TEXT,
    confidence TEXT,
    best_source_table TEXT,
    best_source_record_id INTEGER,
    record_count INTEGER,                -- how many notes/assessments fed this wound
    flagged_for_review INTEGER,
    flag_reason TEXT,
    last_record_date TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_extracted_patient ON extracted_wounds(patient_id);
CREATE INDEX IF NOT EXISTS idx_wounds_patient ON wounds(patient_id);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_extraction_tables():
    with connect() as conn:
        conn.executescript(SCHEMA)


def upsert_extracted_wound(conn: sqlite3.Connection, w) -> None:
    conn.execute(
        """INSERT INTO extracted_wounds
               (source_table, source_record_id, wound_index, patient_id, source_type, confidence,
                record_date, wound_type, stage, location, length_cm, width_cm, depth_cm,
                drainage_amount, drainage_raw, treatment_note, flagged_for_review, flag_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(source_table, source_record_id, wound_index) DO UPDATE SET
               patient_id=excluded.patient_id, source_type=excluded.source_type,
               confidence=excluded.confidence, record_date=excluded.record_date,
               wound_type=excluded.wound_type, stage=excluded.stage, location=excluded.location,
               length_cm=excluded.length_cm, width_cm=excluded.width_cm, depth_cm=excluded.depth_cm,
               drainage_amount=excluded.drainage_amount, drainage_raw=excluded.drainage_raw,
               treatment_note=excluded.treatment_note,
               flagged_for_review=excluded.flagged_for_review, flag_reason=excluded.flag_reason""",
        (w.source_table, w.source_record_id, w.wound_index, w.patient_id, w.source_type, w.confidence,
         w.record_date, w.wound_type, w.stage, w.location, w.length_cm, w.width_cm, w.depth_cm,
         w.drainage_amount, w.drainage_raw, w.treatment_note,
         int(w.flagged_for_review), w.flag_reason),
    )


def upsert_wound(conn: sqlite3.Connection, wound_row: dict) -> None:
    conn.execute(
        """INSERT INTO wounds
               (wound_id, patient_id, location, wound_type, stage, length_cm, width_cm, depth_cm,
                drainage_amount, confidence, best_source_table, best_source_record_id,
                record_count, flagged_for_review, flag_reason, last_record_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(wound_id) DO UPDATE SET
               location=excluded.location, wound_type=excluded.wound_type, stage=excluded.stage,
               length_cm=excluded.length_cm, width_cm=excluded.width_cm, depth_cm=excluded.depth_cm,
               drainage_amount=excluded.drainage_amount, confidence=excluded.confidence,
               best_source_table=excluded.best_source_table,
               best_source_record_id=excluded.best_source_record_id,
               record_count=excluded.record_count,
               flagged_for_review=excluded.flagged_for_review, flag_reason=excluded.flag_reason,
               last_record_date=excluded.last_record_date,
               updated_at=datetime('now')""",
        (wound_row["wound_id"], wound_row["patient_id"], wound_row["location"],
         wound_row["wound_type"], wound_row["stage"], wound_row["length_cm"],
         wound_row["width_cm"], wound_row["depth_cm"], wound_row["drainage_amount"],
         wound_row["confidence"], wound_row["best_source_table"],
         wound_row["best_source_record_id"], wound_row["record_count"],
         int(wound_row["flagged_for_review"]), wound_row["flag_reason"],
         wound_row["last_record_date"]),
    )