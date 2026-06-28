import json
import re
from dataclasses import dataclass, field


@dataclass
class WoundData:
    wound_type: str | None = None
    stage: str | None = None
    location: str | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    depth_cm: float | None = None
    drainage_amount: str | None = None
    drainage_type: str | None = None
    source: str = ""
    confidence: str = "low"


WOUND_TYPE_MAP = {
    "pressure ulcer": "pressure_ulcer",
    "pressure": "pressure_ulcer",
    "pu": "pressure_ulcer",
    "diabetic foot ulcer": "diabetic_foot_ulcer",
    "diabetic foot": "diabetic_foot_ulcer",
    "diabetic": "diabetic_foot_ulcer",
    "dfu": "diabetic_foot_ulcer",
    "venous stasis": "venous_stasis_ulcer",
    "venous": "venous_stasis_ulcer",
    "vsu": "venous_stasis_ulcer",
    "arterial": "arterial_ulcer",
    "burn": "burn",
    "abscess": "abscess",
    "surgical site": "surgical_site",
    "surgical": "surgical_site",
}

DRAINAGE_AMOUNT_MAP = {
    "moderate": "moderate",
    "mod": "moderate",
    "light": "light",
    "lt": "light",
    "slight": "light",
    "scant": "light",
    "min": "light",
    "minimal": "light",
    "heavy": "heavy",
    "hvy": "heavy",
    "lg": "heavy",
    "none": "none",
    "no": "none",
    "no drainage": "none",
}

_LOCATION_FIXES = {
    "lowerle": "lower leg",
    "lowerleg": "lower leg",
    "lowerex": "lower extremity",
    "lowerext": "lower extremity",
    "upperarm": "upper arm",
    "upperex": "upper extremity",
    "wal": "wall",
    "buttoc": "buttock",
    "plantar": "plantar",
}


def normalize_wound_type(raw: str | None) -> str | None:
    if not raw:
        return None
    lowered = raw.strip().lower()
    for key, val in WOUND_TYPE_MAP.items():
        if key in lowered:
            return val
    return None


def normalize_drainage_amount(raw: str | None) -> str | None:
    if not raw:
        return None
    lowered = raw.strip().lower()
    return DRAINAGE_AMOUNT_MAP.get(lowered)


def normalize_location(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    # Insert space before uppercase letters that follow lowercase
    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
    # Fix smashed/truncated location parts
    lower = cleaned.lower()
    for fragment, replacement in _LOCATION_FIXES.items():
        if lower.endswith(fragment):
            prefix = cleaned[: len(cleaned) - len(fragment)]
            cleaned = prefix + replacement
            break
        if fragment in lower:
            cleaned = re.sub(re.escape(fragment), replacement, cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_answer(sections: list[dict], section_name: str, question: str) -> str | None:
    for sec in sections:
        if sec.get("sectionName") == section_name:
            for q in sec.get("questions", []):
                if q.get("question") == question:
                    ans = q.get("answer")
                    if ans and str(ans).strip() and str(ans).strip() != "N/A":
                        return str(ans).strip()
    return None


def extract_from_assessment(assessment: dict) -> WoundData | None:
    raw = assessment.get("raw_json")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return None

    sections = data.get("sections", [])
    if not sections:
        return None

    section_names = {s.get("sectionName") for s in sections}

    # Format A: structured sections (WOUND, LOCATION, DRAINAGE)
    if "WOUND" in section_names:
        wound = WoundData(
            wound_type=normalize_wound_type(_get_answer(sections, "WOUND", "Wound Type")),
            stage=_get_answer(sections, "WOUND", "Stage"),
            location=_get_answer(sections, "LOCATION", "Location"),
            length_cm=_parse_float(_get_answer(sections, "WOUND", "Length (cm)")),
            width_cm=_parse_float(_get_answer(sections, "WOUND", "Width (cm)")),
            depth_cm=_parse_float(_get_answer(sections, "WOUND", "Depth (cm)")),
            drainage_amount=normalize_drainage_amount(_get_answer(sections, "DRAINAGE", "Drainage Amount")),
            drainage_type=(_get_answer(sections, "DRAINAGE", "Drainage Type") or "").lower() or None,
            source="assessment_structured",
            confidence="high",
        )
        return wound

    # Format B: narrative (WOUND_INFO)
    if "WOUND_INFO" in section_names:
        narrative = _get_answer(sections, "WOUND_INFO", "Wound narrative")
        if not narrative:
            return None
        return _parse_narrative(narrative, source="assessment_narrative")

    return None


def _parse_narrative(text: str, source: str = "assessment_narrative") -> WoundData | None:
    wound = WoundData(source=source, confidence="medium")

    # Pattern: "WoundType to Location / Measures L cm x W cm / Stage: X / Drainage: type, amount"
    type_loc = re.search(r"^(.+?)\s+to\s+(.+?)\s*/", text)
    if type_loc:
        wound.wound_type = normalize_wound_type(type_loc.group(1))
        wound.location = type_loc.group(2).strip()

    measures = re.search(r"Measures\s+([\d.]+)\s*cm\s*x\s*([\d.]+)\s*cm", text)
    if measures:
        wound.length_cm = _parse_float(measures.group(1))
        wound.width_cm = _parse_float(measures.group(2))

    stage_m = re.search(r"Stage:\s*(?:Stage\s+)?(\S+)", text)
    if stage_m and stage_m.group(1) != "N/A":
        wound.stage = stage_m.group(1)

    drainage_m = re.search(r"Drainage:\s*(\w+),\s*(\w+)", text)
    if drainage_m:
        wound.drainage_type = drainage_m.group(1).lower()
        wound.drainage_amount = normalize_drainage_amount(drainage_m.group(2))

    # Also check for "Drainage present - type, amount"
    if not drainage_m:
        drainage_m2 = re.search(r"[Dd]rainage present\s*-\s*(\w+),\s*(\w+)", text)
        if drainage_m2:
            wound.drainage_type = drainage_m2.group(1).lower()
            wound.drainage_amount = normalize_drainage_amount(drainage_m2.group(2))

    return wound


def detect_note_format(note_text: str) -> str:
    if not note_text:
        return "unknown"
    if note_text.startswith("*Envive") or "Wound Status:" in note_text:
        return "envive"
    if "Subjective:" in note_text or "Objective:" in note_text:
        return "soap"
    if re.search(r"Meas\s+[\d.]+x[\d.]+", note_text):
        return "prose"
    if "measures aprx" in note_text.lower():
        return "multi_wound"
    return "unknown"


def extract_from_note_soap(note_text: str) -> WoundData | None:
    wound = WoundData(source="note_soap", confidence="high")

    measures = re.search(
        r"(?:Stage\s+(\d+)\s+)?(.+?)\s+((?:Left|Right|Bilateral|Sacr|Coccyx|Abdomin)\S*(?:\s+\w+)*?)\s+"
        r"measures\s+([\d.]+)\s*cm\s*x\s*([\d.]+)\s*cm(?:\s*x\s*([\d.]+)\s*cm)?",
        note_text, re.IGNORECASE
    )
    if measures:
        if measures.group(1):
            wound.stage = measures.group(1)
        raw_type = measures.group(2).strip()
        # Remove duplicates like "Burn burn" or "Abscess abscess"
        words = raw_type.split()
        if len(words) >= 2 and words[0].lower() == words[1].lower():
            raw_type = words[0]
        wound.wound_type = normalize_wound_type(raw_type)
        wound.location = measures.group(3).strip()
        wound.length_cm = _parse_float(measures.group(4))
        wound.width_cm = _parse_float(measures.group(5))
        wound.depth_cm = _parse_float(measures.group(6))

    drainage = re.search(r"Drainage:\s*(\w+)", note_text, re.IGNORECASE)
    if drainage:
        wound.drainage_amount = normalize_drainage_amount(drainage.group(1))

    if wound.length_cm is None:
        return None
    if wound.depth_cm is None:
        wound.confidence = "medium"
    return wound


def extract_from_note_prose(note_text: str) -> WoundData | None:
    wound = WoundData(source="note_prose", confidence="high")

    loc_m = re.search(r"Wound note\s*-\s*(\S+)\.", note_text)
    if loc_m:
        wound.location = normalize_location(loc_m.group(1))

    meas = re.search(r"Meas\s+([\d.]+)x([\d.]+)x([\d.]+)cm", note_text)
    if meas:
        wound.length_cm = _parse_float(meas.group(1))
        wound.width_cm = _parse_float(meas.group(2))
        wound.depth_cm = _parse_float(meas.group(3))
    else:
        return None

    # Drainage: "Mod serosang", "None serosang", "Heavy serosang", "Lt serosang"
    drain_m = re.search(r"(Mod|Heavy|Light|Hvy|Lt|Min|None|No)\s+serosang", note_text, re.IGNORECASE)
    if drain_m:
        wound.drainage_amount = normalize_drainage_amount(drain_m.group(1))
        wound.drainage_type = "serosanguineous"
    else:
        # Try other drainage patterns
        drain_m2 = re.search(r"(moderate|heavy|light|none|minimal)\s+\w*drain", note_text, re.IGNORECASE)
        if drain_m2:
            wound.drainage_amount = normalize_drainage_amount(drain_m2.group(1))

    return wound


def extract_from_note_envive(note_text: str) -> WoundData | None:
    wound = WoundData(source="note_envive", confidence="medium")

    # "Wound Status: Type to Location / Measures L cm x W cm / Stage: X"
    status = re.search(r"Wound Status:\s*(.+?)\s+to\s+(.+?)\s*/\s*Measures\s+([\d.]+)\s*cm\s*x\s*([\d.]+)\s*cm", note_text)
    if status:
        wound.wound_type = normalize_wound_type(status.group(1))
        wound.location = status.group(2).strip()
        wound.length_cm = _parse_float(status.group(3))
        wound.width_cm = _parse_float(status.group(4))

    stage_m = re.search(r"Stage:\s*(?:Stage\s+)?(\S+)", note_text)
    if stage_m and stage_m.group(1) != "N/A":
        wound.stage = stage_m.group(1)

    # "Drainage present - type, amount."
    drainage = re.search(r"[Dd]rainage present\s*-\s*(\w+),\s*(\w+)", note_text)
    if drainage:
        wound.drainage_type = drainage.group(1).lower()
        wound.drainage_amount = normalize_drainage_amount(drainage.group(2))

    if wound.length_cm is None:
        return None
    return wound


def extract_from_note_multi_wound(note_text: str) -> WoundData | None:
    wound = WoundData(source="note_multi_wound", confidence="high")

    # Primary wound: "Type Location measures aprx L x Wcm, depth Dcm"
    primary = re.search(
        r"(\w[\w\s]*?)\s+((?:Left|Right)\s*\w[\w\s]*?)\s+measures\s+aprx\s+([\d.]+)\s*x\s*([\d.]+)cm,\s*depth\s+([\d.]+)cm",
        note_text, re.IGNORECASE
    )
    if primary:
        wound.wound_type = normalize_wound_type(primary.group(1))
        wound.location = primary.group(2).strip()
        wound.length_cm = _parse_float(primary.group(3))
        wound.width_cm = _parse_float(primary.group(4))
        wound.depth_cm = _parse_float(primary.group(5))

    drain_m = re.search(r"(Min|Mod|Heavy|Lt|Light|None)\s+drainage\s+(\w+)", note_text, re.IGNORECASE)
    if drain_m:
        wound.drainage_amount = normalize_drainage_amount(drain_m.group(1))
        wound.drainage_type = drain_m.group(2).lower()

    if wound.length_cm is None:
        return None
    return wound


def extract_wound_data(assessments: list[dict], notes: list[dict]) -> WoundData | None:
    # Try assessments first (most recent)
    sorted_assessments = sorted(
        assessments,
        key=lambda a: a.get("assessment_date") or "",
        reverse=True,
    )
    for assessment in sorted_assessments:
        result = extract_from_assessment(assessment)
        if result and result.length_cm is not None:
            return result

    # Fall back to notes (most recent)
    sorted_notes = sorted(
        notes,
        key=lambda n: n.get("effective_date") or "",
        reverse=True,
    )
    for note in sorted_notes:
        text = note.get("note_text")
        if not text:
            continue
        fmt = detect_note_format(text)
        extractors = {
            "soap": extract_from_note_soap,
            "prose": extract_from_note_prose,
            "envive": extract_from_note_envive,
            "multi_wound": extract_from_note_multi_wound,
        }
        extractor = extractors.get(fmt)
        if extractor:
            result = extractor(text)
            if result and result.length_cm is not None:
                return result

    return None
