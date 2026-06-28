import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE_URL = "https://hackathon.prod.pulsefoundry.ai"
MAX_RETRIES = 3
DATA_DIR = Path(__file__).parent / "data" / "raw"

logger = logging.getLogger(__name__)

_session = requests.Session()


def _request_with_retry(endpoint: str, params: dict) -> list[dict] | None:
    url = BASE_URL + endpoint
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = _session.get(url, params=params, timeout=10)
        except requests.RequestException as e:
            logger.warning("Network error on %s attempt %d: %s", endpoint, attempt + 1, e)
            if attempt < MAX_RETRIES:
                time.sleep(2 * (2 ** attempt))
                continue
            return None

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2))
            wait = retry_after * (2 ** attempt)
            logger.info("429 on %s, attempt %d, waiting %ds", endpoint, attempt + 1, wait)
            if attempt < MAX_RETRIES:
                time.sleep(wait)
                continue
            logger.error("Max retries exceeded for %s %s", endpoint, params)
            return None

        logger.error("HTTP %d on %s: %s", resp.status_code, endpoint, resp.text[:200])
        return None

    return None


def get_patients(facility_id: int, since: str | None = None) -> list[dict]:
    params = {"facility_id": facility_id}
    if since:
        params["since"] = since
    result = _request_with_retry("/pcc/patients", params)
    return result or []


def get_diagnoses(patient_id: str) -> list[dict]:
    result = _request_with_retry("/pcc/diagnoses", {"patient_id": patient_id})
    return result or []


def get_coverage(patient_id: str) -> list[dict]:
    result = _request_with_retry("/pcc/coverage", {"patient_id": patient_id})
    return result or []


def get_notes(patient_int_id: int) -> list[dict]:
    result = _request_with_retry("/pcc/notes", {"patient_id": patient_int_id})
    return result or []


def get_assessments(patient_int_id: int) -> list[dict]:
    result = _request_with_retry("/pcc/assessments", {"patient_id": patient_int_id})
    return result or []


def load_cached_patient(patient_id: str) -> dict | None:
    path = DATA_DIR / patient_id / "_raw.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def fetch_full_patient(patient: dict) -> dict:
    pid_str = patient["patient_id"]
    pid_int = patient["id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_diag = pool.submit(get_diagnoses, pid_str)
        f_cov = pool.submit(get_coverage, pid_str)
        f_notes = pool.submit(get_notes, pid_int)
        f_assess = pool.submit(get_assessments, pid_int)
    return {
        "patient": patient,
        "diagnoses": f_diag.result(),
        "coverage": f_cov.result(),
        "notes": f_notes.result(),
        "assessments": f_assess.result(),
    }
