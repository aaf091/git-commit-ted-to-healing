"""
Eligibility + routing engine.

Joins a patient's coverage, diagnoses and extracted wound into ONE billable-
eligibility decision the way a biller would reason about it:

  Medicare Part B wound-care billing needs all three:
    (1) an active wound,
    (2) active Medicare Part B coverage,
    (3) documented measurements (L, W, D) + a drainage level.

Routing:
  auto_accept     -> all three clearly met. Submit.
  flag_for_review -> eligible but documentation incomplete/ambiguous. Human check.
  reject          -> not billable as Part B wound care (no wound, no Part B,
                     or nothing extractable).

Output mirrors the dashboard's flag shape (decision, reasons, evidence,
confidence, status) so the existing UI renders it unchanged.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.config import (PART_B_PAYER_CODE, PAYER_LABELS, REQUIRED_MEASUREMENTS,
                        ROUTING_ORDER, WOUND_ICD10_PREFIXES)
from app.services import extraction


def assess_patient(bundle: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    p = bundle["patient"]
    diagnoses = bundle.get("diagnoses", [])
    coverage = bundle.get("coverage", [])
    notes = bundle.get("notes", [])
    assessments = bundle.get("assessments", [])

    wound = extraction.extract_wound(notes, assessments)

    # --- criterion 1: active wound -------------------------------------
    wound_dx = [d for d in diagnoses
                if str(d.get("clinical_status", "")).lower() == "active"
                and str(d.get("icd10_code", "")).upper().startswith(WOUND_ICD10_PREFIXES)]
    has_dx = bool(wound_dx)
    has_extracted = wound["extractable"]
    has_wound = has_dx or has_extracted

    # --- criterion 2: active Part B ------------------------------------
    part_b = _active_part_b(coverage, today)
    primary_payer = p.get("primary_payer_code")

    # --- criterion 3: documentation completeness -----------------------
    missing_meas = [m for m in REQUIRED_MEASUREMENTS if wound.get(m) in (None, "")]
    measurements_complete = not missing_meas
    drainage_documented = wound.get("drainage_amount") not in (None, "")

    # --- routing -------------------------------------------------------
    reasons: list[dict[str, Any]] = []

    def add(ok: bool, text: str) -> None:
        reasons.append({"ok": ok, "text": text})

    add(part_b is not None, _part_b_text(part_b, primary_payer))
    add(has_wound, _wound_text(wound_dx, wound))
    add(measurements_complete,
        "All measurements documented (L×W×D)." if measurements_complete
        else f"Missing measurement(s): {', '.join(m.replace('_cm','') for m in missing_meas)}.")
    add(drainage_documented,
        f"Drainage documented: {wound.get('drainage_amount')}." if drainage_documented
        else "Drainage amount not documented.")

    if part_b is None or not has_wound:
        decision = "reject"
    elif measurements_complete and drainage_documented:
        decision = "auto_accept"
    else:
        decision = "flag_for_review"

    # Stage is captured for context but is NOT an eligibility gate — the three
    # stated criteria are wound + Part B + measurements/drainage. We surface a
    # missing pressure-ulcer stage as a note on review items, never to block.
    if decision == "flag_for_review" and (wound.get("wound_type") == "Pressure Ulcer"
                                          and not wound.get("stage")):
        add(False, "Pressure ulcer stage not documented (context, not a blocker).")

    wound_count = wound.get("wound_count", 1)
    if wound_count > 1:
        add(True, f"{wound_count} wounds documented — routing on the best-documented "
                  f"({wound.get('location') or wound.get('wound_type') or 'primary'}).")

    return {
        "row_id": str(p.get("patient_id")),
        "internal_id": p.get("id"),
        "patient_id": p.get("patient_id"),
        "name": f"{p.get('first_name','')} {p.get('last_name','')}".strip(),
        "facility_id": p.get("facility_id"),
        "birth_date": p.get("birth_date"),
        "gender": p.get("gender"),
        "primary_payer_code": primary_payer,
        "part_b_active": part_b is not None,
        "part_b_coverage": part_b,
        "wound_dx": wound_dx,
        "has_wound": has_wound,
        "wound_source": ("both" if has_dx and has_extracted else
                         "diagnosis" if has_dx else
                         "extracted" if has_extracted else "none"),
        "wound": {k: wound[k] for k in extraction.FIELDS},
        "wound_count": wound.get("wound_count", 1),
        "wounds": [{**{k: w.get(k) for k in extraction.FIELDS},
                    "evidence": w.get("evidence", [])} for w in wound.get("wounds", [])],
        "measurements_complete": measurements_complete,
        "missing_measurements": missing_meas,
        "drainage_documented": drainage_documented,
        "decision": decision,
        "reasons": reasons,
        "reasoning": _summary(decision, reasons),
        "confidence": _confidence(decision, wound, part_b),
        "evidence": _evidence(wound, wound_dx, part_b),
        "status": "open",          # human workflow: open -> billed / dismissed
        "note_count": len(notes),
        "assessment_count": len(assessments),
    }


def assess_all(bundles: list[dict[str, Any]], today: date | None = None) -> list[dict[str, Any]]:
    rows = [assess_patient(b, today) for b in bundles]
    rows.sort(key=lambda r: (ROUTING_ORDER.get(r["decision"], 9), -r["confidence"]))
    return rows


# --------------------------------------------------------------------------- #
def _active_part_b(coverage: list[dict], today: date) -> dict[str, Any] | None:
    for c in coverage:
        if str(c.get("payer_code", "")).upper() != PART_B_PAYER_CODE:
            continue
        if _date_active(c.get("effective_from"), c.get("effective_to"), today):
            return {
                "payer_name": c.get("payer_name"),
                "payer_code": c.get("payer_code"),
                "effective_from": c.get("effective_from"),
                "effective_to": c.get("effective_to"),
            }
    return None


def _date_active(eff_from: str | None, eff_to: str | None, today: date) -> bool:
    f = _to_date(eff_from)
    t = _to_date(eff_to)
    if f and f > today:
        return False
    if t and t < today:
        return False
    return True


def _to_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _part_b_text(part_b: dict | None, primary: str | None) -> str:
    if part_b:
        return f"Active Medicare Part B coverage ({part_b.get('payer_name')})."
    label = PAYER_LABELS.get(primary, primary or "unknown")
    return f"No active Medicare Part B coverage (primary payer: {label})."


def _wound_text(wound_dx: list[dict], wound: dict) -> str:
    if wound_dx:
        d = wound_dx[0]
        return f"Active wound diagnosis {d.get('icd10_code')} — {d.get('icd10_description')}."
    if wound["extractable"]:
        wt = wound.get("wound_type") or "wound"
        return f"Wound documented in notes/assessment ({wt}), no active ICD-10 on file."
    return "No active wound diagnosis and no extractable wound documentation."


def _summary(decision: str, reasons: list[dict]) -> str:
    fails = [r["text"] for r in reasons if not r["ok"]]
    if decision == "auto_accept":
        return "Meets all Part B wound-care criteria — clean to bill."
    if decision == "reject":
        return "Not billable as Part B wound care. " + (" ".join(fails[:2]))
    return "Eligible but needs review. " + (" ".join(fails[:2]))


def _confidence(decision: str, wound: dict, part_b: dict | None) -> float:
    if decision == "reject":
        return 95.0 if part_b is None or not wound["extractable"] else 80.0
    present = sum(1 for f in extraction.FIELDS if wound.get(f) not in (None, ""))
    completeness = present / len(extraction.FIELDS)
    structured = any("assessment" in s for s in wound.get("sources", {}).values())
    base = 70 + 25 * completeness + (5 if structured else 0)
    return round(min(base, 100), 1)


def _evidence(wound: dict, wound_dx: list[dict], part_b: dict | None) -> list[dict]:
    ev: list[dict] = []
    if part_b:
        ev.append({"field": "coverage", "value": f"{part_b.get('payer_name')} "
                   f"(from {str(part_b.get('effective_from'))[:10]})"})
    if wound_dx:
        d = wound_dx[0]
        ev.append({"field": "diagnosis", "value": f"{d.get('icd10_code')} {d.get('icd10_description')}"})
    for f in extraction.FIELDS:
        if wound.get(f) not in (None, ""):
            ev.append({"field": f, "value": wound[f]})
    # show the raw text snippets the extractor used
    for e in wound.get("evidence", [])[:3]:
        ev.append({"field": f"src:{e['source']}", "value": e["snippet"]})
    return ev


def compute_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_decision: dict[str, int] = {}
    by_facility: dict[str, int] = {}
    by_status: dict[str, int] = {}
    part_b = 0
    for r in rows:
        by_decision[r["decision"]] = by_decision.get(r["decision"], 0) + 1
        fac = str(r.get("facility_id"))
        by_facility[fac] = by_facility.get(fac, 0) + 1
        st = r.get("status", "open")
        by_status[st] = by_status.get(st, 0) + 1
        part_b += 1 if r["part_b_active"] else 0
    total = len(rows) or 1
    return {
        "patient_count": len(rows),
        "auto_accept": by_decision.get("auto_accept", 0),
        "flag_for_review": by_decision.get("flag_for_review", 0),
        "reject": by_decision.get("reject", 0),
        "part_b_count": part_b,
        "part_b_pct": round(100 * part_b / total, 1),
        "by_decision": by_decision,
        "by_facility": by_facility,
        "by_status": by_status,
    }
