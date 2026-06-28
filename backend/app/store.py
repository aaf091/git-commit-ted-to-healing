"""
In-memory store for the wound-care eligibility pipeline.

Holds the last sync: the raw API bundles (per patient) and the computed
eligibility rows (routing decisions). Hackathon-grade — no DB. The one thing
we persist to disk is the biller's human action on each patient
(open / billed / dismissed), keyed by patient_id, so decisions survive a restart.
"""
from __future__ import annotations

import json
import os
from threading import Lock
from typing import Any, Optional

VALID_STATUSES = {"open", "billed", "dismissed"}
_STATUS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "patient_status.json")


class DataStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.bundles: list[dict[str, Any]] = []      # raw API data per patient
        self.rows: list[dict[str, Any]] = []         # eligibility decisions
        self.rows_by_id: dict[str, dict[str, Any]] = {}
        self.bundles_by_id: dict[str, dict[str, Any]] = {}
        self.facilities_synced: list[int] = []
        self.api_stats: dict[str, int] = {}
        self.last_sync: Optional[str] = None
        self.patient_status: dict[str, dict[str, Any]] = self._load_status()

    def set_results(self, bundles: list[dict], rows: list[dict],
                    facilities: list[int], api_stats: dict, ts: str) -> None:
        with self._lock:
            self.bundles = bundles
            self.rows = rows
            self.rows_by_id = {r["row_id"]: r for r in rows}
            self.bundles_by_id = {str(b["patient"].get("patient_id")): b for b in bundles}
            self.facilities_synced = facilities
            self.api_stats = api_stats
            self.last_sync = ts
            self.apply_status(self.rows)

    def has_data(self) -> bool:
        return bool(self.rows)

    def record_by_id(self, row_id: str) -> Optional[dict[str, Any]]:
        return self.rows_by_id.get(str(row_id))

    def bundle_by_id(self, row_id: str) -> Optional[dict[str, Any]]:
        return self.bundles_by_id.get(str(row_id))

    # -- human workflow status --------------------------------------------
    def apply_status(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for r in rows:
            st = self.patient_status.get(r["row_id"])
            r["status"] = st["status"] if st else "open"
            r["status_note"] = st.get("note") if st else None
        return rows

    def set_status(self, row_id: str, status: str, note: str | None = None) -> None:
        with self._lock:
            self.patient_status[row_id] = {"status": status, "note": note}
            r = self.rows_by_id.get(row_id)
            if r:
                r["status"] = status
                r["status_note"] = note
            self._save_status()

    def _load_status(self) -> dict[str, dict[str, Any]]:
        try:
            with open(_STATUS_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_status(self) -> None:
        os.makedirs(os.path.dirname(_STATUS_PATH), exist_ok=True)
        with open(_STATUS_PATH, "w", encoding="utf-8") as fh:
            json.dump(self.patient_status, fh, indent=2)


store = DataStore()
