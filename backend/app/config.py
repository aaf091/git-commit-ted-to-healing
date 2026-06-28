"""
Central configuration for the ABI hackathon kit.

>>> AT KICKOFF, THIS IS THE FIRST FILE YOU EDIT. <<<

Everything downstream (cleaning, dedupe, rules, dashboard labels) reads from
the SCHEMA and the rule/match configs below. Re-point these to the columns in
the real dataset and most of the pipeline adapts automatically.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. SCHEMA  — map *canonical* field names -> the messy source column name(s).
#    The ingestion layer renames source columns to these canonical names.
#    List multiple candidates; the first one found in the upload wins.
# ---------------------------------------------------------------------------
SCHEMA: dict[str, list[str]] = {
    "patient_id":         ["patient_id", "pat_id", "mrn", "id"],
    "first_name":         ["first_name", "fname", "given_name", "first"],
    "last_name":          ["last_name", "lname", "family_name", "surname", "last"],
    "dob":                ["dob", "date_of_birth", "birth_date", "birthdate"],
    "gender":             ["gender", "sex"],
    "phone":              ["phone", "phone_number", "contact", "mobile"],
    "email":              ["email", "email_address"],
    "address":            ["address", "street_address", "addr"],
    "insurance_id":       ["insurance_id", "member_id", "policy_id", "subscriber_id"],
    "plan_type":          ["plan_type", "plan", "coverage"],
    "eligibility_status": ["eligibility_status", "eligibility", "coverage_status"],
    "encounter_date":     ["encounter_date", "service_date", "visit_date", "dos"],
    "procedure_code":     ["procedure_code", "cpt", "cpt_code", "proc_code"],
    "procedure_desc":     ["procedure_desc", "procedure", "service", "description"],
    "charge_amount":      ["charge_amount", "charge", "amount", "fee"],
    "billed":             ["billed", "is_billed", "claim_submitted"],
    "provider":           ["provider", "physician", "doctor", "rendering_provider"],
}

# Canonical fields the app treats as "required". Missing-value flagging uses this.
REQUIRED_FIELDS: list[str] = ["patient_id", "first_name", "last_name", "dob"]

# Date-like canonical fields → normalized to ISO YYYY-MM-DD during cleaning.
DATE_FIELDS: list[str] = ["dob", "encounter_date"]

# Numeric canonical fields → coerced to float during cleaning.
NUMERIC_FIELDS: list[str] = ["charge_amount"]

# ---------------------------------------------------------------------------
# 2. MATCH CONFIG — controls RapidFuzz dedupe (services/matching.py).
#    `blocking_key` cheaply groups records so we don't compare everyone to
#    everyone. `weights` says how much each field contributes to the score.
# ---------------------------------------------------------------------------
MATCH_CONFIG = {
    # Block on a coarse key first (here: first letter of last name + dob year).
    "blocking_fields": ["last_name", "dob"],
    "weights": {
        "first_name": 0.25,
        "last_name":  0.30,
        "dob":        0.30,
        "phone":      0.10,
        "email":      0.05,
    },
    "match_threshold": 85.0,   # >= this weighted score => candidate duplicate
    "review_threshold": 70.0,  # between review & match => "needs human review"
}

# ---------------------------------------------------------------------------
# 3. RULES — declarative rule set evaluated by services/rules_engine.py.
#    Each rule is data, not code, so you can add/remove rules at kickoff
#    without touching the engine. `expr` is a safe Python expression evaluated
#    per-row with the row's fields as variables (see rules_engine for the
#    whitelist of helpers available).
# ---------------------------------------------------------------------------
RULES: list[dict] = [
    {
        "id": "missed_billable_event",
        "label": "Missed billable event",
        "category": "revenue",
        "severity": "high",
        "expr": "has(procedure_code) and not truthy(billed)",
        "explain": "An encounter has a procedure code but was never billed.",
        "evidence_fields": ["procedure_code", "procedure_desc", "charge_amount", "billed", "encounter_date"],
    },
    {
        "id": "inactive_eligibility_service",
        "label": "Service while ineligible",
        "category": "compliance",
        "severity": "high",
        "expr": "has(encounter_date) and norm(eligibility_status) in ('inactive', 'expired', 'termed')",
        "explain": "A service was rendered while the patient's coverage was inactive.",
        "evidence_fields": ["eligibility_status", "encounter_date", "plan_type", "procedure_code"],
    },
    {
        "id": "missing_required_field",
        "label": "Missing required field",
        "category": "data_quality",
        "severity": "medium",
        "expr": "missing_any(['patient_id', 'first_name', 'last_name', 'dob'])",
        "explain": "A record is missing one or more required identity fields.",
        "evidence_fields": ["patient_id", "first_name", "last_name", "dob"],
    },
    {
        "id": "zero_charge_with_procedure",
        "label": "Procedure with no charge",
        "category": "revenue",
        "severity": "medium",
        "expr": "has(procedure_code) and num(charge_amount) <= 0",
        "explain": "A billable procedure was recorded with a zero or missing charge amount.",
        "evidence_fields": ["procedure_code", "charge_amount", "encounter_date"],
    },
]

# ---------------------------------------------------------------------------
# 4. DASHBOARD LABELS — relabel the UI for the actual problem at kickoff.
#    The frontend reads these via GET /meta.
# ---------------------------------------------------------------------------
DASHBOARD = {
    "app_name": "ABI Ops Radar",
    "tagline": "Messy healthcare data in. Reviewable, evidence-backed issues out.",
    "record_noun": "patient record",
    "record_noun_plural": "patient records",
    "issue_noun": "issue",
    "issue_noun_plural": "issues",
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
