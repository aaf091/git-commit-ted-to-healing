"""Wound-data extraction engine (merged).

Combines the team's best ideas:
  - tiered, reliability-ordered sources with provenance + confidence (ours)
  - authoritative wound type/stage from the ICD-10 diagnosis (ours + jay)
  - MULTI-WOUND handling: free text is segmented per measurement, candidates are
    clustered by anatomical location, and each cluster merged (aishwarya)
  - an EVIDENCE snippet kept for every field so a biller can verify (aishwarya)
  - location repair + abbreviation maps for messy prose (jay)

`extract_for_patient` returns a WoundExtraction for the PRIMARY (best-documented)
wound used in routing, plus the full `wounds` list and per-field evidence.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from . import clinical

MEAS_FIELDS = ("length_cm", "width_cm", "depth_cm")
CORE_FIELDS = ("wound_type", "stage", "location", "length_cm", "width_cm",
               "depth_cm", "drainage_type", "drainage_amount")

_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:cm)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:cm)?"
    r"(?:\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:cm)?)?", re.IGNORECASE)
_DEPTH_RE = re.compile(r"depth[:\s]*?(\d+(?:\.\d+)?)\s*cm", re.IGNORECASE)
_SOURCE_RANK = {"assessment.raw_json": 0, "assessment.narrative": 1, "note": 2}


@dataclass
class WoundExtraction:
    wound_type: Optional[str] = None
    stage: Optional[str] = None
    location: Optional[str] = None
    length_cm: Optional[float] = None
    width_cm: Optional[float] = None
    depth_cm: Optional[float] = None
    drainage_type: Optional[str] = None
    drainage_amount: Optional[str] = None
    sources: dict = field(default_factory=dict)     # field -> source label
    evidence: dict = field(default_factory=dict)    # field -> text snippet
    wounds: list = field(default_factory=list)      # all wounds (multi)
    wound_count: int = 0
    multi_wound: bool = False
    confidence: float = 0.0

    def drainage(self) -> Optional[str]:
        parts = [p for p in (self.drainage_type, self.drainage_amount) if p]
        return ", ".join(parts) if parts else None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["drainage"] = self.drainage()
        return d


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---------- field parsers ---------------------------------------------------
def _measurements(text):
    t = text.lower()
    L = re.search(r"length[:\s]+(\d+\.?\d*)\s*cm", t)
    W = re.search(r"width[:\s]+(\d+\.?\d*)\s*cm", t)
    D = re.search(r"depth[:\s]+(\d+\.?\d*)\s*cm", t)
    if L and W:
        return _f(L.group(1)), _f(W.group(1)), _f(D.group(1)) if D else None
    m = _DIM_RE.search(t)
    if m:
        depth = _f(m.group(3))
        if depth is None:
            dm = _DEPTH_RE.search(t)
            depth = _f(dm.group(1)) if dm else None
        return _f(m.group(1)), _f(m.group(2)), depth
    dm = _DEPTH_RE.search(t)
    return None, None, (_f(dm.group(1)) if dm else None)


def _wound_type(text):
    t = text.lower()
    for name, pat in clinical.WOUND_TYPE_PATTERNS:
        if re.search(pat, t):
            return name
    return None


def _stage(text):
    t = text.lower()
    m = re.search(r"stage[:\s]+(?:stage\s+)?(\d|i{1,3}v?|iv|unstageable|dti)", t)
    if m:
        return f"Stage {m.group(1).upper()}"
    if "unstageable" in t:
        return "Unstageable"
    if "deep tissue" in t or "dti" in t:
        return "Deep Tissue Injury"
    return None


def _location(text):
    m = re.search(r"location[:\s]+([A-Za-z ]+?)(?:\s*[/|.\n]|$)", text, re.I)
    if m:
        return clinical.normalize_location(m.group(1))
    m = re.search(r"\bto\s+((?:right|left|bilateral)?\s*[A-Za-z]+)\b", text, re.I)
    if m:
        return clinical.normalize_location(m.group(1))
    low = text.lower()
    for site in clinical._SITES:
        if site in low:
            return site.title()
    return None


def _drainage(text):
    t = text.lower()
    dt = next((d for d in clinical.DRAINAGE_TYPES if d in t), None)
    dt = clinical.DRAINAGE_TYPE_CANON.get(dt, dt)
    da = next((a for a in clinical.DRAINAGE_AMOUNTS if re.search(rf"\b{a}\b", t)), None)
    if not da:
        for ab, canon in clinical.DRAINAGE_AMOUNT_ABBR.items():
            if re.search(rf"\b{ab}\b", t):
                da = canon
                break
    return dt, da


# ---------- candidate building ----------------------------------------------
def _fields_from_text(text):
    l, w, d = _measurements(text)
    dt, da = _drainage(text)
    return {"wound_type": _wound_type(text), "stage": _stage(text),
            "location": _location(text), "length_cm": l, "width_cm": w,
            "depth_cm": d, "drainage_type": dt, "drainage_amount": da}


def _segments(text):
    """Split a multi-wound note into per-wound chunks at each measurement."""
    if not text:
        return []
    idxs = [m.start() for m in _DIM_RE.finditer(text)]
    if len(idxs) <= 1:
        return [text]
    bounds = [0] + idxs[1:] + [len(text)]
    return [text[bounds[i]:bounds[i + 1]] for i in range(len(idxs))]


def _raw_json(raw):
    flat, narrs = {}, []
    if not raw:
        return flat, narrs
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return flat, [str(raw)]
    if isinstance(obj, dict):
        for k in CORE_FIELDS:
            if k in obj and obj[k] is not None:
                flat[k] = obj[k]
        for sec in obj.get("sections", []) or []:
            for q in sec.get("questions", []) or []:
                a = q.get("answer")
                if isinstance(a, str) and a.strip():
                    narrs.append(a)
    return flat, narrs


def _candidate(fields, source, snippet):
    c = {k: fields.get(k) for k in CORE_FIELDS}
    c["_source"] = source
    c["_rank"] = _SOURCE_RANK.get(source, 9)
    c["_snippet"] = (snippet or "").strip()[:200]
    return c


def _gather(notes, assessments):
    cands = []
    for a in assessments:
        flat, narrs = _raw_json(a.get("raw_json", ""))
        if flat:
            flat["location"] = clinical.normalize_location(flat.get("location"))
            cands.append(_candidate(flat, "assessment.raw_json",
                                    json.dumps(flat, default=str)))
        for nar in narrs:
            for seg in _segments(nar):
                cands.append(_candidate(_fields_from_text(seg),
                                        "assessment.narrative", seg))
    for n in notes:
        txt = n.get("note_text") or ""
        for seg in _segments(txt):
            cands.append(_candidate(_fields_from_text(seg), "note", seg))
    return cands


def _same_wound(a, b):
    """Two candidates are the same wound if they share an anatomical location
    OR the same length×width. Merges a wound seen in both a note and an
    assessment, while keeping genuinely different sites separate."""
    la, lb = a.get("location"), b.get("location")
    if la and lb:
        la, lb = str(la).lower(), str(lb).lower()
        if la == lb or la in lb or lb in la:
            return True
    ma = (a.get("length_cm"), a.get("width_cm"))
    mb = (b.get("length_cm"), b.get("width_cm"))
    if ma[0] and ma[1] and ma == mb:
        return True
    return False


def _cluster(cands):
    """Union-find: group candidates that refer to the same physical wound."""
    n = len(cands)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    for i in range(n):
        for j in range(i + 1, n):
            if _same_wound(cands[i], cands[j]):
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(cands[i])
    return [_merge_cluster(g) for g in groups.values()]


def _merge_cluster(cands):
    cands = sorted(cands, key=lambda c: c["_rank"])
    merged = {k: None for k in CORE_FIELDS}
    sources, evidence = {}, {}
    for c in cands:
        for k in CORE_FIELDS:
            if merged[k] in (None, "") and c.get(k) not in (None, ""):
                merged[k] = c[k]
                sources[k] = c["_source"]
                evidence[k] = c["_snippet"]
    merged["sources"], merged["evidence"] = sources, evidence
    return merged


def _completeness(w):
    needed = ("wound_type",) + MEAS_FIELDS
    return sum(1 for k in needed if w.get(k) not in (None, "")) / len(needed)


# ---------- public entry ----------------------------------------------------
def extract_for_patient(notes, assessments, diagnoses=None):
    cands = _gather(notes or [], assessments or [])
    wounds = _cluster(cands) if cands else []
    # drop empty clusters (no meaningful field)
    wounds = [w for w in wounds if any(w.get(k) for k in CORE_FIELDS)]

    # ICD-10 authoritative type/stage backfill (ours + jay)
    icd_codes, icd_type, icd_stage = [], None, None
    if diagnoses:
        active = [d for d in diagnoses if d.get("clinical_status") == "active"
                  and clinical.is_wound_icd(d.get("icd10_code", ""))]
        icd_codes = [d.get("icd10_code") for d in active]
        icd_type = clinical.infer_type_from_icd(icd_codes)
        for d in active:
            icd_stage = _stage(d.get("icd10_description", "")) or icd_stage
            if icd_stage:
                break

    if not wounds and (icd_type or icd_stage):
        wounds = [{k: None for k in CORE_FIELDS} | {"sources": {}, "evidence": {}}]
    for w in wounds:
        if not w.get("wound_type") and icd_type:
            w["wound_type"] = icd_type
            w["sources"]["wound_type"] = "diagnosis.icd10"
            w["evidence"]["wound_type"] = ", ".join(icd_codes)
        if not w.get("stage") and icd_stage:
            w["stage"] = icd_stage
            w["sources"]["stage"] = "diagnosis.icd10"

    ex = WoundExtraction()
    if wounds:
        wounds.sort(key=_completeness, reverse=True)
        primary = wounds[0]
        for k in CORE_FIELDS:
            setattr(ex, k, primary.get(k))
        ex.sources = primary.get("sources", {})
        ex.evidence = primary.get("evidence", {})
    ex.wounds = wounds
    ex.wound_count = len(wounds)
    ex.multi_wound = len(wounds) > 1
    ex.confidence = _score(ex)
    return ex


def _score(ex):
    completeness = sum(1 for k in ("wound_type",) + MEAS_FIELDS
                       if getattr(ex, k) is not None) / 4
    drain = 1.0 if ex.drainage() else 0.0
    ranks = [_SOURCE_RANK.get(s, 9) for s in ex.sources.values()]
    rel = (1.0 - (sum(ranks) / len(ranks)) / 9) if ranks else 0.0
    conf = 0.55 * completeness + 0.20 * drain + 0.25 * rel
    if ex.multi_wound:
        conf *= 0.85
    return round(min(conf, 1.0), 3)
