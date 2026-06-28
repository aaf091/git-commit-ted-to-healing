"""Pydantic response models — keep the API contract explicit for the frontend."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class UploadResponse(BaseModel):
    dataset_name: str
    row_count: int
    columns: list[str]
    column_map: dict[str, str]
    unmapped_columns: list[str]
    preview: list[dict[str, Any]]


class Record(BaseModel):
    row_id: str
    data: dict[str, Any]


class Evidence(BaseModel):
    field: str
    value: Any


class Flag(BaseModel):
    flag_id: str
    row_id: str
    type: str                 # "rule" | "duplicate"
    rule_id: Optional[str] = None
    label: str
    category: str
    severity: str             # high | medium | low
    confidence: float         # 0-100
    explanation: str
    evidence: list[Evidence]
    related_row_ids: list[str] = []


class DupeMember(BaseModel):
    row_id: str
    name: str
    dob: Optional[str] = None
    score: float


class DupeCluster(BaseModel):
    cluster_id: str
    status: str               # "match" | "review"
    score: float
    members: list[DupeMember]


class Stats(BaseModel):
    record_count: int
    flag_count: int
    high_severity: int
    duplicate_clusters: int
    by_category: dict[str, int]
    estimated_recoverable: float
