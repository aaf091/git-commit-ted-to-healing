"""Ingestion pipeline: pull all patients + related records into SQLite.

Resolves the two-layer identity (patient_id string -> id int) from the patients
endpoint, then fetches diagnoses/coverage (by string id) and notes/assessments
(by int id). Every call goes through the resilient APIClient so the 30%
rate-limit never produces partial data.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .api_client import APIClient
from .db import connect, init_db


def _fetch_one(client: APIClient, p: dict) -> dict:
    """Fetch all related records for a single patient (thread-safe: read-only client)."""
    sid, iid = p["patient_id"], p["id"]
    return {
        "p": p,
        "diagnoses": client.diagnoses(sid),
        "coverage": client.coverage(sid),
        "notes": client.notes(iid),
        "assessments": client.assessments(iid),
    }


def ingest_parallel(reset: bool = True, limit: int | None = None,
                    workers: int = 8) -> dict:
    """Concurrent ingest. Each patient is independent; threads absorb the 30%
    rate-limit far better than a sequential loop. Writes happen on the main
    thread (SQLite is single-writer)."""
    init_db(reset=reset)
    client = APIClient(verbose=False)
    conn = connect()
    cur = conn.cursor()

    print("Fetching patients across all facilities...")
    patients = client.all_patients()
    if limit:
        patients = patients[:limit]
    print(f"Total patients: {len(patients)}")

    for p in patients:
        cur.execute(
            """INSERT OR REPLACE INTO patients
               (id, patient_id, facility_id, first_name, last_name, birth_date,
                gender, primary_payer_code, is_new_admission, last_modified_at, raw)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (p["id"], p["patient_id"], p["facility_id"], p.get("first_name"),
             p.get("last_name"), p.get("birth_date"), p.get("gender"),
             p.get("primary_payer_code"), int(p.get("is_new_admission", False)),
             p.get("last_modified_at"), json.dumps(p)))
    conn.commit()

    n, done = len(patients), 0
    failed: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one, client, p): p for p in patients}
        for fut in as_completed(futs):
            p = futs[fut]
            try:
                bundle = fut.result()
            except Exception as e:                     # never let one patient kill the run
                failed.append(p)
                print(f"  ! fetch failed for {p['patient_id']}: {e}")
                continue
            _write_bundle(cur, bundle)
            done += 1
            if done % 25 == 0 or done == n:
                print(f"  [{done}/{n}]  429s so far: {client.stats['rate_limited']}")
            conn.commit()

    # Sequential retry of any failures (slow path, guarantees completeness)
    for p in failed:
        try:
            _write_bundle(cur, _fetch_one(client, p))
            conn.commit()
            print(f"  recovered {p['patient_id']}")
        except Exception as e:
            print(f"  !! still failed {p['patient_id']}: {e}")

    # Completeness backfill: any patient with no records gets re-fetched.
    _backfill(client, conn, cur)

    conn.close()
    print("\nIngestion complete. API stats:", client.stats)
    return client.stats


def _backfill(client: APIClient, conn, cur, rounds: int = 3) -> None:
    """Re-fetch any patient missing all related records until none remain."""
    for rnd in range(rounds):
        gaps = cur.execute(
            """SELECT id, patient_id FROM patients p WHERE NOT EXISTS
               (SELECT 1 FROM diagnoses d WHERE d.patient_id=p.patient_id)
               AND NOT EXISTS (SELECT 1 FROM coverage c WHERE c.patient_id=p.patient_id)
               AND NOT EXISTS (SELECT 1 FROM notes n WHERE n.int_id=p.id)
               AND NOT EXISTS (SELECT 1 FROM assessments a WHERE a.int_id=p.id)"""
        ).fetchall()
        if not gaps:
            return
        print(f"  backfill round {rnd+1}: {len(gaps)} patients with no records")
        for row in gaps:
            p = {"id": row["id"], "patient_id": row["patient_id"]}
            try:
                _write_bundle(cur, _fetch_one(client, p))
                conn.commit()
            except Exception as e:
                print(f"    backfill failed {row['patient_id']}: {e}")


def _write_bundle(cur, b: dict) -> None:
    p = b["p"]
    sid, iid = p["patient_id"], p["id"]
    for d in b["diagnoses"]:
        cur.execute(
            """INSERT INTO diagnoses (patient_id, icd10_code, icd10_description,
               clinical_status, onset_date, raw) VALUES (?,?,?,?,?,?)""",
            (sid, d.get("icd10_code"), d.get("icd10_description"),
             d.get("clinical_status"), d.get("onset_date"), json.dumps(d)))
    for c in b["coverage"]:
        cur.execute(
            """INSERT INTO coverage (patient_id, payer_name, payer_code, payer_type,
               effective_from, effective_to, raw) VALUES (?,?,?,?,?,?,?)""",
            (sid, c.get("payer_name"), c.get("payer_code"), c.get("payer_type"),
             c.get("effective_from"), c.get("effective_to"), json.dumps(c)))
    for nt in b["notes"]:
        cur.execute(
            """INSERT INTO notes (int_id, note_type, effective_date, note_text,
               is_current, raw) VALUES (?,?,?,?,?,?)""",
            (iid, nt.get("note_type"), nt.get("effective_date"), nt.get("note_text"),
             int(nt.get("is_current", True)), json.dumps(nt)))
    for a in b["assessments"]:
        cur.execute(
            """INSERT INTO assessments (int_id, assessment_type, status,
               assessment_date, raw_json, is_current, raw) VALUES (?,?,?,?,?,?,?)""",
            (iid, a.get("assessment_type"), a.get("status"), a.get("assessment_date"),
             a.get("raw_json"), int(a.get("is_current", True)), json.dumps(a)))


def ingest(reset: bool = True, limit: int | None = None) -> dict:
    init_db(reset=reset)
    client = APIClient()
    conn = connect()
    cur = conn.cursor()

    print("Fetching patients across all facilities...")
    patients = client.all_patients()
    if limit:
        patients = patients[:limit]
    print(f"Total patients: {len(patients)}")

    for p in patients:
        cur.execute(
            """INSERT OR REPLACE INTO patients
               (id, patient_id, facility_id, first_name, last_name, birth_date,
                gender, primary_payer_code, is_new_admission, last_modified_at, raw)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (p["id"], p["patient_id"], p["facility_id"], p.get("first_name"),
             p.get("last_name"), p.get("birth_date"), p.get("gender"),
             p.get("primary_payer_code"), int(p.get("is_new_admission", False)),
             p.get("last_modified_at"), json.dumps(p)),
        )
    conn.commit()

    n = len(patients)
    for i, p in enumerate(patients, 1):
        sid, iid = p["patient_id"], p["id"]
        if i % 25 == 0 or i == n:
            print(f"  [{i}/{n}] {sid}  (429s so far: {client.stats['rate_limited']})")

        for d in client.diagnoses(sid):
            cur.execute(
                """INSERT INTO diagnoses
                   (patient_id, icd10_code, icd10_description, clinical_status,
                    onset_date, raw) VALUES (?,?,?,?,?,?)""",
                (sid, d.get("icd10_code"), d.get("icd10_description"),
                 d.get("clinical_status"), d.get("onset_date"), json.dumps(d)),
            )
        for c in client.coverage(sid):
            cur.execute(
                """INSERT INTO coverage
                   (patient_id, payer_name, payer_code, payer_type,
                    effective_from, effective_to, raw) VALUES (?,?,?,?,?,?,?)""",
                (sid, c.get("payer_name"), c.get("payer_code"), c.get("payer_type"),
                 c.get("effective_from"), c.get("effective_to"), json.dumps(c)),
            )
        for nt in client.notes(iid):
            cur.execute(
                """INSERT INTO notes
                   (int_id, note_type, effective_date, note_text, is_current, raw)
                   VALUES (?,?,?,?,?,?)""",
                (iid, nt.get("note_type"), nt.get("effective_date"),
                 nt.get("note_text"), int(nt.get("is_current", True)), json.dumps(nt)),
            )
        for a in client.assessments(iid):
            cur.execute(
                """INSERT INTO assessments
                   (int_id, assessment_type, status, assessment_date, raw_json,
                    is_current, raw) VALUES (?,?,?,?,?,?,?)""",
                (iid, a.get("assessment_type"), a.get("status"),
                 a.get("assessment_date"), a.get("raw_json"),
                 int(a.get("is_current", True)), json.dumps(a)),
            )
        conn.commit()

    conn.close()
    print("\nIngestion complete. API stats:", client.stats)
    return client.stats


if __name__ == "__main__":
    import sys
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    t0 = time.time()
    ingest(reset=True, limit=lim)
    print(f"Elapsed: {time.time()-t0:.1f}s")
