"""
Declarative rules engine. Rules live as DATA in config.RULES; this file just
evaluates them. Add/remove/edit rules at kickoff without touching engine code.

Each rule's `expr` is a Python expression evaluated per row with the row's
canonical fields available as variables, plus a small whitelist of helpers:

    has(x)            -> field has a non-empty value
    missing(x)        -> field is empty
    missing_any([..]) -> any listed field is empty
    truthy(x)         -> value looks affirmative (yes/y/true/1/billed)
    norm(x)           -> lowercased trimmed string ('' if empty)
    num(x)            -> float value (0.0 if not numeric)

Evaluation is sandboxed: no builtins, no imports, only the helpers above.
"""
from __future__ import annotations

from typing import Any

from app.config import RULES, SCHEMA


def evaluate(records: list[dict[str, Any]],
             rules: list[dict] | None = None) -> list[dict[str, Any]]:
    rules = rules if rules is not None else RULES
    flags: list[dict[str, Any]] = []

    for r in records:
        env = _row_env(r)
        for rule in rules:
            try:
                hit = bool(_safe_eval(rule["expr"], env))
            except Exception:
                # A broken rule should never crash the whole run during a demo.
                hit = False
            if hit:
                flags.append(_make_flag(r, rule))
    return flags


def _make_flag(r: dict[str, Any], rule: dict) -> dict[str, Any]:
    evidence = [{"field": f, "value": r.get(f)}
                for f in rule.get("evidence_fields", [])]
    return {
        "flag_id": f"{rule['id']}::{r['_row_id']}",
        "row_id": r["_row_id"],
        "type": "rule",
        "rule_id": rule["id"],
        "label": rule["label"],
        "category": rule["category"],
        "severity": rule["severity"],
        "confidence": _confidence(r, rule),
        "explanation": rule["explain"],
        "evidence": evidence,
        "related_row_ids": [],
    }


def _confidence(r: dict[str, Any], rule: dict) -> float:
    """
    Simple, defensible confidence: start high for a deterministic rule hit,
    reduce when the evidence fields backing it are themselves incomplete.
    Healthcare reviewers trust "here's why" far more than a black-box number.
    """
    fields = rule.get("evidence_fields", []) or list(SCHEMA)
    present = sum(1 for f in fields if r.get(f) not in (None, ""))
    completeness = present / len(fields) if fields else 1.0
    return round(60 + 40 * completeness, 1)


# --------------------------------------------------------------------------- #
# Safe evaluation environment
# --------------------------------------------------------------------------- #
def _row_env(r: dict[str, Any]) -> dict[str, Any]:
    env: dict[str, Any] = {f: r.get(f) for f in SCHEMA}

    def has(x: Any) -> bool:
        return x not in (None, "")

    def missing(x: Any) -> bool:
        return x in (None, "")

    def missing_any(names: list[str]) -> bool:
        return any(r.get(n) in (None, "") for n in names)

    def truthy(x: Any) -> bool:
        return str(x).strip().lower() in ("y", "yes", "true", "1", "billed", "t")

    def norm(x: Any) -> str:
        return "" if x in (None, "") else str(x).strip().lower()

    def num(x: Any) -> float:
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0

    env.update(has=has, missing=missing, missing_any=missing_any,
               truthy=truthy, norm=norm, num=num)
    return env


def _safe_eval(expr: str, env: dict[str, Any]) -> Any:
    # No builtins exposed -> expressions can only use the row fields + helpers.
    return eval(expr, {"__builtins__": {}}, env)
