"""
Dead-simple in-memory store. One process, one active dataset.

Hackathon-grade on purpose: no DB, no migrations. Swap for SQLite/Postgres
later if you genuinely need persistence. Everything keys off the most recent
upload so the demo flow is: upload -> clean -> dedupe -> rules -> review.

Flag review status (open/resolved/dismissed/confirmed) is the one thing we DO
persist — to data/flag_status.json — so a reviewer's decisions survive a
backend restart. Flag IDs are deterministic (rule_id::row_id), so re-uploading
the same data lines the statuses back up.
"""
from __future__ import annotations

import json
import os
from threading import Lock
from typing import Any, Optional

import pandas as pd

VALID_STATUSES = {"open", "resolved", "dismissed", "confirmed"}
_STATUS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "flag_status.json")


class DataStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.raw_df: Optional[pd.DataFrame] = None        # exactly as uploaded
        self.clean_df: Optional[pd.DataFrame] = None       # normalized/canonical
        self.dataset_name: Optional[str] = None
        self.dupe_clusters: list[dict[str, Any]] = []      # from dedupe run
        self.flags: list[dict[str, Any]] = []              # unified issue queue
        self.column_map: dict[str, str] = {}               # canonical -> source col
        self.flag_status: dict[str, dict[str, Any]] = self._load_status()

    def set_dataset(self, name: str, raw: pd.DataFrame, clean: pd.DataFrame,
                    column_map: dict[str, str]) -> None:
        with self._lock:
            self.dataset_name = name
            self.raw_df = raw
            self.clean_df = clean
            self.column_map = column_map
            # New data invalidates previous analysis (but NOT review statuses —
            # those are keyed by deterministic flag_id and persisted to disk).
            self.dupe_clusters = []
            self.flags = []

    def has_data(self) -> bool:
        return self.clean_df is not None and not self.clean_df.empty

    def records(self) -> list[dict[str, Any]]:
        if not self.has_data():
            return []
        return self.clean_df.to_dict(orient="records")

    def record_by_id(self, record_id: str) -> Optional[dict[str, Any]]:
        if not self.has_data():
            return None
        df = self.clean_df
        hit = df[df["_row_id"].astype(str) == str(record_id)]
        if hit.empty:
            return None
        return hit.iloc[0].to_dict()

    # -- review status -----------------------------------------------------
    def apply_status(self, flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Stamp each flag with its review status + note (default 'open')."""
        for f in flags:
            st = self.flag_status.get(f["flag_id"])
            f["status"] = st["status"] if st else "open"
            f["status_note"] = st.get("note") if st else None
        return flags

    def set_status(self, flag_id: str, status: str, note: str | None = None) -> None:
        with self._lock:
            self.flag_status[flag_id] = {"status": status, "note": note}
            for f in self.flags:                 # update the cached queue in place
                if f["flag_id"] == flag_id:
                    f["status"] = status
                    f["status_note"] = note
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
            json.dump(self.flag_status, fh, indent=2)


# Module-level singleton imported everywhere.
store = DataStore()
