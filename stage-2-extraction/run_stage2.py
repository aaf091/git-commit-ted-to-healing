"""
Stage 2 orchestrator.

1. Read every progress_note and assessment from Stage 1's database.
2. Run the appropriate extractor on each (with diagnosis fallback for
   narrative notes that don't name a wound type).
3. Store every individual extraction in `extracted_wounds` (full audit
   trail -- nothing is thrown away).
4. Group extractions per patient by normalized location into distinct
   `wounds` -- this is the "a patient can have N wounds" structure.
   Each wound's displayed fields come from its single best source record
   (highest confidence, then most recent), not a blended average across
   all records, so the wound's data always traces back to one real
   document.
"""
import sqlite3
from collections import defaultdict

import storage as stage1_storage
import extraction
import extraction_storage as storage

CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}


def get_diagnosis_hint(conn: sqlite3.Connection, internal_patient_id: int) -> str | None:
    # diagnoses are keyed on the string patient_id (e.g. "FA-001"), not the
    # internal integer id notes/assessments use -- resolve via patients table.
    row = conn.execute(
        "SELECT patient_id FROM patients WHERE id = ?", (internal_patient_id,)
    ).fetchone()
    if not row:
        return None
    diag = conn.execute(
        "SELECT icd10_description FROM diagnoses WHERE patient_id = ? "
        "AND clinical_status = 'active' ORDER BY last_modified_at DESC LIMIT 1",
        (row["patient_id"],),
    ).fetchone()
    return diag["icd10_description"] if diag else None


def run_extraction() -> dict:
    storage.init_extraction_tables()
    stats = {"assessments_processed": 0, "notes_processed": 0, "wound_records_from_notes": 0,
              "flagged_for_review": 0, "wounds_identified": 0}

    with stage1_storage.connect() as src_conn:
        assessments = [dict(r) for r in src_conn.execute("SELECT * FROM assessments WHERE is_current = 1")]
        notes = [dict(r) for r in src_conn.execute("SELECT * FROM progress_notes WHERE is_current = 1")]
        diagnosis_cache = {}
        for n in notes:
            pid = n["patient_id"]
            if pid not in diagnosis_cache:
                diagnosis_cache[pid] = get_diagnosis_hint(src_conn, pid)

    extracted = []
    with storage.connect() as conn:
        for row in assessments:
            result = extraction.extract_from_assessment(row)
            storage.upsert_extracted_wound(conn, result)
            extracted.append(result)
            stats["assessments_processed"] += 1
            if result.flagged_for_review:
                stats["flagged_for_review"] += 1

        for row in notes:
            hint = diagnosis_cache.get(row["patient_id"])
            results = extraction.extract_from_note(row, diagnosis_hint=hint)
            stats["notes_processed"] += 1
            for result in results:
                storage.upsert_extracted_wound(conn, result)
                extracted.append(result)
                stats["wound_records_from_notes"] += 1
                if result.flagged_for_review:
                    stats["flagged_for_review"] += 1

        wounds = group_into_wounds(extracted)
        for wound_row in wounds:
            storage.upsert_wound(conn, wound_row)
        stats["wounds_identified"] = len(wounds)

    return stats


def group_into_wounds(extracted: list) -> list[dict]:
    """Groups individual extraction records into distinct wounds per
    patient by normalized location. A missing location can't be safely
    grouped with anything (we don't know which wound it belongs to), so
    each such record becomes its own singleton wound rather than being
    silently dropped or merged into an arbitrary bucket."""
    groups = defaultdict(list)
    ungrouped_counter = 0
    for w in extracted:
        if w.location:
            key = (w.patient_id, w.location)
        else:
            ungrouped_counter += 1
            key = (w.patient_id, f"__unknown_{w.source_table}_{w.source_record_id}")
        groups[key].append(w)

    wound_rows = []
    for (patient_id, location_key), records in groups.items():
        best = max(records, key=lambda r: (CONFIDENCE_RANK.get(r.confidence, 0), r.record_date or ""))
        latest_date = max((r.record_date for r in records if r.record_date), default=None)

        is_unknown_location = location_key.startswith("__unknown_")
        has_low_confidence_contributor = any(r.confidence == "low" for r in records)

        flag_reason = best.flag_reason
        if is_unknown_location and not flag_reason:
            flag_reason = "location could not be determined; wound could not be grouped with related records"
        elif has_low_confidence_contributor and best.confidence != "low":
            # The displayed fields come from a high/medium-confidence record,
            # but at least one contributing note for this same wound was a
            # low-confidence narrative extraction. Surface that explicitly --
            # a biller should know not every record behind this wound agrees,
            # even though the headline values are trustworthy.
            n_low = sum(1 for r in records if r.confidence == "low")
            flag_reason = (
                f"{n_low} of {len(records)} record(s) for this wound came from "
                f"lower-confidence narrative notes; displayed values use the "
                f"best available ({best.source_table} #{best.source_record_id})"
            )

        wound_rows.append({
            "wound_id": f"{patient_id}:{location_key}",
            "patient_id": patient_id,
            "location": None if is_unknown_location else location_key,
            "wound_type": best.wound_type,
            "stage": best.stage,
            "length_cm": best.length_cm,
            "width_cm": best.width_cm,
            "depth_cm": best.depth_cm,
            "drainage_amount": best.drainage_amount,
            "confidence": best.confidence,
            "best_source_table": best.source_table,
            "best_source_record_id": best.source_record_id,
            "record_count": len(records),
            "flagged_for_review": bool(best.flagged_for_review or is_unknown_location or has_low_confidence_contributor),
            "flag_reason": flag_reason,
            "last_record_date": latest_date,
        })
    return wound_rows


if __name__ == "__main__":
    result = run_extraction()
    print("\n=== Stage 2 extraction report ===")
    for k, v in result.items():
        print(f"  {k}: {v}")