"""
Mock server replicating the documented contract: 30% random 429 with
Retry-After 1-5s, same endpoints/schemas as the real API. Used only to
validate the scheduler logic in this sandbox, which cannot reach
hackathon.prod.pulsefoundry.ai. Run the real ingest.py against the real
BASE_URL outside this sandbox -- the code is identical either way.
"""
import hashlib
import random
from datetime import datetime, timedelta

from fastapi import FastAPI, Query, Response
from fastapi.responses import JSONResponse

app = FastAPI()

FACILITIES = {101: "FA", 102: "FB", 103: "FC"}
N_PATIENTS_PER_FACILITY = 40  # smaller than real 100 for fast local testing


def stable_id(s: str) -> int:
    # Python's built-in hash() is randomized per-process (PYTHONHASHSEED) for
    # strings, which made earlier dev runs of this mock generate different
    # "id" values across server restarts -- a test-harness artifact that
    # doesn't reflect how the real API behaves (real DB primary keys are
    # stable). Use a deterministic digest instead so repeated runs here are
    # consistent, matching the real API's actual contract.
    return int(hashlib.sha256(s.encode()).hexdigest(), 16) % 100000


def maybe_rate_limit():
    if random.random() < 0.30:
        retry_after = random.randint(1, 5)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Back off and retry."},
            headers={"Retry-After": str(retry_after)},
        )
    return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/pcc/patients")
def patients(facility_id: int = Query(...), since: str = Query(None)):
    limited = maybe_rate_limit()
    if limited:
        return limited
    prefix = FACILITIES[facility_id]
    out = []
    base_id = (facility_id - 101) * N_PATIENTS_PER_FACILITY
    for i in range(1, N_PATIENTS_PER_FACILITY + 1):
        out.append({
            "id": base_id + i,
            "facility_id": facility_id,
            "patient_id": f"{prefix}-{i:03d}",
            "first_name": f"First{i}",
            "last_name": f"Last{i}",
            "birth_date": "1945-01-01",
            "gender": "Female" if i % 2 == 0 else "Male",
            "primary_payer_code": ["MCB", "MCA", "MCD", "HMO"][i % 4],
            "last_modified_at": (datetime(2026, 5, 1) + timedelta(days=i)).isoformat(),
            "is_new_admission": i % 5 == 0,
        })
    return out


@app.get("/pcc/diagnoses")
def diagnoses(patient_id: str = Query(...)):
    limited = maybe_rate_limit()
    if limited:
        return limited
    return [{
        "id": stable_id(patient_id),
        "patient_id": patient_id,
        "icd10_code": "L89.152",
        "icd10_description": "Pressure ulcer of sacral region, stage 2",
        "clinical_status": "active",
        "onset_date": "2026-04-10",
        "last_modified_at": "2026-05-17T19:13:00",
    }]


@app.get("/pcc/coverage")
def coverage(patient_id: str = Query(...)):
    limited = maybe_rate_limit()
    if limited:
        return limited
    is_mcb = stable_id(patient_id) % 3 == 0
    return [{
        "id": stable_id(patient_id) + 1,
        "patient_id": patient_id,
        "payer_name": "Medicare Part B" if is_mcb else "HMO Plan",
        "payer_code": "MCB" if is_mcb else "HMO",
        "payer_type": "Medicare B" if is_mcb else "HMO",
        "effective_from": "2020-01-01T00:00:00",
        "effective_to": None,
        "last_modified_at": "2026-05-17T19:13:00",
    }]


@app.get("/pcc/notes")
def notes(patient_id: int = Query(...), since: str = Query(None)):
    limited = maybe_rate_limit()
    if limited:
        return limited
    structured = patient_id % 2 == 0
    if structured:
        text = (
            "Wound Assessment Note\nLocation: Sacrum\nWound Type: Pressure Ulcer, Stage 2\n"
            "Length: 3.2 cm  Width: 2.1 cm  Depth: 0.4 cm\n"
            "Drainage: Moderate serosanguineous\nPeriwound: Intact skin with mild erythema\n"
            "Treatment: Foam dressing with moisture barrier"
        )
    else:
        text = (
            "Patient seen today for routine wound check. The sacral wound continues to show "
            "signs of healing, measuring approximately 2.8 by 1.9 cm with shallow depth around "
            "0.3 cm. Drainage was light and serosanguineous in nature. Periwound tissue intact."
        )
    return [{
        "id": patient_id * 10 + 1,
        "patient_id": patient_id,
        "org_id": "ORG-101",
        "pcc_note_id": 10000 + patient_id,
        "note_type": "Wound (SPN)" if structured else "Envive narrative",
        "effective_date": "2026-05-10T09:00:00",
        "note_text": text,
        "created_by": "RN Smith",
        "note_label": None,
        "sync_version": 1,
        "is_current": True,
    }]


@app.get("/pcc/assessments")
def assessments(patient_id: int = Query(...), since: str = Query(None)):
    limited = maybe_rate_limit()
    if limited:
        return limited
    import json
    raw = {
        "wound_type": "pressure_ulcer", "stage": 2, "location": "Sacrum",
        "length_cm": 3.2, "width_cm": 2.1, "depth_cm": 0.4,
        "drainage_type": "serosanguineous", "drainage_amount": "moderate",
    }
    return [{
        "id": patient_id * 10 + 2,
        "patient_id": patient_id,
        "org_id": "ORG-101",
        "pcc_assessment_id": 20000 + patient_id,
        "assessment_type": "Weekly Wound Information Sheet",
        "status": "Complete",
        "assessment_date": "2026-05-10",
        "completion_date": "2026-05-10",
        "template_id": 5,
        "assessment_type_description": "Quarterly",
        "raw_json": json.dumps(raw),
        "sync_version": 1,
        "is_current": True,
    }]