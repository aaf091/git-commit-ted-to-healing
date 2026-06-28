"""
Wound data extraction — the core technical challenge.

Handles MULTIPLE wounds per patient (the notes frequently document two, e.g. a
sacral pressure ulcer AND a heel wound in one note). Strategy:

  1. Gather wound CANDIDATES from every source, in order of trust:
       structured assessment fields  >  assessment narrative  >  free-text note
     Free text is segmented on each measurement (L×W×D), so a two-wound note
     yields two candidates.
  2. CLUSTER candidates by anatomical location (a wound is identified by its
     site) so the same wound seen in a note and an assessment merges into one,
     while genuinely different sites stay separate.
  3. MERGE each cluster (structured values win; free text backfills gaps).

Every field keeps its source + evidence snippet so the biller can verify — and
missing measurements are surfaced as gaps, never guessed. `extract_wound`
returns the PRIMARY (best-documented) wound for routing, plus the full list.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.config import (DRAINAGE_AMOUNTS, DRAINAGE_TYPES, STAGE_PATTERNS,
                        WOUND_TYPES)

FIELDS = ["wound_type", "stage", "location", "length_cm", "width_cm",
          "depth_cm", "drainage_amount", "drainage_type"]

# L x W [x D] with optional cm/spacing: "2.9 cm x 2.8 cm", "8.0x3.5x0.2cm".
_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:cm)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:cm)?"
    r"(?:\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:cm)?)?",
    re.IGNORECASE,
)
# Depth stated separately: "depth 1.8cm", "depth: 0.3 cm".
_DEPTH_RE = re.compile(r"depth[:\s]*?(\d+(?:\.\d+)?)\s*cm", re.IGNORECASE)

_SOURCE_RANK = {"assessment": 0, "assessment-narrative": 1, "note": 2}


def extract_wound(notes: list[dict], assessments: list[dict]) -> dict[str, Any]:
    """Back-compatible entry point: flat PRIMARY wound + the full `wounds` list."""
    wounds = extract_wounds(notes, assessments)
    primary = _pick_primary(wounds)

    flat = {f: (primary.get(f) if primary else None) for f in FIELDS}
    present = {f: flat[f] not in (None, "") for f in FIELDS}
    sources = primary.get("sources", {}) if primary else {}
    evidence = primary.get("evidence", []) if primary else []
    extractable = any(
        w.get(f) not in (None, "")
        for w in wounds
        for f in ("wound_type", "length_cm", "width_cm", "depth_cm", "drainage_amount")
    )
    return {
        **flat,
        "fields_present": present,
        "sources": sources,
        "evidence": evidence,
        "extractable": extractable,
        "wounds": wounds,
        "wound_count": len(wounds),
    }


def extract_wounds(notes: list[dict], assessments: list[dict]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for a in assessments:
        struct, narrative = _parse_assessment(a)
        label = a.get("assessment_type") or "assessment"
        if struct:
            candidates.append(_candidate(struct, "assessment", label, _struct_snippet(struct)))
        if narrative:
            for w in _wounds_from_text(narrative):
                candidates.append(_candidate(w, "assessment-narrative", label, narrative))

    for n in notes:
        text = n.get("note_text") or ""
        if not text.strip():
            continue
        ntype = n.get("note_type", "note")
        for w in _wounds_from_text(text):
            candidates.append(_candidate(w, "note", ntype, text))

    return _cluster_and_merge(candidates)


# --------------------------------------------------------------------------- #
# Candidate construction + clustering
# --------------------------------------------------------------------------- #
def _candidate(fields: dict, source_kind: str, label: str, snippet: str) -> dict[str, Any]:
    return {
        **{f: fields.get(f) for f in FIELDS},
        "_source_kind": source_kind,
        "_source": f"{source_kind}:{label}",
        "_snippet": (snippet or "").strip()[:240],
        "_rank": _SOURCE_RANK.get(source_kind, 9),
    }


def _cluster_key(c: dict) -> str:
    loc = _norm_loc(c.get("location"))
    if loc:
        return f"loc:{loc}"
    if c.get("length_cm") and c.get("width_cm"):
        return f"meas:{c['length_cm']}x{c['width_cm']}"
    if c.get("wound_type"):
        return f"type:{c['wound_type']}"
    return "unknown"


def _cluster_and_merge(candidates: list[dict]) -> list[dict[str, Any]]:
    """
    Union-find: two candidates are the SAME wound if they share an anatomical
    location OR the same length×width. This merges a wound seen in both a note
    and an assessment (even if one source lacks the location, e.g. a typo'd
    note), while keeping genuinely different sites separate.
    """
    n = len(candidates)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    loc_map: dict[str, int] = {}
    meas_map: dict[tuple, int] = {}
    for i, c in enumerate(candidates):
        loc = _norm_loc(c.get("location"))
        if loc:
            if loc in loc_map:
                union(i, loc_map[loc])
            else:
                loc_map[loc] = i
        if c.get("length_cm") and c.get("width_cm"):
            mk = (round(float(c["length_cm"]), 1), round(float(c["width_cm"]), 1))
            if mk in meas_map:
                union(i, meas_map[mk])
            else:
                meas_map[mk] = i

    groups: dict[int, list[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(candidates[i])

    wounds = [_merge_cluster(group) for group in groups.values()]
    wounds.sort(key=lambda w: -_completeness(w))  # most-complete first
    return wounds


def _merge_cluster(group: list[dict]) -> dict[str, Any]:
    group = sorted(group, key=lambda c: c["_rank"])  # structured first
    merged: dict[str, Any] = {f: None for f in FIELDS}
    sources: dict[str, str] = {}
    evidence: list[dict[str, str]] = []
    seen_snippets: set[str] = set()
    for c in group:
        used = False
        for f in FIELDS:
            if c.get(f) not in (None, "") and merged.get(f) in (None, ""):
                merged[f] = c[f]
                sources[f] = c["_source"]
                used = True
        if used and c["_snippet"] and c["_snippet"] not in seen_snippets:
            evidence.append({"source": c["_source"], "snippet": c["_snippet"]})
            seen_snippets.add(c["_snippet"])
    merged["sources"] = sources
    merged["evidence"] = evidence
    merged["fields_present"] = {f: merged[f] not in (None, "") for f in FIELDS}
    return merged


def _pick_primary(wounds: list[dict]) -> Optional[dict]:
    if not wounds:
        return None
    # Best = most required measurements + drainage present, then overall completeness.
    def billable_score(w: dict) -> tuple:
        meas = sum(1 for f in ("length_cm", "width_cm", "depth_cm") if w.get(f) not in (None, ""))
        drain = 1 if w.get("drainage_amount") not in (None, "") else 0
        return (meas + drain, _completeness(w))
    return max(wounds, key=billable_score)


def _completeness(w: dict) -> int:
    return sum(1 for f in FIELDS if w.get(f) not in (None, ""))


# --------------------------------------------------------------------------- #
# Structured assessment parsing
# --------------------------------------------------------------------------- #
def _parse_assessment(a: dict) -> tuple[dict[str, Any], Optional[str]]:
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
            elif "wound type" in question:
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
    return {k: v for k, v in out.items() if v not in (None, "")}, narrative


def _struct_snippet(struct: dict[str, Any]) -> str:
    parts = [f"{k}={v}" for k, v in struct.items() if v not in (None, "")]
    return "Structured assessment: " + ", ".join(parts) if parts else ""


# --------------------------------------------------------------------------- #
# Free-text parsing — segment into one wound per measurement
# --------------------------------------------------------------------------- #
def _wounds_from_text(text: str) -> list[dict[str, Any]]:
    matches = list(_DIM_RE.finditer(text))
    if not matches:
        seg = _parse_segment(text)
        return [seg] if seg else []

    wounds: list[dict[str, Any]] = []
    for i, m in enumerate(matches):
        prev_end = matches[i - 1].end() if i > 0 else 0
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        lead = text[prev_end:m.start()]    # before the measurement: location + type
        trail = text[m.end():next_start]   # after the measurement: drainage + depth

        w = _parse_segment(lead)
        tail = _parse_segment(trail)
        # type/location may appear on either side; drainage/stage live in the trail.
        for k in ("wound_type", "location"):
            if not w.get(k) and tail.get(k):
                w[k] = tail[k]
        for k in ("drainage_amount", "drainage_type", "stage"):
            if tail.get(k):
                w[k] = tail[k]

        w["length_cm"] = _num(m.group(1))
        w["width_cm"] = _num(m.group(2))
        if m.group(3):
            w["depth_cm"] = _num(m.group(3))
        else:
            # only look AFTER this measurement so wound 1's depth can't bleed in
            dm = _DEPTH_RE.search(trail)
            if dm:
                w["depth_cm"] = _num(dm.group(1))
        if any(w.get(f) not in (None, "") for f in FIELDS):
            wounds.append(w)
    return wounds


def _parse_segment(text: str) -> dict[str, Any]:
    """Extract non-measurement fields from a text window."""
    low = text.lower()
    out: dict[str, Any] = {}
    wt = _canon_wound_type(low)
    if wt:
        out["wound_type"] = wt
    for stage in STAGE_PATTERNS:
        if stage in low:
            out["stage"] = stage.title().replace("Dti", "DTI")
            break
    da = _canon_drainage(low)
    if da:
        out["drainage_amount"] = da
    for dt in DRAINAGE_TYPES:
        if dt in low:
            out["drainage_type"] = dt
            break
    loc = _parse_location(text)
    if loc:
        out["location"] = loc
    return out


_ANATOMY = (r"(sacral|sacrum|coccyx|ischium|ischial|trochanter|buttock|hip|heel|"
            r"ankle|foot|plantar|toe|leg|lower leg|calf|shin|thigh|knee|elbow|"
            r"forearm|hand|finger|back|shoulder|scapula|abdomen|groin)")


def _parse_location(text: str) -> Optional[str]:
    # "Pressure Ulcer to Right hip / ..." -> "Right hip"
    m = re.search(r"\bto\s+([A-Za-z][A-Za-z ]+?)\s*(?:/|,|\.|;|measures|meas|$)", text, re.IGNORECASE)
    if m:
        loc = m.group(1).strip()
        if 2 < len(loc) < 40:
            return loc.title()
    # laterality + anatomy: "L heel", "Right plantar", "Left buttock"
    m = re.search(r"\b(left|right|l|r|bilateral)\s+(?:\w+\s+)?" + _ANATOMY, text, re.IGNORECASE)
    if m:
        return re.sub(r"\s+", " ", m.group(0)).title()
    m = re.search(_ANATOMY, text, re.IGNORECASE)
    if m:
        return m.group(0).title()
    return None


def _norm_loc(loc: Any) -> Optional[str]:
    if not loc:
        return None
    s = str(loc).lower().strip()
    s = re.sub(r"^l\b", "left", s)
    s = re.sub(r"^r\b", "right", s)
    return re.sub(r"\s+", " ", s) or None


# --------------------------------------------------------------------------- #
def _canon_wound_type(text: str) -> Optional[str]:
    low = text.lower()
    for canon, phrases in WOUND_TYPES.items():
        if any(p in low for p in phrases):
            return canon
    return None


def _canon_drainage(text: str) -> Optional[str]:
    low = text.lower()
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
