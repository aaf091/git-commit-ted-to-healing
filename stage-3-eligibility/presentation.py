"""
Stage 4 — Presentation.

Turns Stage 3's eligibility table into the plain-English summary a
non-technical biller actually needs: how many patients, how many in each
bucket, and what they should do next. No new data is computed here --
this only narrates what Stage 3 already decided.
"""
from collections import Counter

import eligibility


def summarize(results: list) -> dict:
    counts = Counter(r.decision for r in results)
    total = len(results)
    auto = counts.get("auto_accept", 0)
    review = counts.get("flag_for_review", 0)
    rejected = counts.get("reject", 0)

    # Break down WHY patients were rejected/flagged, since "reject: 12" alone
    # doesn't tell a biller anything actionable.
    reject_reasons = Counter()
    for r in results:
        if r.decision != "reject":
            continue
        if not r.has_active_mcb:
            if r.has_lapsed_mcb:
                reject_reasons["Part B coverage lapsed"] += 1
            else:
                reject_reasons[f"no Part B coverage (payer: {r.primary_payer_code or 'unknown'})"] += 1
        elif r.wound_count == 0:
            reject_reasons["no wound documentation found"] += 1

    review_reasons = Counter()
    for r in results:
        if r.decision != "flag_for_review":
            continue
        if r.best_wound_depth_cm is None:
            review_reasons["missing depth measurement"] += 1
        elif r.best_wound_type is None:
            review_reasons["wound type not documented"] += 1
        else:
            review_reasons["other incomplete documentation"] += 1

    return {
        "total": total,
        "auto_accept": auto,
        "flag_for_review": review,
        "reject": rejected,
        "auto_accept_pct": round(100 * auto / total, 1) if total else 0,
        "flag_for_review_pct": round(100 * review / total, 1) if total else 0,
        "reject_pct": round(100 * rejected / total, 1) if total else 0,
        "reject_reasons": dict(reject_reasons),
        "review_reasons": dict(review_reasons),
    }


def narrative(summary: dict) -> str:
    """The one-paragraph version a biller reads first."""
    lines = []
    lines.append(
        f"Out of {summary['total']} patients reviewed, "
        f"{summary['auto_accept']} ({summary['auto_accept_pct']}%) are ready "
        f"to bill as-is, {summary['flag_for_review']} ({summary['flag_for_review_pct']}%) "
        f"need a quick documentation check before billing, and "
        f"{summary['reject']} ({summary['reject_pct']}%) don't qualify under "
        f"this program right now."
    )
    if summary["reject_reasons"]:
        parts = [f"{v} {k}" for k, v in sorted(summary["reject_reasons"].items(), key=lambda x: -x[1])]
        lines.append("Of those that don't qualify: " + "; ".join(parts) + ".")
    if summary["review_reasons"]:
        parts = [f"{v} {k}" for k, v in sorted(summary["review_reasons"].items(), key=lambda x: -x[1])]
        lines.append("Of those needing review: " + "; ".join(parts) + ".")
    return " ".join(lines)


def biller_action_list(results: list, decision: str, limit: int = 10) -> list[dict]:
    """The actual worklist for a given bucket -- what a biller would scroll
    through, sorted with the most actionable items first."""
    subset = [r for r in results if r.decision == decision]
    if decision == "flag_for_review":
        # fewest missing fields first -- quickest fixes surface at the top
        subset.sort(key=lambda r: len(r.missing_fields_on_best))
    return [
        {
            "patient": f"{r.first_name} {r.last_name}",
            "patient_id": r.patient_id_str,
            "facility_id": r.facility_id,
            "reason": r.reason,
        }
        for r in subset[:limit]
    ]


if __name__ == "__main__":
    results = eligibility.run_eligibility()
    summary = summarize(results)

    print("=" * 70)
    print("WOUND CARE BILLING ELIGIBILITY -- SUMMARY FOR BILLING TEAM")
    print("=" * 70)
    print()
    print(narrative(summary))
    print()
    print("-" * 70)
    print(f"READY TO BILL ({summary['auto_accept']} patients):")
    for item in biller_action_list(results, "auto_accept", limit=5):
        print(f"  - {item['patient']} ({item['patient_id']}, facility {item['facility_id']})")
    if summary["auto_accept"] > 5:
        print(f"  ... and {summary['auto_accept'] - 5} more")
    print()
    print("-" * 70)
    print(f"NEEDS YOUR REVIEW ({summary['flag_for_review']} patients):")
    for item in biller_action_list(results, "flag_for_review", limit=5):
        print(f"  - {item['patient']} ({item['patient_id']}): {item['reason']}")
    if summary["flag_for_review"] > 5:
        print(f"  ... and {summary['flag_for_review'] - 5} more")
    print()
    print("-" * 70)
    print(f"DOES NOT QUALIFY ({summary['reject']} patients):")
    for item in biller_action_list(results, "reject", limit=5):
        print(f"  - {item['patient']} ({item['patient_id']}): {item['reason']}")
    if summary["reject"] > 5:
        print(f"  ... and {summary['reject'] - 5} more")