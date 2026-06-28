from dataclasses import dataclass, field
from extractor import WoundData, extract_wound_data, normalize_wound_type

WOUND_ICD10_PREFIXES = (
    "L89",  # pressure ulcer
    "E10", "E11",  # diabetic
    "I83",  # venous
    "L97",  # non-pressure chronic ulcer
    "T20", "T21", "T22", "T23", "T24", "T25",  # burns
    "L02",  # abscess
    "T81",  # surgical complications
    "I70",  # arterial disease (found in real data)
)

ICD10_TO_WOUND_TYPE = {
    "L89": "pressure_ulcer",
    "E10": "diabetic_foot_ulcer",
    "E11": "diabetic_foot_ulcer",
    "I83": "venous_stasis_ulcer",
    "L97": "pressure_ulcer",
    "L02": "abscess",
    "T81": "surgical_site",
    "I70": "arterial_ulcer",
}


@dataclass
class EligibilityResult:
    patient_id: str = ""
    patient_name: str = ""
    has_medicare_b: bool = False
    has_wound_diagnosis: bool = False
    wound_icd10_codes: list[str] = field(default_factory=list)
    wound_data: WoundData | None = None
    decision: str = "reject"
    reason: str = ""
    from_cache: bool = False


def check_medicare_b(coverage: list[dict]) -> bool:
    for c in coverage:
        if c.get("payer_code") == "MCB" and c.get("effective_to") is None:
            return True
    return False


def check_wound_diagnosis(diagnoses: list[dict]) -> tuple[bool, list[str]]:
    matching = []
    for d in diagnoses:
        if d.get("clinical_status") != "active":
            continue
        code = d.get("icd10_code", "")
        if code and any(code.startswith(p) for p in WOUND_ICD10_PREFIXES):
            matching.append(code)
    return bool(matching), matching


def _infer_wound_type_from_icd10(codes: list[str]) -> str | None:
    for code in codes:
        for prefix, wtype in ICD10_TO_WOUND_TYPE.items():
            if code.startswith(prefix):
                return wtype
        # Burns T20-T25
        if code[:3] in ("T20", "T21", "T22", "T23", "T24", "T25"):
            return "burn"
    return None


def determine_eligibility(patient_data: dict) -> EligibilityResult:
    patient = patient_data["patient"]
    result = EligibilityResult(
        patient_id=patient.get("patient_id", ""),
        patient_name=f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip(),
    )

    # Step 1: Medicare B check
    result.has_medicare_b = check_medicare_b(patient_data.get("coverage", []))
    if not result.has_medicare_b:
        payer = patient.get("primary_payer_code", "unknown")
        result.decision = "reject"
        result.reason = f"No active Medicare Part B coverage (payer: {payer})"
        return result

    # Step 2: Wound diagnosis check
    result.has_wound_diagnosis, result.wound_icd10_codes = check_wound_diagnosis(
        patient_data.get("diagnoses", [])
    )
    if not result.has_wound_diagnosis:
        result.decision = "reject"
        result.reason = "No active wound-related ICD-10 diagnosis"
        return result

    # Step 3: Wound data extraction
    wound = extract_wound_data(
        patient_data.get("assessments", []),
        patient_data.get("notes", []),
    )
    result.wound_data = wound

    if wound is None:
        result.decision = "reject"
        result.reason = "Unable to extract wound documentation"
        return result

    # Fill in wound_type from ICD-10 if extraction missed it
    if not wound.wound_type and result.wound_icd10_codes:
        wound.wound_type = _infer_wound_type_from_icd10(result.wound_icd10_codes)

    # Step 4: Assess completeness
    missing = []
    if not wound.wound_type:
        missing.append("wound_type")
    if wound.length_cm is None:
        missing.append("length")
    if wound.width_cm is None:
        missing.append("width")
    if wound.drainage_amount is None:
        missing.append("drainage")

    if not missing and wound.depth_cm is not None:
        dims = f"{wound.length_cm}x{wound.width_cm}x{wound.depth_cm}cm"
        result.decision = "auto_accept"
        result.reason = f"Complete wound documentation: {wound.wound_type}, {dims}, drainage: {wound.drainage_amount}"
    elif not missing and wound.depth_cm is None:
        result.decision = "flag_for_review"
        result.reason = "Wound depth not documented; other fields complete"
    elif missing:
        result.decision = "flag_for_review"
        result.reason = f"Missing wound fields: {', '.join(missing)}"
    else:
        result.decision = "flag_for_review"
        result.reason = "Incomplete wound documentation"

    return result
