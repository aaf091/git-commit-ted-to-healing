import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import api_client
from eligibility import EligibilityResult, determine_eligibility

logger = logging.getLogger(__name__)

PAGE_SIZE = 20

_cache: dict[str, EligibilityResult] = {}
_cache_lock = threading.Lock()
_patient_list: list[dict] = []
_current_facility: int | None = None
_prefetch_thread: threading.Thread | None = None


def load_facility(facility_id: int, force_refresh: bool = False) -> list[dict]:
    global _patient_list, _current_facility
    if _current_facility == facility_id and not force_refresh and _patient_list:
        return _patient_list

    _patient_list = api_client.get_patients(facility_id)
    _patient_list.sort(key=lambda p: p.get("patient_id", ""))
    _current_facility = facility_id
    with _cache_lock:
        _cache.clear()
    return _patient_list


def total_pages() -> int:
    return max(1, math.ceil(len(_patient_list) / PAGE_SIZE))


def get_page(page_num: int) -> list[dict]:
    start = page_num * PAGE_SIZE
    end = start + PAGE_SIZE
    return _patient_list[start:end]


def is_cached(patient_id: str) -> bool:
    with _cache_lock:
        return patient_id in _cache


def process_patient(patient: dict) -> EligibilityResult:
    pid = patient["patient_id"]

    with _cache_lock:
        if pid in _cache:
            result = _cache[pid]
            result.from_cache = True
            return result

    # Try disk cache first
    cached_data = api_client.load_cached_patient(pid)
    if cached_data:
        full_data = cached_data
    else:
        full_data = api_client.fetch_full_patient(patient)

    result = determine_eligibility(full_data)
    result.from_cache = False

    with _cache_lock:
        _cache[pid] = result
    return result


def process_page(page_num: int) -> list[EligibilityResult]:
    patients = get_page(page_num)
    results: dict[str, EligibilityResult] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        future_to_patient = {pool.submit(process_patient, p): p for p in patients}
        for future in as_completed(future_to_patient):
            patient = future_to_patient[future]
            pid = patient.get("patient_id", "")
            try:
                results[pid] = future.result()
            except Exception as e:
                logger.error("Error processing %s: %s", pid, e)
                results[pid] = EligibilityResult(
                    patient_id=pid,
                    patient_name=f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip(),
                    decision="flag_for_review",
                    reason=f"Processing error: {e}",
                )
    return [results[p["patient_id"]] for p in patients]


def _prefetch_worker(page_num: int):
    try:
        process_page(page_num)
    except Exception as e:
        logger.error("Prefetch error for page %d: %s", page_num, e)


def start_prefetch(next_page: int) -> threading.Thread | None:
    global _prefetch_thread
    if next_page >= total_pages():
        return None
    if _prefetch_thread and _prefetch_thread.is_alive():
        return _prefetch_thread
    _prefetch_thread = threading.Thread(target=_prefetch_worker, args=(next_page,), daemon=True)
    _prefetch_thread.start()
    return _prefetch_thread


def get_summary_stats() -> dict:
    with _cache_lock:
        values = list(_cache.values())
    stats = {"total": len(_patient_list), "auto_accept": 0, "flag_for_review": 0, "reject": 0, "processed": len(values)}
    for r in values:
        if r.decision in stats:
            stats[r.decision] += 1
    return stats


def process_all_patients() -> list[EligibilityResult]:
    results = []
    for patient in _patient_list:
        try:
            result = process_patient(patient)
            results.append(result)
        except Exception as e:
            logger.error("Error processing %s: %s", patient.get("patient_id"), e)
    return results
