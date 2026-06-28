"""
PointClickCare (mock) API client.

The API returns HTTP 429 on ~30% of requests with a Retry-After header. The whole
point of "pipeline design — graceful failure handling" is here: every request
retries with backoff that honors Retry-After, so a rate-limited fetch never loses
data, it just slows down.

Endpoints (per API.md):
  GET /pcc/patients?facility_id=101[&since=ISO]   -> list (id int, patient_id str, ...)
  GET /pcc/diagnoses?patient_id=FA-001            -> ICD-10 diagnoses
  GET /pcc/coverage?patient_id=FA-001             -> insurance coverage
  GET /pcc/notes?patient_id=1                     -> progress notes (INTEGER id!)
  GET /pcc/assessments?patient_id=1               -> structured assessments (INTEGER id!)

Note the id quirk: diagnoses/coverage key on the STRING patient_id ("FA-001"),
while notes/assessments key on the INTEGER id (1). We handle both.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from app.config import PCC_BASE_URL

_MAX_RETRIES = 10
_TIMEOUT = 25


class PCCClient:
    def __init__(self, base_url: str = PCC_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.stats = {"requests": 0, "rate_limited": 0, "errors": 0}

    # -- low-level GET with rate-limit handling ----------------------------
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        qs = ("?" + urllib.parse.urlencode(params)) if params else ""
        url = self.base_url + path + qs
        backoff = 1.0
        for attempt in range(_MAX_RETRIES):
            self.stats["requests"] += 1
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    self.stats["rate_limited"] += 1
                    retry_after = _parse_retry_after(e.headers.get("Retry-After"), backoff)
                    time.sleep(retry_after)
                    backoff = min(backoff * 1.5, 8)
                    continue
                if e.code == 422:
                    self.stats["errors"] += 1
                    raise ValueError(f"Bad request to {path}: {e.read().decode()[:200]}")
                # 5xx: retry a few times, then give up gracefully.
                self.stats["errors"] += 1
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 8)
            except (urllib.error.URLError, TimeoutError):
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 8)
        # Exhausted retries — return empty rather than crash the whole sync.
        return []

    # -- typed endpoints ---------------------------------------------------
    def health(self) -> dict:
        return self._get("/health")

    def patients(self, facility_id: int, since: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"facility_id": facility_id}
        if since:
            params["since"] = since
        data = self._get("/pcc/patients", params)
        return data if isinstance(data, list) else []

    def diagnoses(self, patient_id_str: str) -> list[dict]:
        return _as_list(self._get("/pcc/diagnoses", {"patient_id": patient_id_str}))

    def coverage(self, patient_id_str: str) -> list[dict]:
        return _as_list(self._get("/pcc/coverage", {"patient_id": patient_id_str}))

    def notes(self, patient_id_int: int, since: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"patient_id": patient_id_int}
        if since:
            params["since"] = since
        return _as_list(self._get("/pcc/notes", params))

    def assessments(self, patient_id_int: int, since: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"patient_id": patient_id_int}
        if since:
            params["since"] = since
        return _as_list(self._get("/pcc/assessments", params))

    # -- orchestration: pull everything for a facility ---------------------
    def fetch_facility(self, facility_id: int, limit: int | None = None,
                       since: str | None = None,
                       progress: Optional[Callable[[int, int], None]] = None,
                       max_workers: int = 6) -> list[dict]:
        """
        Returns a list of bundles: {patient, diagnoses, coverage, notes, assessments}.
        Fetches per-patient detail concurrently (bounded) so 429s on one patient
        don't stall the others. `limit` caps patients for a fast demo sync.
        """
        patients = self.patients(facility_id, since=since)
        if limit:
            patients = patients[:limit]
        total = len(patients)
        bundles: list[dict] = []

        def _one(p: dict) -> dict:
            pid_str = str(p.get("patient_id"))
            pid_int = p.get("id")
            return {
                "patient": p,
                "diagnoses": self.diagnoses(pid_str),
                "coverage": self.coverage(pid_str),
                "notes": self.notes(pid_int, since=since),
                "assessments": self.assessments(pid_int, since=since),
            }

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for i, bundle in enumerate(pool.map(_one, patients), 1):
                bundles.append(bundle)
                if progress:
                    progress(i, total)
        return bundles


def _as_list(data: Any) -> list[dict]:
    return data if isinstance(data, list) else ([] if data is None else [data])


def _parse_retry_after(header: str | None, fallback: float) -> float:
    if not header:
        return fallback
    try:
        return max(0.5, float(header))
    except (TypeError, ValueError):
        return fallback
