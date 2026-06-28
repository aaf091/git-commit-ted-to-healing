"""Resilient client for the Pulse Foundry mock PCC API.

The API returns HTTP 429 on ~30% of requests. This client retries with
exponential backoff + jitter and honors the Retry-After header, so callers
always get complete data. It also transparently handles the two-layer patient
identity (string patient_id like 'FA-001' vs integer id like 1).
"""
from __future__ import annotations

import random
import threading
import time
from typing import Any

import requests

BASE_URL = "https://hackathon.prod.pulsefoundry.ai"
FACILITIES = [101, 102, 103]


class APIClient:
    def __init__(self, base_url: str = BASE_URL, max_retries: int = 8,
                 base_backoff: float = 0.5, timeout: float = 20.0,
                 verbose: bool = True):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.timeout = timeout
        self.verbose = verbose
        # requests.Session is NOT thread-safe -> one Session per thread.
        self._local = threading.local()
        self._stats_lock = threading.Lock()
        self.stats = {"requests": 0, "rate_limited": 0, "retries": 0, "errors": 0}

    @property
    def session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            self._local.session = s
        return s

    def _bump(self, key: str) -> None:
        with self._stats_lock:
            self.stats[key] += 1

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        attempt = 0
        while True:
            attempt += 1
            self._bump("requests")
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException:
                self._bump("errors")
                if attempt > self.max_retries:
                    raise
                self._sleep(attempt)
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                self._bump("rate_limited")
                self._bump("retries")
                if attempt > self.max_retries:
                    raise RuntimeError(f"429 exhausted retries: {path} {params}")
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else None
                self._sleep(attempt, delay)
                continue

            # 422 / 500 etc. — surface with context
            self._bump("errors")
            raise RuntimeError(
                f"HTTP {resp.status_code} for {path} {params}: {resp.text[:300]}"
            )

    def _sleep(self, attempt: int, fixed: float | None = None) -> None:
        if fixed is not None:
            delay = fixed + random.uniform(0, 0.4)
        else:
            delay = self.base_backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.4)
        delay = min(delay, 8.0)
        time.sleep(delay)

    # ---- endpoint wrappers -------------------------------------------------
    def health(self) -> Any:
        return self._get("/health")

    def patients(self, facility_id: int, since: str | None = None) -> list[dict]:
        params = {"facility_id": facility_id}
        if since:
            params["since"] = since
        return self._get("/pcc/patients", params)

    def diagnoses(self, patient_id_str: str) -> list[dict]:
        return self._get("/pcc/diagnoses", {"patient_id": patient_id_str})

    def coverage(self, patient_id_str: str) -> list[dict]:
        return self._get("/pcc/coverage", {"patient_id": patient_id_str})

    def notes(self, int_id: int, since: str | None = None) -> list[dict]:
        params: dict = {"patient_id": int_id}
        if since:
            params["since"] = since
        return self._get("/pcc/notes", params)

    def assessments(self, int_id: int, since: str | None = None) -> list[dict]:
        params: dict = {"patient_id": int_id}
        if since:
            params["since"] = since
        return self._get("/pcc/assessments", params)

    def all_patients(self) -> list[dict]:
        out: list[dict] = []
        for fac in FACILITIES:
            rows = self.patients(fac)
            if self.verbose:
                print(f"  facility {fac}: {len(rows)} patients")
            out.extend(rows)
        return out
