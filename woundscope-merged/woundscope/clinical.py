"""Clinical vocab + normalization (merged from the team's strongest pieces).

- Comprehensive wound ICD-10 coverage and ICD->type inference (from jay's branch,
  including burns / abscess / surgical / arterial codes found in real data).
- Location-string repair for mangled free text like "Rightlowerle" (jay).
- Wound-type, drainage, and stage vocab + abbreviation maps.

Kept dependency-free so every module (extraction, routing) shares one source of
clinical truth.
"""
from __future__ import annotations

import re

# --- ICD-10: which active diagnoses make a wound billable -------------------
WOUND_ICD10_PREFIXES = (
    "L89",                                  # pressure ulcer
    "L97",                                  # non-pressure chronic ulcer
    "L98.4",                                # non-pressure chronic ulcer, other
    "E10.621", "E11.621", "E10.622", "E11.622",  # diabetic ulcer
    "I83.0", "I83.2",                       # venous stasis ulcer w/ ulceration
    "I70.23", "I70.24", "I70.25",           # arterial / atherosclerotic ulcer
    "L02",                                  # cutaneous abscess
    "T81.3", "T81.4",                       # surgical wound complications
    "T20", "T21", "T22", "T23", "T24", "T25",    # burns by site
)

# ICD-10 prefix -> canonical wound_type (authoritative type backfill)
ICD10_TO_WOUND_TYPE = [
    ("L89", "pressure_ulcer"),
    ("L97", "pressure_ulcer"),
    ("L98.4", "pressure_ulcer"),
    ("E10.62", "diabetic_foot_ulcer"),
    ("E11.62", "diabetic_foot_ulcer"),
    ("I83", "venous_ulcer"),
    ("I70.2", "arterial_ulcer"),
    ("L02", "abscess"),
    ("T81", "surgical_wound"),
    ("T20", "burn"), ("T21", "burn"), ("T22", "burn"),
    ("T23", "burn"), ("T24", "burn"), ("T25", "burn"),
]

# --- free-text wound-type detection ----------------------------------------
WOUND_TYPE_PATTERNS = [
    ("pressure_ulcer", r"pressure\s+(?:ulcer|injury|sore)|decubitus|bed\s*sore|\bpu\b"),
    ("diabetic_foot_ulcer", r"diabetic(?:\s+foot)?(?:\s+ulcer)?|\bdfu\b|neuropathic\s+ulcer"),
    ("venous_ulcer", r"venous(?:\s+stasis)?(?:\s+ulcer)?|stasis\s+ulcer|\bvsu\b"),
    ("arterial_ulcer", r"arterial(?:\s+ulcer)?|ischemic\s+ulcer"),
    ("surgical_wound", r"surgical\s+(?:wound|site)|incision|dehiscence"),
    ("burn", r"\bburn\b"),
    ("abscess", r"\babscess\b"),
    ("skin_tear", r"skin\s+tear"),
]

# --- drainage vocab + abbreviations ----------------------------------------
DRAINAGE_TYPES = ["serosanguineous", "serosang", "serous", "sanguineous",
                  "purulent", "seropurulent", "bloody"]
DRAINAGE_TYPE_CANON = {"serosang": "serosanguineous"}
DRAINAGE_AMOUNTS = ["none", "scant", "minimal", "small", "moderate", "large",
                    "heavy", "copious"]
DRAINAGE_AMOUNT_ABBR = {"mod": "moderate", "min": "minimal", "lt": "minimal",
                        "light": "minimal", "lg": "large", "hvy": "heavy",
                        "sm": "small", "no": "none"}

# --- location repair for mangled free text (jay) ---------------------------
_LOCATION_FIXES = {
    "lowerle": "lower leg", "lowerleg": "lower leg",
    "lowerex": "lower extremity", "lowerext": "lower extremity",
    "upperarm": "upper arm", "upperex": "upper extremity",
    "buttoc": "buttock", "sacrumarea": "sacrum",
}
_SITES = ["sacrum", "coccyx", "ischium", "trochanter", "hip", "heel", "ankle",
          "foot", "toe", "buttock", "elbow", "calf", "shin", "lower leg",
          "lower extremity", "knee", "thigh"]


def normalize_location(raw: str | None) -> str | None:
    if not raw:
        return None
    t = raw.strip().lower()
    for bad, good in _LOCATION_FIXES.items():
        t = t.replace(bad, good)
    return t.title()


def infer_type_from_icd(codes: list[str]) -> str | None:
    for code in codes:
        c = (code or "").upper()
        for prefix, wt in ICD10_TO_WOUND_TYPE:
            if c.startswith(prefix):
                return wt
    return None


def is_wound_icd(code: str) -> bool:
    return (code or "").upper().startswith(WOUND_ICD10_PREFIXES)
