"""Eligibility + routing engine.

Combines clinical signals into one of three decisions with a human-readable
reason a billing specialist can act on:

  auto_accept      active wound dx + active Medicare Part B + complete, high-
                   confidence wound documentation (L/W/D + drainage)
  flag_for_review  eligible but documentation is incomplete or ambiguous
  reject           not billable: no active wound, no active Part B, or the
                   extraction is too unreliable to trust
"""
from __future__ import annotations

from datetime import datetime, date

from . import clinical
from .extract import WoundExtraction

ACCEPT_CONF = 0.75
REVIEW_CONF = 0.45


def _is_active_coverage(row: dict) -> bool:
    eff_to = row.get("effective_to")
    if not eff_to:
        return True
    try:
        return datetime.fromisoformat(eff_to.replace("Z", "")).date() >= date.today()
    except (ValueError, AttributeError):
        return True


def has_active_mcb(coverage_rows: list[dict]) -> bool:
    return any(c.get("payer_code") == "MCB" and _is_active_coverage(c)
              for c in coverage_rows)


def active_wound_dx(diagnoses: list[dict]) -> list[dict]:
    out = []
    for d in diagnoses:
        if d.get("clinical_status") != "active":
            continue
        code = (d.get("icd10_code") or "").upper()
        desc = (d.get("icd10_description") or "").lower()
        if clinical.is_wound_icd(code) or "ulcer" in desc or "wound" in desc:
            out.append(d)
    return out


def route(ex: WoundExtraction, diagnoses: list[dict], coverage: list[dict]) -> dict:
    wounds = active_wound_dx(diagnoses)
    has_wound = len(wounds) > 0
    has_mcb = has_active_mcb(coverage)
    measurements_complete = all(
        getattr(ex, f) is not None for f in ("length_cm", "width_cm", "depth_cm"))
    has_drainage = ex.drainage() is not None

    reasons: list[str] = []
    decision: str

    # --- hard rejects ---
    if not has_wound:
        decision = "reject"
        reasons.append("No active wound diagnosis on record.")
    elif not has_mcb:
        decision = "reject"
        payers = sorted({c.get("payer_code") for c in coverage if c.get("payer_code")})
        reasons.append(
            f"No active Medicare Part B coverage (payers: {', '.join(payers) or 'none'}); "
            "Part B is required to separately bill wound care.")
    elif ex.confidence < REVIEW_CONF or ex.wound_type is None:
        decision = "reject"
        reasons.append(
            f"Wound documentation could not be reliably extracted "
            f"(confidence {ex.confidence:.2f}); not safe to auto-bill.")
    # --- accept vs review ---
    # A patient with at least one fully-documented wound is billable on that
    # wound, even if other wounds are messier (the primary is the best-documented
    # wound, so a complete primary == "at least one complete wound").
    elif measurements_complete and has_drainage and ex.confidence >= ACCEPT_CONF:
        decision = "auto_accept"
        reasons.append(
            f"Active {ex.wound_type or 'wound'} dx + active Medicare Part B + "
            f"complete measurements ({ex.length_cm}×{ex.width_cm}×{ex.depth_cm} cm) "
            f"and drainage ({ex.drainage()}) documented; confidence {ex.confidence:.2f}.")
        if ex.multi_wound:
            reasons.append(
                f"Patient has {ex.wound_count} wounds — auto-accepted on the "
                f"best-documented one; confirm the other(s) are billed separately.")
    else:
        decision = "flag_for_review"
        if not measurements_complete:
            missing = [f.replace("_cm", "") for f in ("length_cm", "width_cm", "depth_cm")
                       if getattr(ex, f) is None]
            reasons.append(f"Missing measurement(s): {', '.join(missing)}.")
        if not has_drainage:
            reasons.append("Drainage not documented.")
        if ex.multi_wound:
            reasons.append(f"{ex.wound_count} wounds detected; no single wound is "
                           "fully documented — needs manual review.")
        if ex.confidence < ACCEPT_CONF:
            reasons.append(f"Extraction confidence below auto-accept threshold "
                           f"({ex.confidence:.2f} < {ACCEPT_CONF}).")
        reasons.append("Eligible on dx + Part B, but documentation needs a human check.")

    return {
        "decision": decision,
        "confidence": ex.confidence,
        "has_active_wound": int(has_wound),
        "has_active_mcb": int(has_mcb),
        "wound_dx": wounds[0]["icd10_description"] if wounds else None,
        "reasoning": " ".join(reasons),
    }
