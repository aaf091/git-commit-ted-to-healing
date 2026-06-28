"""
Storage for Stage 3 output: one row per patient, the literal deliverable
the task asks for. Lands in the same pcc_data.db as Stages 1 and 2.
"""
import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS eligibility (
    patient_id INTEGER PRIMARY KEY,
    patient_id_str TEXT,
    facility_id INTEGER,
    first_name TEXT,
    last_name TEXT,
    primary_payer_code TEXT,
    has_active_mcb INTEGER,
    has_lapsed_mcb INTEGER,
    coverage_payer_name TEXT,
    coverage_effective_from TEXT,
    coverage_effective_to TEXT,
    wound_count INTEGER,
    best_wound_id TEXT,
    best_wound_type TEXT,
    best_wound_location TEXT,
    best_wound_stage INTEGER,
    best_wound_length_cm REAL,
    best_wound_width_cm REAL,
    best_wound_depth_cm REAL,
    best_wound_drainage TEXT,
    best_wound_confidence TEXT,
    best_wound_complete INTEGER,
    any_wound_complete INTEGER,
    decision TEXT,
    reason TEXT,
    computed_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_eligibility_decision ON eligibility(decision);
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


def init_eligibility_table():
    with connect() as conn:
        conn.executescript(SCHEMA)


def upsert_result(conn: sqlite3.Connection, r) -> None:
    conn.execute(
        """INSERT INTO eligibility
               (patient_id, patient_id_str, facility_id, first_name, last_name,
                primary_payer_code, has_active_mcb, has_lapsed_mcb, coverage_payer_name,
                coverage_effective_from, coverage_effective_to, wound_count,
                best_wound_id, best_wound_type, best_wound_location, best_wound_stage,
                best_wound_length_cm, best_wound_width_cm, best_wound_depth_cm,
                best_wound_drainage, best_wound_confidence, best_wound_complete,
                any_wound_complete, decision, reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(patient_id) DO UPDATE SET
               has_active_mcb=excluded.has_active_mcb, wound_count=excluded.wound_count,
               best_wound_id=excluded.best_wound_id, decision=excluded.decision,
               reason=excluded.reason, computed_at=datetime('now')""",
        (r.patient_id, r.patient_id_str, r.facility_id, r.first_name, r.last_name,
         r.primary_payer_code, int(r.has_active_mcb), int(r.has_lapsed_mcb), r.coverage_payer_name,
         r.coverage_effective_from, r.coverage_effective_to, r.wound_count,
         r.best_wound_id, r.best_wound_type, r.best_wound_location, r.best_wound_stage,
         r.best_wound_length_cm, r.best_wound_width_cm, r.best_wound_depth_cm,
         r.best_wound_drainage, r.best_wound_confidence, int(r.best_wound_complete),
         int(r.any_wound_complete), r.decision, r.reason),
    )