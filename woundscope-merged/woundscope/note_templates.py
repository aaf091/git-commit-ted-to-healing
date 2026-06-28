"""Note + assessment template parsers.

Authored by Aadit (team branch `aadit`, stage-2-extraction) — empirically
reverse-engineered the 4 real note templates (envive/soap/pt_seen/shorthand)
and the 2 real assessment raw_json shapes by testing against production data,
after finding the API docs example format does not occur. Integrated here
verbatim and adapted into the WoundScope pipeline via extract.py.
"""
"""
Stage 2 — Wound data extraction.

Pulls the 5 required fields (wound type, stage, location, length/width/depth,
drainage amount) out of two source types:

  - assessments.raw_json    -- already structured JSON, direct field mapping
  - progress_notes.note_text -- two sub-formats:
        * "Wound (SPN)"        -- labeled fields (Location:, Length:, etc.)
        * "Envive narrative"   -- free-text prose, fields embedded in sentences

Every extracted record carries a `source_type` and `confidence` so downstream
stages (and the biller-facing presentation) can distinguish "this came from
a structured field" from "this was inferred from prose and might be wrong."

Wound identity isn't given by the API (no wound_id field anywhere), so wounds
are grouped per patient by normalized `location` -- multiple assessments/notes
at the same location over time are treated as the same wound being tracked;
a different location is treated as a distinct wound.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Optional

DRAINAGE_LEVELS = ["none", "light", "moderate", "heavy"]

# Maps the free-text drainage descriptors seen in notes/assessments to the
# canonical 4-level scale the task asks for. Real data will likely use more
# synonyms than this; unmapped terms fall through to the raw text with a
# lower confidence flag rather than guessing a bucket silently.
DRAINAGE_SYNONYMS = {
    "none": "none", "no drainage": "none", "dry": "none",
    "minimal": "light", "min": "light", "scant": "light", "light": "light",
    "small": "light", "sm": "light", "slight": "light",
    "moderate": "moderate", "mod": "moderate", "medium": "moderate",
    "heavy": "heavy", "copious": "heavy", "large": "heavy", "lg": "heavy", "profuse": "heavy",
}

WOUND_TYPE_SYNONYMS = {
    "pressure ulcer": "pressure_ulcer", "pressure_ulcer": "pressure_ulcer",
    "decubitus": "pressure_ulcer", "decubitus ulcer": "pressure_ulcer",
    "venous ulcer": "venous_ulcer", "venous": "venous_ulcer",
    "diabetic ulcer": "diabetic_ulcer", "diabetic foot ulcer": "diabetic_ulcer",
    "arterial ulcer": "arterial_ulcer",
    "surgical wound": "surgical_wound", "surgical": "surgical_wound",
    "skin tear": "skin_tear",
}


@dataclass
class ExtractedWound:
    patient_id: int                 # internal integer id (notes/assessments key)
    source_table: str                # "assessments" | "progress_notes"
    source_record_id: int            # id of the assessments/progress_notes row
    source_type: str                 # see TEMPLATE constants below
    confidence: str                  # "high" | "medium" | "low"
    record_date: Optional[str]       # assessment_date or effective_date
    wound_index: int = 0              # 0 = first/only wound mentioned in this record,
                                       # 1 = second wound in the SAME note (pt_seen template
                                       # sometimes documents two distinct wounds in one note)
    wound_type: Optional[str] = None
    stage: Optional[int] = None
    location: Optional[str] = None
    length_cm: Optional[float] = None
    width_cm: Optional[float] = None
    depth_cm: Optional[float] = None
    drainage_amount: Optional[str] = None
    drainage_raw: Optional[str] = None     # original text, e.g. "moderate serosanguineous"
    treatment_note: Optional[str] = None   # free-text treatment mention, if present -- NOT a billing field
    flagged_for_review: bool = False
    flag_reason: Optional[str] = None
    raw_text: Optional[str] = None         # original note_text/raw_json, kept for audit/traceability


LOCATION_SYNONYMS = {
    "sacrum": "sacrum", "sacral": "sacrum",
    "coccyx": "coccyx", "tailbone": "coccyx",
    "heel": "heel", "heels": "heel",
    "ankle": "ankle", "ankles": "ankle",
    "hip": "hip", "hips": "hip",
    "elbow": "elbow", "elbows": "elbow",
    "ischium": "ischium", "ischial": "ischium",
    "trochanter": "trochanter",
    "buttock": "buttock", "buttocks": "buttock",
    "shoulder": "shoulder", "shoulders": "shoulder",
    "back": "back",
    "foot": "foot", "feet": "foot",
    "plantar": "plantar foot",
    "abdominal wall": "abdominal wall", "abdomen": "abdominal wall",
    "cervical": "cervical",
    "lower leg": "lower leg", "lowerle": "lower leg", "lowerleg": "lower leg",
    "leg": "lower leg",
    "toe": "toe", "toes": "toe",
    "knee": "knee", "knees": "knee",
}

WOUND_TYPE_SYNONYMS = {
    "pressure ulcer": "pressure_ulcer", "pressure_ulcer": "pressure_ulcer",
    "decubitus": "pressure_ulcer", "decubitus ulcer": "pressure_ulcer",
    "venous ulcer": "venous_ulcer", "venous": "venous_ulcer",
    "diabetic ulcer": "diabetic_ulcer", "diabetic foot ulcer": "diabetic_ulcer",
    "diabetic": "diabetic_ulcer",
    "arterial ulcer": "arterial_ulcer", "arterial": "arterial_ulcer",
    "surgical wound": "surgical_wound", "surgical": "surgical_wound",
    "skin tear": "skin_tear",
    "abscess": "abscess",
}


_LATERALITY_PATTERN = re.compile(r"^(right|left|bilateral|bil\.?|r|l)\.?\s+", re.IGNORECASE)
_LATERALITY_ABBREV = {"r": "right", "l": "left", "bil": "bilateral", "bil.": "bilateral"}


def normalize_location(loc: Optional[str]) -> Optional[str]:
    """Canonicalizes location strings while PRESERVING laterality, since a
    right-side and left-side wound are genuinely different wounds for a
    patient who has both -- e.g. 'Right hip' and 'Left hip' must stay
    distinct, not collapse into a single 'hip' bucket. What gets normalized
    is the body-part word itself (hip/hips -> hip) and the laterality
    prefix's spelling (R/Right -> right), so 'R hip' and 'Right hip' match
    as the same wound, but 'Right hip' and 'Left hip' do not."""
    if not loc:
        return None
    key = loc.strip().lower()
    m = _LATERALITY_PATTERN.match(key)
    laterality = None
    if m:
        raw_lat = m.group(1).rstrip(".")
        laterality = _LATERALITY_ABBREV.get(raw_lat, raw_lat)
        key = key[m.end():]
    body_part = LOCATION_SYNONYMS.get(key, key)
    return f"{laterality} {body_part}" if laterality else body_part


def normalize_wound_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = raw.strip().lower()
    # strip a trailing ", stage N" if present, e.g. "Pressure Ulcer, Stage 2"
    key = re.sub(r",?\s*stage\s*\d+", "", key).strip()
    return WOUND_TYPE_SYNONYMS.get(key, key.replace(" ", "_"))


def normalize_drainage(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    text = raw.strip().lower()
    for term, level in DRAINAGE_SYNONYMS.items():
        if re.search(rf"\b{re.escape(term)}\b", text):
            return level
    return None  # unrecognized -- caller decides how to flag this


def extract_stage(text: str) -> Optional[int]:
    m = re.search(r"stage\s*(\d)", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Path 1: structured assessments (assessments.raw_json)
#
# Real data has TWO sub-formats inside raw_json (verified against all 300
# real assessments, no other variants found):
#
#   (a) Structured section/question/answer survey -- sections named LOCATION,
#       WOUND, DRAINAGE, WOUND_BED, each containing a list of
#       {"question": ..., "answer": ...} pairs. 219/300 in the real data.
#       NOTE: this is NOT the flat {"wound_type": ..., "length_cm": ...}
#       shape the API docs showed -- that flat shape does not occur in the
#       real dataset at all, same lesson as the note-template mismatch.
#
#   (b) A single WOUND_INFO section with one free-text "Wound narrative"
#       answer in the same slash-delimited prose style as the envive note
#       template: "{type} to {location} / Measures {L} cm x {W} cm /
#       Stage: {N or N/A} / Drainage: {dtype}, {level}". 81/300 in the real
#       data -- always lower-confidence since it requires prose parsing.
# ---------------------------------------------------------------------------

_NUM = r"[\d.]+"

_ASSESSMENT_NARRATIVE = re.compile(
    rf"(?P<type>[^/]+?)\s+to\s+(?P<location>[^/]+?)\s*/\s*"
    rf"Measures\s*(?P<length>{_NUM})\s*cm\s*x\s*(?P<width>{_NUM})\s*cm\s*/\s*"
    rf"Stage:\s*(?P<stage>Stage\s*\d|N/A)\s*/\s*"
    rf"Drainage:\s*(?P<dtype>[^,]+),\s*(?P<level>\w+)",
    re.IGNORECASE,
)


def _sections_to_qa_map(data: dict) -> dict:
    """Flattens the real section/question/answer structure into a single
    {lowercased question: answer} dict for easy lookup, since the question
    text (not the section name) is what actually identifies each field."""
    qa = {}
    for section in data.get("sections", []):
        for q in section.get("questions", []):
            key = (q.get("question") or "").strip().lower()
            if key:
                qa[key] = q.get("answer")
    return qa


def _combine_location_and_laterality(location_raw: Optional[str], laterality_raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """The real data has two separate fields -- Location (e.g. "Left
    buttock", often already laterality-inclusive) and a separate
    Laterality field. These serve different purposes and most apparent
    "disagreements" are not real conflicts:

      - Laterality "N/A" means not applicable / not recorded -- there is
        nothing to conflict with, regardless of what Location says.
      - Laterality "Bilateral" is a distinct clinical signal meaning the
        underlying condition affects both sides of the body (e.g. bilateral
        pressure ulcers); it does not compete with Location's statement of
        which specific side THIS record documents. Confirmed against real
        samples: Location never says "Bilateral X" itself, and some
        Bilateral-flagged records have a midline Location ("Sacral
        region") that has no left/right concept at all -- so "Bilateral"
        is describing the condition, not contradicting the location.

    The only genuine conflict is Location stating one side (Right/Left)
    while Laterality explicitly states the OTHER side -- that combination
    really is contradictory and is the only case flagged here."""
    if not location_raw:
        return None, None
    existing_lat_match = _LATERALITY_PATTERN.match(location_raw.strip().lower())
    if existing_lat_match:
        existing_lat = _LATERALITY_ABBREV.get(
            existing_lat_match.group(1).rstrip("."), existing_lat_match.group(1).rstrip(".")
        )
        lat_normalized = (laterality_raw or "").strip().lower()
        is_real_disagreement = (
            lat_normalized in ("left", "right")
            and lat_normalized != existing_lat
        )
        if is_real_disagreement:
            return location_raw, (
                f"Location field states '{existing_lat}' but separate Laterality "
                f"field says '{laterality_raw}' -- used Location's value, flagging conflict"
            )
        return location_raw, None
    if laterality_raw and laterality_raw.strip().lower() in ("left", "right"):
        return f"{laterality_raw} {location_raw}", None
    return location_raw, None


def _parse_structured_assessment(row: dict, qa: dict) -> ExtractedWound:
    missing = []

    location_raw = qa.get("location")
    laterality_raw = qa.get("laterality")
    location, laterality_conflict = _combine_location_and_laterality(location_raw, laterality_raw)
    if not location_raw:
        missing.append("location")

    wound_type_raw = qa.get("wound type")
    if not wound_type_raw:
        missing.append("wound_type")

    stage_raw = qa.get("stage")
    stage = None
    if stage_raw and "n/a" not in stage_raw.lower():
        stage = extract_stage(stage_raw)

    def _to_float(key):
        val = qa.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    length_cm = _to_float("length (cm)")
    width_cm = _to_float("width (cm)")
    depth_cm = _to_float("depth (cm)")
    for label, val in [("length", length_cm), ("width", width_cm), ("depth", depth_cm)]:
        if val is None:
            missing.append(f"{label}_cm")

    drainage_present = (qa.get("drainage present") or "").strip().lower()
    drainage_amount = drainage_raw = None
    if drainage_present == "no":
        drainage_amount, drainage_raw = "none", "no drainage"
    else:
        amount_raw = qa.get("drainage amount")
        type_raw = qa.get("drainage type")
        if amount_raw:
            drainage_amount = normalize_drainage(amount_raw)
            drainage_raw = f"{amount_raw} {type_raw}".strip() if type_raw else amount_raw
        if drainage_amount is None:
            missing.append("drainage")

    flag_reason = (
        f"structured assessment; missing field(s): {', '.join(missing)}" if missing else None
    )
    if laterality_conflict:
        flag_reason = f"{flag_reason}; {laterality_conflict}" if flag_reason else laterality_conflict

    return ExtractedWound(
        patient_id=row["patient_id"], source_table="assessments",
        source_record_id=row["id"], source_type="structured_assessment",
        confidence="high" if not missing and not laterality_conflict else "medium",
        record_date=row.get("assessment_date"),
        wound_type=normalize_wound_type(wound_type_raw), stage=stage,
        location=normalize_location(location),
        length_cm=length_cm, width_cm=width_cm, depth_cm=depth_cm,
        drainage_amount=drainage_amount, drainage_raw=drainage_raw,
        flagged_for_review=bool(missing or laterality_conflict), flag_reason=flag_reason,
        raw_text=row.get("raw_json"),
    )


def _parse_narrative_assessment(row: dict, narrative_text: str) -> ExtractedWound:
    m = _ASSESSMENT_NARRATIVE.search(narrative_text or "")
    missing = []

    if not m:
        return ExtractedWound(
            patient_id=row["patient_id"], source_table="assessments",
            source_record_id=row["id"], source_type="narrative_assessment",
            confidence="low", record_date=row.get("assessment_date"),
            flagged_for_review=True,
            flag_reason="WOUND_INFO narrative text did not match expected pattern",
            raw_text=row.get("raw_json"),
        )

    wound_type = m.group("type").strip()
    location = m.group("location").strip()
    length_cm = float(m.group("length"))
    width_cm = float(m.group("width"))
    stage_raw = m.group("stage")
    stage = extract_stage(stage_raw) if "n/a" not in stage_raw.lower() else None
    drainage_amount = normalize_drainage(m.group("level"))
    drainage_raw = f"{m.group('level')} {m.group('dtype').strip()}"
    if drainage_amount is None:
        missing.append(f"drainage (unrecognized: {m.group('level')!r})")

    # This narrative format never reports depth -- same structural gap as
    # the envive note template, flagged as a template property, not a miss.
    missing.append("depth (not reported in this assessment narrative format)")

    flag_reason = f"narrative assessment (WOUND_INFO); missing field(s): {', '.join(missing)}"

    return ExtractedWound(
        patient_id=row["patient_id"], source_table="assessments",
        source_record_id=row["id"], source_type="narrative_assessment",
        confidence="medium", record_date=row.get("assessment_date"),
        wound_type=normalize_wound_type(wound_type), stage=stage,
        location=normalize_location(location),
        length_cm=length_cm, width_cm=width_cm, depth_cm=None,
        drainage_amount=drainage_amount, drainage_raw=drainage_raw,
        flagged_for_review=True, flag_reason=flag_reason,
        raw_text=row.get("raw_json"),
    )


def extract_from_assessment(row: dict) -> ExtractedWound:
    raw = row.get("raw_json")
    try:
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return ExtractedWound(
            patient_id=row["patient_id"], source_table="assessments",
            source_record_id=row["id"], source_type="structured_assessment",
            confidence="low", record_date=row.get("assessment_date"),
            flagged_for_review=True, flag_reason="raw_json failed to parse",
            raw_text=raw,
        )

    section_names = {s.get("sectionName") for s in data.get("sections", [])}

    if section_names == {"WOUND_INFO"}:
        qa = _sections_to_qa_map(data)
        narrative_text = qa.get("wound narrative", "")
        return _parse_narrative_assessment(row, narrative_text)

    if {"LOCATION", "WOUND", "DRAINAGE"}.issubset(section_names):
        qa = _sections_to_qa_map(data)
        return _parse_structured_assessment(row, qa)

    # Unknown section layout -- never silently drop, flag for review instead
    return ExtractedWound(
        patient_id=row["patient_id"], source_table="assessments",
        source_record_id=row["id"], source_type="unrecognized_assessment_format",
        confidence="low", record_date=row.get("assessment_date"),
        flagged_for_review=True,
        flag_reason=f"unrecognized section layout: {sorted(section_names)}",
        raw_text=raw,
    )



# ---------------------------------------------------------------------------
# Path 2: progress_notes.note_text -- 4 real templates observed in production
# data, detected by structural signature in the text itself, NOT by the
# note_type field (note_type is just a label and does not correlate with
# which template a given note actually uses -- all 4 templates appear under
# multiple note_type values in the real data).
# ---------------------------------------------------------------------------

TEMPLATE_ENVIVE = "envive"           # "*Envive Care Conference Review..." / "Wound Status: ... / Measures ... / Stage: ..."
TEMPLATE_SOAP = "soap"               # "Subjective: ... Objective: ... Assessment: ... Plan: ..."
TEMPLATE_PT_SEEN = "pt_seen"         # "Pt seen for wound eval. {type} {location} measures aprx {L} x {W}cm, depth {D}cm." -- may describe 2 wounds
TEMPLATE_SHORTHAND = "shorthand"     # "Wound note - {location}. Meas {L}x{W}x{D}cm. ..."

def detect_template(text: str) -> str:
    if "Envive Care Conference" in text:
        return TEMPLATE_ENVIVE
    if "Subjective:" in text:
        return TEMPLATE_SOAP
    if text.strip().lower().startswith("pt seen for wound eval"):
        return TEMPLATE_PT_SEEN
    if text.strip().lower().startswith("wound note -"):
        return TEMPLATE_SHORTHAND
    return "unknown"


_LOCATION_KEYWORDS = sorted(LOCATION_SYNONYMS.keys(), key=len, reverse=True)
_WOUND_TYPE_KEYWORDS = sorted(WOUND_TYPE_SYNONYMS.keys(), key=len, reverse=True)


_LATERALITY_WORD = r"(?:right|left|bilateral|bil\.?|r|l)\.?"


def _find_location(text: str) -> Optional[str]:
    """Finds a location keyword in free text and, if a laterality word
    (Right/Left/R/L/Bilateral) immediately precedes it, includes that in
    the returned phrase so normalize_location can preserve it -- a bare
    keyword match alone would silently drop which side the wound is on."""
    lower = text.lower()
    for kw in _LOCATION_KEYWORDS:
        idx = lower.find(kw)
        if idx == -1:
            continue
        prefix = lower[:idx]
        m = re.search(rf"\b{_LATERALITY_WORD}\s*$", prefix)
        if m:
            return f"{m.group(0).strip()} {kw}"
        return kw
    return None


def _find_wound_type(text: str) -> Optional[str]:
    lower = text.lower()
    for kw in _WOUND_TYPE_KEYWORDS:
        if kw in lower:
            return kw
    return None


def _dedupe_repeated_word(text: str) -> str:
    # The SOAP template sometimes repeats the wound-type word, e.g.
    # "Diabetic diabetic Right plantar" or "Abscess abscess Right cervical".
    # Collapse an immediate case-insensitive word repeat into one occurrence
    # so downstream type/location parsing isn't confused by the duplicate.
    return re.sub(r"\b(\w+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)


def _drainage_amount_from_words(*phrases: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    for phrase in phrases:
        if not phrase:
            continue
        amt = normalize_drainage(phrase)
        if amt:
            return amt, phrase
    # nothing recognized but something was present -- return the first non-empty raw phrase
    raw = next((p for p in phrases if p), None)
    return None, raw


# --- Template: Envive Care Conference Review ---
# "Wound Status: {type} to {location} / Measures {L} cm x {W} cm / Stage: {N or N/A}"
# "Drainage present - {drainage_type}, {level}. {odor phrase}. Treatment: {text}"
# NOTE: this template never reports depth -- that's a structural gap in the
# template itself, not a parse failure, and is flagged as such rather than
# silently leaving depth null with no explanation.

_ENVIVE_STATUS = re.compile(
    rf"Wound Status:\s*(?P<type>[^/]+?)\s+to\s+(?P<location>[^/]+?)\s*/\s*"
    rf"Measures\s*(?P<length>{_NUM})\s*cm\s*x\s*(?P<width>{_NUM})\s*cm\s*/\s*"
    rf"Stage:\s*(?P<stage>Stage\s*\d|N/A)",
    re.IGNORECASE,
)
_ENVIVE_DRAINAGE = re.compile(
    r"Drainage present\s*-\s*(?P<dtype>[^,]+),\s*(?P<level>\w+)", re.IGNORECASE
)
_ENVIVE_NO_DRAINAGE = re.compile(r"No drainage", re.IGNORECASE)
_ENVIVE_TREATMENT = re.compile(r"Treatment:\s*(.+?)(?:$|\.\s*$)", re.IGNORECASE)


def _parse_envive(row: dict) -> ExtractedWound:
    text = row["note_text"] or ""
    m = _ENVIVE_STATUS.search(text)
    missing = []
    wound_type = location = stage = length_cm = width_cm = None

    if m:
        wound_type = m.group("type").strip()
        location = m.group("location").strip()
        length_cm = float(m.group("length"))
        width_cm = float(m.group("width"))
        stage_raw = m.group("stage")
        stage = extract_stage(stage_raw) if stage_raw and "n/a" not in stage_raw.lower() else None
    else:
        missing.append("wound_status_line")

    dm = _ENVIVE_DRAINAGE.search(text)
    if dm:
        drainage_amount, drainage_raw = _drainage_amount_from_words(dm.group("level"))
        if drainage_raw and dm.group("dtype"):
            drainage_raw = f"{dm.group('level')} {dm.group('dtype').strip()}"
    elif _ENVIVE_NO_DRAINAGE.search(text):
        drainage_amount, drainage_raw = "none", "no drainage"
    else:
        drainage_amount, drainage_raw = None, None
        missing.append("drainage")

    tm = _ENVIVE_TREATMENT.search(text)
    treatment = tm.group(1).strip() if tm else None

    # depth is structurally absent from this template -- always note it,
    # distinct from "we tried to find it and failed"
    missing.append("depth (not reported in this note template)")

    flag_reason = f"envive template; missing field(s): {', '.join(missing)}"

    return ExtractedWound(
        patient_id=row["patient_id"], source_table="progress_notes",
        source_record_id=row["id"], source_type=f"structured_note:{TEMPLATE_ENVIVE}",
        confidence="medium" if m else "low",
        record_date=row.get("effective_date"),
        wound_type=normalize_wound_type(wound_type), stage=stage,
        location=normalize_location(location),
        length_cm=length_cm, width_cm=width_cm, depth_cm=None,
        drainage_amount=drainage_amount, drainage_raw=drainage_raw,
        treatment_note=treatment,
        flagged_for_review=True, flag_reason=flag_reason,
        raw_text=text,
    )


# --- Template: SOAP-style note ---
# "Objective: ... {Type} {type repeated} {location} measures {L} cm x {W} cm x {D} cm."
# "Drainage: {level}." "Odor: {present/none}, {descriptor}"

_SOAP_MEASURE = re.compile(
    rf"measures\s*(?P<length>{_NUM})\s*cm\s*x\s*(?P<width>{_NUM})\s*cm\s*x\s*(?P<depth>{_NUM})\s*cm",
    re.IGNORECASE,
)
_SOAP_TYPE_LOCATION = re.compile(
    r"Objective:.*?Wound assessment performed\.\s*(?P<rest>.+?)\s+measures", re.IGNORECASE | re.DOTALL
)
_SOAP_DRAINAGE = re.compile(r"Drainage:\s*(\w+)", re.IGNORECASE)


def _parse_soap_type_and_location(rest: str) -> tuple[Optional[str], Optional[str]]:
    # `rest` is something like "Diabetic diabetic Right plantar" after the
    # duplicate-word collapse -> "Diabetic Right plantar". The wound type is
    # the leading clinical term; the location is whatever location keyword
    # appears in the remainder.
    rest = _dedupe_repeated_word(rest)
    wtype = _find_wound_type(rest)
    loc = _find_location(rest)
    return wtype, loc


def _parse_soap(row: dict) -> ExtractedWound:
    text = row["note_text"] or ""
    missing = []

    tl = _SOAP_TYPE_LOCATION.search(text)
    wound_type = location = None
    if tl:
        wound_type, location = _parse_soap_type_and_location(tl.group("rest"))
    if not wound_type:
        missing.append("wound_type")
    if not location:
        missing.append("location")

    mm = _SOAP_MEASURE.search(text)
    length_cm = width_cm = depth_cm = None
    if mm:
        length_cm, width_cm, depth_cm = (float(mm.group(g)) for g in ("length", "width", "depth"))
    else:
        missing.append("measurements")

    dm = _SOAP_DRAINAGE.search(text)
    drainage_amount = drainage_raw = None
    if dm:
        drainage_raw = dm.group(1)
        drainage_amount = normalize_drainage(drainage_raw)
        if drainage_amount is None:
            missing.append(f"drainage (unrecognized: {drainage_raw!r})")
    else:
        missing.append("drainage")

    stage = extract_stage(text)  # SOAP template doesn't appear to report stage; usually None

    flag_reason = (
        f"soap template; missing field(s): {', '.join(missing)}" if missing
        else "soap template; all required fields parsed"
    )

    return ExtractedWound(
        patient_id=row["patient_id"], source_table="progress_notes",
        source_record_id=row["id"], source_type=f"structured_note:{TEMPLATE_SOAP}",
        confidence="high" if not missing else "medium",
        record_date=row.get("effective_date"),
        wound_type=normalize_wound_type(wound_type), stage=stage,
        location=normalize_location(location),
        length_cm=length_cm, width_cm=width_cm, depth_cm=depth_cm,
        drainage_amount=drainage_amount, drainage_raw=drainage_raw,
        flagged_for_review=bool(missing), flag_reason=flag_reason if missing else None,
        raw_text=text,
    )


# --- Template: "Pt seen for wound eval" ---
# "{type} {location} measures aprx {L} x {W}cm, depth {D}cm."
# Sometimes followed by a SECOND wound in the same note:
# "{location2} wound also eval - {site} {L2}x{W2}, {D2}cm deep, {drainage}"
# This template is the one place a single note legitimately describes two
# distinct wounds -- handled by returning a list, not a single record.

_PT_SEEN_FIRST = re.compile(
    rf"Pt seen for wound eval\.\s*(?P<rest>.+?)\s+measures\s*aprx\s*"
    rf"(?P<length>{_NUM})\s*x\s*(?P<width>{_NUM})\s*cm,?\s*depth\s*(?P<depth>{_NUM})\s*cm",
    re.IGNORECASE,
)
_PT_SEEN_DRAINAGE_FIRST = re.compile(
    r"cm\.\s*(?P<level>\w+)\s+drainage\s+(?P<dtype>\w+)", re.IGNORECASE
)
_PT_SEEN_SECOND = re.compile(
    rf"(?P<location_label>[\w\s]+?)\s+wound also eval\s*-\s*(?P<site>[\w\s.]+?)\s+"
    rf"(?P<length>{_NUM})\s*x\s*(?P<width>{_NUM}),?\s*(?P<depth>{_NUM})\s*cm\s*deep,?\s*"
    rf"(?P<drainage>[\w\s]+?)\.\s",
    re.IGNORECASE,
)


def _parse_pt_seen(row: dict) -> list[ExtractedWound]:
    text = row["note_text"] or ""
    results = []
    missing_first = []

    m1 = _PT_SEEN_FIRST.search(text)
    if m1:
        wound_type, location = _parse_soap_type_and_location(m1.group("rest"))
        length_cm, width_cm, depth_cm = (float(m1.group(g)) for g in ("length", "width", "depth"))
    else:
        wound_type = location = None
        length_cm = width_cm = depth_cm = None
        missing_first.append("wound_status_line")

    dm1 = _PT_SEEN_DRAINAGE_FIRST.search(text)
    drainage_amount1 = drainage_raw1 = None
    if dm1:
        drainage_raw1 = f"{dm1.group('level')} {dm1.group('dtype')}"
        drainage_amount1 = normalize_drainage(dm1.group("level"))
    if drainage_amount1 is None:
        missing_first.append("drainage")
    if not wound_type:
        missing_first.append("wound_type")
    if not location:
        missing_first.append("location")

    flag1 = f"pt_seen template; missing field(s): {', '.join(missing_first)}" if missing_first else None

    results.append(ExtractedWound(
        patient_id=row["patient_id"], source_table="progress_notes",
        source_record_id=row["id"], source_type=f"structured_note:{TEMPLATE_PT_SEEN}",
        confidence="high" if not missing_first else "medium",
        record_date=row.get("effective_date"), wound_index=0,
        wound_type=normalize_wound_type(wound_type), stage=None,
        location=normalize_location(location),
        length_cm=length_cm, width_cm=width_cm, depth_cm=depth_cm,
        drainage_amount=drainage_amount1, drainage_raw=drainage_raw1,
        flagged_for_review=bool(missing_first), flag_reason=flag1,
        raw_text=text,
    ))

    m2 = _PT_SEEN_SECOND.search(text)
    if m2:
        location2 = _find_location(m2.group("site")) or _find_location(m2.group("location_label"))
        length2, width2, depth2 = (float(m2.group(g)) for g in ("length", "width", "depth"))
        drainage_amount2 = normalize_drainage(m2.group("drainage"))
        missing_second = []
        if not location2:
            missing_second.append("location")
        if drainage_amount2 is None:
            missing_second.append(f"drainage (unrecognized: {m2.group('drainage')!r})")
        # The second wound mention is typically terser than the first and
        # doesn't restate a wound type -- fall back to the first wound's
        # type only if explicitly the same anatomical region context;
        # otherwise leave null rather than assuming.
        flag2 = (
            f"pt_seen template (second wound in note); missing field(s): {', '.join(missing_second)}"
            if missing_second else
            "pt_seen template (second wound documented in same note); wound_type not restated for this wound"
        )
        results.append(ExtractedWound(
            patient_id=row["patient_id"], source_table="progress_notes",
            source_record_id=row["id"], source_type=f"structured_note:{TEMPLATE_PT_SEEN}",
            confidence="medium",
            record_date=row.get("effective_date"), wound_index=1,
            wound_type=None, stage=None,
            location=normalize_location(location2),
            length_cm=length2, width_cm=width2, depth_cm=depth2,
            drainage_amount=drainage_amount2, drainage_raw=m2.group("drainage").strip(),
            flagged_for_review=True, flag_reason=flag2,
            raw_text=text,
        ))

    return results


# --- Template: terse shorthand ---
# "Wound note - {location}. Meas {L}x{W}x{D}cm. {level} {dtype} drainage, odor {present/none}.
#  Wound bed {gran}% gran, {slough}% slough..."
# No explicit wound type is stated in this template at all -- relies on
# diagnosis fallback every time.

_SHORTHAND_LOCATION = re.compile(r"Wound note\s*-\s*([\w\s.]+?)\.", re.IGNORECASE)
_SHORTHAND_MEASURE = re.compile(
    rf"Meas\.?\s*(?P<length>{_NUM})\s*x\s*(?P<width>{_NUM})\s*x\s*(?P<depth>{_NUM})\s*cm", re.IGNORECASE
)
_SHORTHAND_DRAINAGE = re.compile(r"(\w+)\s+\w*\s*drainage", re.IGNORECASE)


def _parse_shorthand(row: dict, diagnosis_hint: Optional[str] = None) -> ExtractedWound:
    text = row["note_text"] or ""
    missing = []

    lm = _SHORTHAND_LOCATION.search(text)
    location_raw = lm.group(1).strip() if lm else None
    location = _find_location(location_raw) if location_raw else None
    if not location:
        # the raw label (e.g. "Rightlowerle") may be a mashed-together
        # abbreviation our keyword list won't catch -- keep the raw text
        # rather than silently dropping it, but still flag it as unresolved
        location = location_raw
        if not location:
            missing.append("location")

    mm = _SHORTHAND_MEASURE.search(text)
    length_cm = width_cm = depth_cm = None
    if mm:
        length_cm, width_cm, depth_cm = (float(mm.group(g)) for g in ("length", "width", "depth"))
    else:
        missing.append("measurements")

    dm = _SHORTHAND_DRAINAGE.search(text)
    drainage_amount = drainage_raw = None
    if dm:
        drainage_raw = dm.group(0)
        drainage_amount = normalize_drainage(dm.group(1))
    if drainage_amount is None:
        missing.append("drainage")

    wound_type = None
    wound_type_source = None
    if diagnosis_hint:
        wound_type = _find_wound_type(diagnosis_hint)
        if wound_type:
            wound_type_source = "diagnosis_fallback"
    if not wound_type:
        missing.append("wound_type")

    flag_reason = f"shorthand template; missing/uncertain field(s): {', '.join(missing)}" if missing else \
        "shorthand template; all fields resolved"
    if wound_type_source == "diagnosis_fallback":
        flag_reason += "; wound_type taken from diagnosis record, not the note text"

    return ExtractedWound(
        patient_id=row["patient_id"], source_table="progress_notes",
        source_record_id=row["id"], source_type=f"structured_note:{TEMPLATE_SHORTHAND}",
        confidence="medium" if not missing else "low",
        record_date=row.get("effective_date"),
        wound_type=normalize_wound_type(wound_type) if wound_type else None,
        stage=extract_stage(text), location=normalize_location(location),
        length_cm=length_cm, width_cm=width_cm, depth_cm=depth_cm,
        drainage_amount=drainage_amount, drainage_raw=drainage_raw,
        flagged_for_review=True, flag_reason=flag_reason,
        raw_text=text,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def extract_from_note(row: dict, diagnosis_hint: Optional[str] = None) -> list[ExtractedWound]:
    """Returns a LIST, not a single record -- the pt_seen template can
    legitimately describe two distinct wounds in one note. Every other
    template returns a single-element list."""
    text = row.get("note_text") or ""
    template = detect_template(text)

    if template == TEMPLATE_ENVIVE:
        return [_parse_envive(row)]
    if template == TEMPLATE_SOAP:
        return [_parse_soap(row)]
    if template == TEMPLATE_PT_SEEN:
        return _parse_pt_seen(row)
    if template == TEMPLATE_SHORTHAND:
        return [_parse_shorthand(row, diagnosis_hint=diagnosis_hint)]

    # Defensive fallback for any future/unseen format -- never silently
    # drop a note. Flag it clearly as unparseable rather than guessing.
    return [ExtractedWound(
        patient_id=row["patient_id"], source_table="progress_notes",
        source_record_id=row["id"], source_type="unrecognized_template",
        confidence="low", record_date=row.get("effective_date"),
        flagged_for_review=True,
        flag_reason="note text did not match any known template signature",
        raw_text=text,
    )]