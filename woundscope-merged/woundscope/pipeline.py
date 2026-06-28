"""Orchestrator: read stored records -> extract -> route -> write results table.

Runs entirely off the local SQLite DB, so it can be re-run instantly without
touching the rate-limited API.
"""
from __future__ import annotations

import json

from .db import connect, reset_results
from .extract import extract_for_patient
from .route import route


def build_results() -> list[dict]:
    reset_results()
    conn = connect()
    cur = conn.cursor()
    patients = cur.execute("SELECT * FROM patients").fetchall()
    results: list[dict] = []

    for p in patients:
        sid, iid = p["patient_id"], p["id"]
        diagnoses = [dict(r) for r in cur.execute(
            "SELECT * FROM diagnoses WHERE patient_id=?", (sid,)).fetchall()]
        coverage = [dict(r) for r in cur.execute(
            "SELECT * FROM coverage WHERE patient_id=?", (sid,)).fetchall()]
        notes = [dict(r) for r in cur.execute(
            "SELECT * FROM notes WHERE int_id=?", (iid,)).fetchall()]
        assessments = [dict(r) for r in cur.execute(
            "SELECT * FROM assessments WHERE int_id=?", (iid,)).fetchall()]

        ex = extract_for_patient(notes, assessments, diagnoses)
        decision = route(ex, diagnoses, coverage)

        row = {
            "patient_id": sid,
            "int_id": iid,
            "name": f"{p['first_name']} {p['last_name']}",
            "facility_id": p["facility_id"],
            "decision": decision["decision"],
            "confidence": decision["confidence"],
            "has_active_wound": decision["has_active_wound"],
            "has_active_mcb": decision["has_active_mcb"],
            "wound_type": ex.wound_type,
            "wound_stage": ex.stage,
            "wound_location": ex.location,
            "length_cm": ex.length_cm,
            "width_cm": ex.width_cm,
            "depth_cm": ex.depth_cm,
            "drainage": ex.drainage(),
            "sources": json.dumps(ex.sources),
            "evidence": json.dumps(ex.evidence),
            "wound_count": ex.wound_count,
            "wounds": json.dumps(ex.wounds, default=str),
            "reasoning": decision["reasoning"],
        }
        cur.execute(
            """INSERT OR REPLACE INTO results
               (patient_id,int_id,name,facility_id,decision,confidence,
                has_active_wound,has_active_mcb,wound_type,wound_stage,
                wound_location,length_cm,width_cm,depth_cm,drainage,sources,
                evidence,wound_count,wounds,reasoning,raw)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["patient_id"], row["int_id"], row["name"], row["facility_id"],
             row["decision"], row["confidence"], row["has_active_wound"],
             row["has_active_mcb"], row["wound_type"], row["wound_stage"],
             row["wound_location"], row["length_cm"], row["width_cm"],
             row["depth_cm"], row["drainage"], row["sources"], row["evidence"],
             row["wound_count"], row["wounds"], row["reasoning"],
             json.dumps(row)),
        )
        results.append(row)

    conn.commit()
    conn.close()
    return results


def summarize(results: list[dict]) -> dict:
    from collections import Counter
    c = Counter(r["decision"] for r in results)
    return {
        "total": len(results),
        "auto_accept": c.get("auto_accept", 0),
        "flag_for_review": c.get("flag_for_review", 0),
        "reject": c.get("reject", 0),
    }


if __name__ == "__main__":
    res = build_results()
    s = summarize(res)
    print("Results:", s)
    print("\nSample (first 10):")
    for r in res[:10]:
        print(f"  {r['patient_id']:7} {r['decision']:16} conf={r['confidence']:.2f} "
              f"{r['wound_type'] or '-':18} {r['reasoning'][:60]}")
