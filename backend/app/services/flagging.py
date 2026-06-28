"""
Flagging = the unified issue queue. It merges:
  - rule violations (from rules_engine), and
  - duplicate clusters (from matching)
into ONE list of flags with a consistent shape, sorted so reviewers see the
highest-severity, highest-confidence items first.

This is what makes the demo land: one prioritized queue, every item explainable.
"""
from __future__ import annotations

from typing import Any

from app.config import SEVERITY_ORDER
from app.services import matching, rules_engine


def build_flags(records: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Returns (flags, duplicate_clusters)."""
    flags: list[dict[str, Any]] = rules_engine.evaluate(records)

    clusters = matching.find_duplicates(records)
    flags.extend(_dupe_flags(clusters))

    flags.sort(key=lambda f: (
        SEVERITY_ORDER.get(f["severity"], 9),
        -f["confidence"],
    ))
    return flags, clusters


def _dupe_flags(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in clusters:
        member_ids = [m["row_id"] for m in c["members"]]
        names = ", ".join(m["name"] for m in c["members"])
        is_match = c["status"] == "match"
        for m in c["members"]:
            others = [rid for rid in member_ids if rid != m["row_id"]]
            out.append({
                "flag_id": f"{c['cluster_id']}::{m['row_id']}",
                "row_id": m["row_id"],
                "type": "duplicate",
                "rule_id": None,
                "label": "Likely duplicate record" if is_match else "Possible duplicate (review)",
                "category": "duplicate",
                "severity": "high" if is_match else "medium",
                "confidence": c["score"],
                "explanation": f"Matches {len(others)} other record(s) in cluster "
                               f"{c['cluster_id']} ({names}) at {c['score']}% similarity.",
                "evidence": [
                    {"field": "cluster_id", "value": c["cluster_id"]},
                    {"field": "similarity", "value": c["score"]},
                    {"field": "members", "value": names},
                ],
                "related_row_ids": others,
            })
    return out


def compute_stats(records: list[dict], flags: list[dict],
                  clusters: list[dict]) -> dict[str, Any]:
    by_category: dict[str, int] = {}
    recoverable = 0.0
    for f in flags:
        by_category[f["category"]] = by_category.get(f["category"], 0) + 1

    # Rough "money on the table" estimate from revenue-category flags.
    by_id = {r["_row_id"]: r for r in records}
    for f in flags:
        if f["category"] == "revenue":
            amt = by_id.get(f["row_id"], {}).get("charge_amount")
            try:
                recoverable += float(amt)
            except (TypeError, ValueError):
                continue

    by_status: dict[str, int] = {}
    for f in flags:
        s = f.get("status", "open")
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "record_count": len(records),
        "flag_count": len(flags),
        "open_count": by_status.get("open", len(flags)),
        "high_severity": sum(1 for f in flags if f["severity"] == "high"),
        "duplicate_clusters": len(clusters),
        "by_category": by_category,
        "by_status": by_status,
        "estimated_recoverable": round(recoverable, 2),
    }
