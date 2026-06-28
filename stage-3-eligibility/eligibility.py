"""
Stage 3 — Eligibility output table.

Produces one row per patient (per the task's literal spec), built on top of
Stage 1's `patients`/`coverage` tables and Stage 2's `wounds` table.

Routing rule, in priority order:

  1. No active Medicare Part B coverage           -> reject
     (wrong payer is a hard stop regardless of how good the wound data is)
  2. Active MCB, but zero wounds extracted at all  -> reject
     (nothing to bill -- there's no wound to attach a claim to)
  3. Active MCB, at least one wound with complete,
     non-flagged data (type, location, all 3
     measurements, drainage all present)           -> auto_accept
     (that one wound alone is enough to bill on, even if the patient also
     has other less-documented wounds)
  4. Active MCB, has wound(s), but none meet the
     completeness bar above                         -> flag_for_review
     (there's a real wound here, the documentation just isn't clean enough
      to auto-process -- a human needs to look at it)

A patient can have multiple wounds (Stage 2 confirmed up to 5 per patient
in the real data). Routing is based on whether ANY wound clears the bar,
not an average across all of them -- one well-documented wound is
billable on its own even if the patient has other messier wounds.
"""
from dataclasses import dataclass, field
from typing import Optional

import config
import storage
import extraction_storage
import eligibility_storage

REQUIRED_WOUND_FIELDS = ["wound_type", "location", "length_cm", "width_cm", "depth_cm", "drainage_amount"]


@dataclass
class EligibilityResult:
    patient_id: int
    patient_id_str: str
    facility_id: int
    first_name: Optional[str]
    last_name: Optional[str]
    primary_payer_code: Optional[str]
    has_active_mcb: bool
    has_lapsed_mcb: bool
    coverage_payer_name: Optional[str]
    coverage_effective_from: Optional[str]
    coverage_effective_to: Optional[str]
    wound_count: int
    best_wound_id: Optional[str]
    best_wound_type: Optional[str]
    best_wound_location: Optional[str]
    best_wound_stage: Optional[int]
    best_wound_length_cm: Optional[float]
    best_wound_width_cm: Optional[float]
    best_wound_depth_cm: Optional[float]
    best_wound_drainage: Optional[str]
    best_wound_confidence: Optional[str]
    best_wound_complete: bool
    any_wound_complete: bool
    decision: str  # "auto_accept" | "flag_for_review" | "reject"
    reason: str
    missing_fields_on_best: list = field(default_factory=list)


def is_wound_complete(wound: dict) -> bool:
    """A wound is billable-ready if every required field is present AND
    it wasn't flagged by Stage 2 (a flag means Stage 2 itself wasn't
    confident in this record, e.g. a template-structural gap, a
    diagnosis-fallback, or a genuine source-data conflict)."""
    if wound.get("flagged_for_review"):
        return False
    return all(wound.get(f) not in (None, "") for f in REQUIRED_WOUND_FIELDS)


def missing_fields(wound: dict) -> list:
    return [f for f in REQUIRED_WOUND_FIELDS if wound.get(f) in (None, "")]


def pick_best_wound(wounds: list[dict]) -> Optional[dict]:
    """Picks the most billable-ready wound: complete+unflagged wounds win
    over flagged ones; among complete wounds, higher confidence wins;
    among equally-ranked wounds, the one with fewest missing fields wins."""
    if not wounds:
        return None
    conf_rank = {"high": 2, "medium": 1, "low": 0}

    def score(w):
        complete = is_wound_complete(w)
        conf = conf_rank.get(w.get("confidence"), 0)
        n_missing = len(missing_fields(w))
        return (complete, conf, -n_missing)

    return max(wounds, key=score)


def check_active_mcb(coverage_rows: list[dict], today: str = None) -> Optional[dict]:
    """Returns the active MCB coverage row, or None. 'Active' means
    payer_code == MCB and effective_to is null or in the future. We don't
    have a reliable 'today' reference baked into the data, so null
    effective_to is treated as active (consistent with how Stage 1/2's
    real data behaves -- every coverage row we've seen has null
    effective_to when truly active, and a real past date when ended)."""
    import datetime
    today = today or datetime.date.today().isoformat()
    for c in coverage_rows:
        if (c.get("payer_code") or "").upper() != config.TARGET_PAYER_CODE:
            continue
        eff_to = c.get("effective_to")
        if eff_to is None or eff_to == "":
            return c
        # effective_to present -- only active if it's in the future
        if str(eff_to)[:10] >= today:
            return c
    return None


def assess_patient(patient: dict, coverage_rows: list[dict], wounds: list[dict]) -> EligibilityResult:
    active_mcb = check_active_mcb(coverage_rows)
    best = pick_best_wound(wounds)
    any_complete = any(is_wound_complete(w) for w in wounds)
    best_complete = is_wound_complete(best) if best else False

    name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
    has_lapsed = False

    if active_mcb is None:
        decision = "reject"
        # Distinguish "wrong payer entirely" from "has an MCB record, but it
        # lapsed" -- these need different wording or the reason reads as
        # contradictory (e.g. "no active Part B... payer on file: MCB").
        mcb_rows = [c for c in coverage_rows if (c.get("payer_code") or "").upper() == config.TARGET_PAYER_CODE]
        has_lapsed = bool(mcb_rows)
        if mcb_rows:
            lapsed = mcb_rows[0]
            reason = (
                f"{name} has a Medicare Part B record on file, but it is not "
                f"currently active (coverage ended {str(lapsed.get('effective_to'))[:10]}). "
                f"Active Part B coverage at the time of service is required to bill "
                f"wound care under this program, so this patient is not billable "
                f"regardless of wound documentation quality."
            )
        else:
            non_mcb_payer = patient.get("primary_payer_code") or "unknown"
            reason = (
                f"{name} does not have Medicare Part B coverage on file "
                f"(primary payer: {non_mcb_payer}). Part B is required "
                f"to bill wound care under this program, so this patient is not "
                f"billable regardless of wound documentation quality."
            )
    elif not wounds:
        decision = "reject"
        reason = (
            f"{name} has active Medicare Part B coverage, but no wound was "
            f"found in their notes or assessments. There's nothing to "
            f"attach a wound-care claim to."
        )
    elif any_complete:
        decision = "auto_accept"
        loc = best.get("location") or "an unspecified site"
        wtype = (best.get("wound_type") or "wound").replace("_", " ")
        reason = (
            f"{name} has active Medicare Part B coverage and a fully "
            f"documented {wtype} at the {loc} (type, location, all three "
            f"measurements, and drainage level are all on file). Ready to "
            f"bill."
        )
    else:
        decision = "flag_for_review"
        missing = missing_fields(best) if best else REQUIRED_WOUND_FIELDS
        flag_note = best.get("flag_reason") if best else None

        if missing:
            missing_txt = ", ".join(m.replace("_cm", "").replace("_", " ") for m in missing)
            reason = (
                f"{name} has active Medicare Part B coverage and {len(wounds)} "
                f"wound record(s) on file, but none have complete, confident "
                f"documentation. The best-documented wound is missing: "
                f"{missing_txt}."
            )
        else:
            # All 6 required fields are technically present, but the wound
            # was still flagged by Stage 2 -- e.g. the wound type came from
            # a diagnosis fallback rather than the note itself, or the
            # location had a genuine Location-vs-Laterality conflict in the
            # source data. There's nothing "missing" to name, so don't
            # claim there is -- name the actual concern instead.
            reason = (
                f"{name} has active Medicare Part B coverage and {len(wounds)} "
                f"wound record(s) on file. All required fields are present, "
                f"but the extraction was not fully confident in this record."
            )

        if flag_note:
            reason += f" Note from extraction: {flag_note}."
        reason += " A clinician or biller should confirm the details before this can be billed."

    return EligibilityResult(
        patient_id=patient["id"],
        patient_id_str=patient["patient_id"],
        facility_id=patient["facility_id"],
        first_name=patient.get("first_name"),
        last_name=patient.get("last_name"),
        primary_payer_code=patient.get("primary_payer_code"),
        has_active_mcb=active_mcb is not None,
        has_lapsed_mcb=has_lapsed,
        coverage_payer_name=active_mcb.get("payer_name") if active_mcb else None,
        coverage_effective_from=active_mcb.get("effective_from") if active_mcb else None,
        coverage_effective_to=active_mcb.get("effective_to") if active_mcb else None,
        wound_count=len(wounds),
        best_wound_id=best.get("wound_id") if best else None,
        best_wound_type=best.get("wound_type") if best else None,
        best_wound_location=best.get("location") if best else None,
        best_wound_stage=best.get("stage") if best else None,
        best_wound_length_cm=best.get("length_cm") if best else None,
        best_wound_width_cm=best.get("width_cm") if best else None,
        best_wound_depth_cm=best.get("depth_cm") if best else None,
        best_wound_drainage=best.get("drainage_amount") if best else None,
        best_wound_confidence=best.get("confidence") if best else None,
        best_wound_complete=best_complete,
        any_wound_complete=any_complete,
        decision=decision,
        reason=reason,
        missing_fields_on_best=missing_fields(best) if best else [],
    )


def run_eligibility() -> list[EligibilityResult]:
    with storage.connect() as conn:
        patients = [dict(r) for r in conn.execute("SELECT * FROM patients")]
        coverage_by_patient: dict[str, list[dict]] = {}
        for r in conn.execute("SELECT * FROM coverage"):
            row = dict(r)
            coverage_by_patient.setdefault(row["patient_id"], []).append(row)

    with extraction_storage.connect() as conn:
        wounds_by_patient: dict[int, list[dict]] = {}
        for r in conn.execute("SELECT * FROM wounds"):
            row = dict(r)
            wounds_by_patient.setdefault(row["patient_id"], []).append(row)

    results = []
    for p in patients:
        coverage_rows = coverage_by_patient.get(p["patient_id"], [])
        wounds = wounds_by_patient.get(p["id"], [])
        results.append(assess_patient(p, coverage_rows, wounds))

    eligibility_storage.init_eligibility_table()
    with eligibility_storage.connect() as conn:
        for r in results:
            eligibility_storage.upsert_result(conn, r)

    return results


def export_csv(results: list[EligibilityResult], path: str = "eligibility_output.csv") -> str:
    import csv
    fields = [
        "patient_id_str", "first_name", "last_name", "facility_id",
        "primary_payer_code", "has_active_mcb", "coverage_payer_name",
        "wound_count", "best_wound_type", "best_wound_location", "best_wound_stage",
        "best_wound_length_cm", "best_wound_width_cm", "best_wound_depth_cm",
        "best_wound_drainage", "best_wound_confidence", "decision", "reason",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        for r in results:
            writer.writerow([getattr(r, f) for f in fields])
    return path


if __name__ == "__main__":
    results = run_eligibility()
    counts = {"auto_accept": 0, "flag_for_review": 0, "reject": 0}
    for r in results:
        counts[r.decision] += 1
    print("=== Stage 3 eligibility report ===")
    print(f"  total patients: {len(results)}")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print()
    for r in results:
        print(f"[{r.decision.upper()}] {r.first_name} {r.last_name} ({r.patient_id_str}) - {r.reason}")
        print()
    csv_path = export_csv(results)
    print(f"CSV exported to: {csv_path}")
    print(f"Results also persisted to the 'eligibility' table in {config.DB_PATH}")