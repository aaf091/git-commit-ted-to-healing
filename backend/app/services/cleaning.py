"""
Cleaning / normalization. Healthcare exports are reliably messy: stray
whitespace, inconsistent casing, a dozen date formats, phone numbers with
punctuation. Normalize once here so matching + rules see consistent values.

Reusable for ANY problem. Tune DATE_FIELDS / NUMERIC_FIELDS in config.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd
from dateutil import parser as dateparser

from app.config import DATE_FIELDS, NUMERIC_FIELDS, SCHEMA


def clean(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in SCHEMA:
        if col not in out.columns:
            continue
        if col in DATE_FIELDS:
            out[col] = out[col].map(normalize_date)
        elif col in NUMERIC_FIELDS:
            out[col] = out[col].map(normalize_number)
        elif col == "phone":
            out[col] = out[col].map(normalize_phone)
        elif col == "email":
            out[col] = out[col].map(lambda v: _trim(v).lower() or None)
        else:
            out[col] = out[col].map(normalize_text)
    return out


def normalize_text(v: Any) -> Optional[str]:
    s = _trim(v)
    if not s:
        return None
    # Collapse internal whitespace; preserve original casing for display.
    return re.sub(r"\s+", " ", s)


def normalize_date(v: Any) -> Optional[str]:
    s = _trim(v)
    if not s:
        return None
    try:
        # dayfirst=False handles US-style; flip at kickoff if data is intl.
        return dateparser.parse(s, dayfirst=False, fuzzy=True).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return s  # keep raw so it's visible rather than silently dropped


def normalize_number(v: Any) -> Optional[float]:
    s = _trim(v)
    if not s:
        return None
    s = re.sub(r"[^0-9.\-]", "", s)  # strip $ , and other symbols
    try:
        return float(s)
    except ValueError:
        return None


def normalize_phone(v: Any) -> Optional[str]:
    s = _trim(v)
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits or None


def _trim(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "null", "n/a", "na", "-"):
        return ""
    return s
