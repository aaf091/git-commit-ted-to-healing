"""
Central configuration — ABI Wound Care Billing Eligibility (Medicare Part B).

Problem: identify which post-acute patients qualify for wound care billing under
Medicare Part B, by ingesting a mock PointClickCare API, extracting wound details
from free-text notes + structured assessments, and routing each patient to
auto_accept / flag_for_review / reject with plain-English reasoning.

>>> THIS IS THE FILE YOU TUNE. <<<
Everything downstream (extraction vocab, eligibility rules, routing thresholds,
dashboard labels) reads from here.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. API
# ---------------------------------------------------------------------------
PCC_BASE_URL = "https://hackathon.prod.pulsefoundry.ai"
FACILITIES = {101: "Facility A", 102: "Facility B", 103: "Facility C"}

# ---------------------------------------------------------------------------
# 2. COVERAGE — what counts as billable Medicare Part B.
# ---------------------------------------------------------------------------
PART_B_PAYER_CODE = "MCB"  # coverage.payer_code for Medicare Part B
PAYER_LABELS = {"MCB": "Medicare Part B", "MCA": "Medicare Part A",
                "MCD": "Medicaid", "HMO": "HMO"}

# ---------------------------------------------------------------------------
# 3. WOUND CLINICAL VOCABULARY — drives both extraction and "is there a wound".
# ---------------------------------------------------------------------------
# ICD-10 prefixes that indicate an active billable wound (pressure/diabetic/
# venous ulcers, chronic ulcers of skin, etc.).
WOUND_ICD10_PREFIXES = ("L89", "L97", "L98.4", "I83.0", "I83.2", "E11.621", "E11.622")

# Canonical wound types + the phrases that map to them (lowercased, substring).
WOUND_TYPES = {
    "Pressure Ulcer":      ["pressure ulcer", "pressure injury", "decubitus", "bedsore", "l89"],
    "Diabetic Foot Ulcer": ["diabetic foot ulcer", "diabetic ulcer", "diabetic", "dfu", "e11.621", "e11.622"],
    "Venous Ulcer":        ["venous ulcer", "venous stasis", "stasis ulcer", "venous", "i83"],
    "Arterial Ulcer":      ["arterial ulcer", "ischemic ulcer"],
    "Surgical Wound":      ["surgical wound", "incision", "dehiscence"],
    "Trauma/Laceration":   ["laceration", "skin tear", "abrasion", "trauma"],
}

# Drainage amount vocabulary (ordered none -> heavy). Maps note/assessment text.
DRAINAGE_AMOUNTS = {
    "none":     ["none", "no drainage", "dry", "minimal"],
    "light":    ["light", "scant", "small", "low"],
    "moderate": ["moderate", "mod ", "moderate amount"],
    "heavy":    ["heavy", "large", "copious", "profuse"],
}
# Drainage *type* (serosanguineous etc.) — captured for context, not required.
DRAINAGE_TYPES = ["serosanguineous", "serosang", "serous", "sanguineous",
                  "purulent", "seropurulent", "bloody"]

# Pressure-ulcer stage vocabulary.
STAGE_PATTERNS = ["stage 1", "stage 2", "stage 3", "stage 4",
                  "unstageable", "deep tissue injury", "dti"]

# ---------------------------------------------------------------------------
# 4. ROUTING — the three decisions the biller acts on.
#    Each patient gets exactly one. Reasoning lists which criteria passed/failed.
# ---------------------------------------------------------------------------
# A wound is "fully measured" when length, width AND depth are all present.
REQUIRED_MEASUREMENTS = ["length_cm", "width_cm", "depth_cm"]
# Drainage must be documented (an amount, not just "present").
ROUTING = {
    "auto_accept":     {"label": "Auto-accept", "severity": "auto",
                        "desc": "Active wound + active Part B + complete measurements + drainage all clearly documented. Biller can submit."},
    "flag_for_review": {"label": "Flag for review", "severity": "review",
                        "desc": "Eligible but documentation is incomplete or ambiguous. Needs a human check before billing."},
    "reject":          {"label": "Reject", "severity": "reject",
                        "desc": "Not billable as Part B wound care — no active wound, no Part B coverage, or nothing extractable."},
}
ROUTING_ORDER = {"flag_for_review": 0, "auto_accept": 1, "reject": 2}  # review first

# ---------------------------------------------------------------------------
# 5. DASHBOARD LABELS — relabel the UI here.
# ---------------------------------------------------------------------------
DASHBOARD = {
    "app_name": "ABI Wound-Care Eligibility Radar",
    "tagline": "PointClickCare data in. Part B wound-care billing decisions out — with evidence.",
    "record_noun": "patient",
    "record_noun_plural": "patients",
}
