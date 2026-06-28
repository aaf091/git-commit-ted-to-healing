"""
Wound data extraction — the core technical challenge.

Pulls wound fields (type, stage, location, length/width/depth cm, drainage
amount + type) from THREE source shapes, in order of trust:
  1. Structured assessment sections  (raw_json -> sections -> question/answer)
  2. Narrative answer inside an assessment ("Wound narrative" free text)
  3. Free-text progress notes         (Envive narrative OR terse SPN)

Every field records WHERE it came from and the EVIDENCE snippet, so the
dashboard can show the biller exactly why each value was extracted — never a
black box. Structured values win; gaps are backfilled from free text.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.config import (DRAINAGE_AMOUNTS, DRAINAGE_TYPES, STAGE_PATTERNS,
                        WOUND_TYPES)

FIELDS = ["wound_type", "stage", "location", "length_cm", "width_cm",
          "depth_cm", "drainage_amount", "drainage_type"]

# L x W [x D] with optional cm and spacing: "2.9 cm x 2.8 cm", "8.0x3.5x0.2cm".
_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:cm)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:cm)?"
    r"(?:\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:cm)?)?",
    re.IGNORECASE,
)


def extract_wound(notes: list[dict], assessments: list[dict]) -> dict[str, Any]:
    """Merge all sources into one wound record with provenance + evidence."""
    fields: dict[str, Any] = {f: None for f in FIELDS}
    sources: dict[str, str] = {}
    evidence: list[dict[str, str]] = []

    def absorb(partial: dict[str, Any], source: str, snippet: str) -> None:
        used = False
        for k, v in partial.items():
            if v in (None, "") or fields.get(k) not in (None, ""):
                continue
            fields[k] = v
            sources[k] = source
            used = True
        if used and snippet:
            evidence.append({"source": source, "snippet": snippet.strip()[:240]})

    # 1) structured assessments first (highest trust)
    for a in assessments:
        struct, narrative = _parse_assessment(a)
        label = a.get("assessment_type") or "assessment"
        absorb(struct, f"assessment:{label}", _struct_snippet(struct))
        if narrative:
            absorb(_parse_free_text(narrative), f"assessment-narrative:{label}", narrative)

    # 2) then notes (backfill remaining gaps)
    for n in notes:
        text = n.get("note_text") or ""
        if text.strip():
            absorb(_parse_free_text(text), f"note:{n.get('note_type','note')}", text)

    present = {f: fields[f] not in (None, "") for f in FIELDS}
    extractable = any(present[f] for f in
                      ("wound_type", "length_cm", "width_cm", "depth_cm", "drainage_amount"))
    return {
        **fields,
        "fields_present": present,
        "sources": sources,
        "evidence": evidence,
        "extractable": extractable,
    }


# --------------------------------------------------------------------------- #
# Structured assessment parsing
# --------------------------------------------------------------------------- #
def _parse_assessment(a: dict) -> tuple[dict[str, Any], Optional[str]]:
    """Returns (structured_fields, narrative_text_or_None)."""
    raw = a.get("raw_json")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}, raw
    if not isinstance(raw, dict):
        return {}, None

    out: dict[str, Any] = {}
    narrative: Optional[str] = None
    for section in raw.get("sections", []):
        for q in section.get("questions", []):
            question = str(q.get("question", "")).strip().lower()
            answer = q.get("answer")
            if answer in (None, ""):
                continue
            ans = str(answer).strip()
            if "narrative" in question or "wound status" in question:
                narrative = ans
            elif question == "wound type" or "wound type" in question:
                out["wound_type"] = _canon_wound_type(ans) or ans
            elif question.startswith("stage"):
                out.setdefault("stage", _clean_stage(ans))
            elif "location" in question and "laterality" not in question:
                out["location"] = ans
            elif question.startswith("length"):
                out["length_cm"] = _num(ans)
            elif question.startswith("width"):
                out["width_cm"] = _num(ans)
            elif question.startswith("depth"):
                out["depth_cm"] = _num(ans)
            elif "drainage amount" in question or question == "amount":
                out["drainage_amount"] = _canon_drainage(ans)
            elif "drainage type" in question or question == "type":
                out["drainage_type"] = ans
            elif "drainage present" in question and ans.lower().startswith("y"):
                out.setdefault("_drainage_present", True)
    out.pop("_drainage_present", None)
    return {k: v for k, v in out.items() if v not in (None, "")}, narrative


def _struct_snippet(struct: dict[str, Any]) -> str:
    parts = [f"{k}={v}" for k, v in struct.items() if v not in (None, "")]
    return "Structured assessment: " + ", ".join(parts) if parts else ""


# --------------------------------------------------------------------------- #
# Free-text parsing (notes + narrative answers)
# --------------------------------------------------------------------------- #
def _parse_free_text(text: str) -> dict[str, Any]:
    low = text.lower()
    out: dict[str, Any] = {}

    out["wound_type"] = _canon_wound_type(low)

    for stage in STAGE_PATTERNS:
        if stage in low:
            out["stage"] = stage.title().replace("Dti", "DTI")
            break

    m = _DIM_RE.search(text)
    if m:
        out["length_cm"] = _num(m.group(1))
        out["width_cm"] = _num(m.group(2))
        if m.group(3):
            out["depth_cm"] = _num(m.group(3))

    out["drainage_amount"] = _canon_drainage(low)
    for dt in DRAINAGE_TYPES:
        if dt in low:
            out["drainage_type"] = dt
            break

    loc = _parse_location(text)
    if loc:
        out["location"] = loc

    return {k: v for k, v in out.items() if v not in (None, "")}


def _parse_location(text: str) -> Optional[str]:
    # "Pressure Ulcer to Right hip / Measures..." -> "Right hip"
    m = re.search(r"\bto\s+([A-Za-z][A-Za-z ]+?)\s*(?:/|,|\.|;|$)", text)
    if m:
        loc = m.group(1).strip()
        if 2 < len(loc) < 40:
            return loc.title()
    return None


# --------------------------------------------------------------------------- #
# Canonicalizers
# --------------------------------------------------------------------------- #
def _canon_wound_type(text: str) -> Optional[str]:
    low = text.lower()
    for canon, phrases in WOUND_TYPES.items():
        if any(p in low for p in phrases):
            return canon
    return None


def _canon_drainage(text: str) -> Optional[str]:
    low = text.lower()
    # Check heavy -> light order so "moderate" isn't shadowed by "mod" in "moderate".
    for amount in ("heavy", "moderate", "light", "none"):
        if any(kw in low for kw in DRAINAGE_AMOUNTS[amount]):
            return amount
    return None


def _clean_stage(ans: str) -> Optional[str]:
    a = ans.strip()
    if not a or a.lower() in ("n/a", "na", "none", "-", "unknown"):
        return None
    return a


def _num(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else None
