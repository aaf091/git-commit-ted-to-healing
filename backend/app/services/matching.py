"""
Fuzzy matching / deduplication with RapidFuzz.

Strategy:
  1. BLOCKING — group records by a cheap coarse key so we only compare records
     that could plausibly match (avoids O(n^2) over the whole dataset).
  2. SCORING — within a block, compute a weighted similarity per field pair and
     combine into a single 0-100 score.
  3. CLUSTERING — union-find pairs above the threshold into duplicate clusters.

Reusable for ANY entity-matching problem (patients, providers, claims,
facilities). Only MATCH_CONFIG.weights / blocking_fields change at kickoff.
"""
from __future__ import annotations

from typing import Any, Optional

from rapidfuzz import fuzz

from app.config import MATCH_CONFIG


def find_duplicates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weights = MATCH_CONFIG["weights"]
    match_t = MATCH_CONFIG["match_threshold"]
    review_t = MATCH_CONFIG["review_threshold"]

    blocks = _build_blocks(records)
    uf = _UnionFind()
    pair_scores: dict[tuple[str, str], float] = {}

    for block in blocks.values():
        for i in range(len(block)):
            for j in range(i + 1, len(block)):
                a, b = block[i], block[j]
                score = _pair_score(a, b, weights)
                if score >= review_t:
                    # Cluster at the *candidate* threshold so review-band pairs
                    # (70-85) surface too. Each cluster's status (match vs
                    # review) is then derived from its max pair score below.
                    key = tuple(sorted((a["_row_id"], b["_row_id"])))
                    pair_scores[key] = max(pair_scores.get(key, 0.0), score)
                    uf.union(a["_row_id"], b["_row_id"])

    return _assemble_clusters(records, uf, pair_scores, match_t)


def _build_blocks(records: list[dict[str, Any]]) -> dict[str, list[dict]]:
    """Coarse buckets so we never compare every record to every other record."""
    fields = MATCH_CONFIG["blocking_fields"]
    blocks: dict[str, list[dict]] = {}
    for r in records:
        key = _blocking_key(r, fields)
        blocks.setdefault(key, []).append(r)
    return blocks


def _blocking_key(r: dict[str, Any], fields: list[str]) -> str:
    parts: list[str] = []
    for f in fields:
        v = (r.get(f) or "")
        v = str(v)
        if f == "dob" and len(v) >= 4:
            parts.append(v[:4])            # birth year
        else:
            parts.append(v[:1].lower())    # first initial / first char
    return "|".join(parts)


def _pair_score(a: dict, b: dict, weights: dict[str, float]) -> float:
    total_w = 0.0
    acc = 0.0
    for field, w in weights.items():
        va, vb = a.get(field), b.get(field)
        if not va or not vb:
            continue  # skip fields missing on either side; don't penalize
        sim = fuzz.token_sort_ratio(str(va).lower(), str(vb).lower())
        acc += w * sim
        total_w += w
    if total_w == 0:
        return 0.0
    return round(acc / total_w, 1)


def _assemble_clusters(records, uf, pair_scores, match_t) -> list[dict[str, Any]]:
    by_id = {r["_row_id"]: r for r in records}
    groups: dict[str, list[str]] = {}
    for rid in by_id:
        root = uf.find(rid)
        if root is not None:
            groups.setdefault(root, []).append(rid)

    clusters: list[dict[str, Any]] = []
    cid = 0
    for member_ids in groups.values():
        if len(member_ids) < 2:
            continue
        cid += 1
        scores = [pair_scores[k] for k in pair_scores
                  if k[0] in member_ids and k[1] in member_ids]
        cluster_score = round(max(scores), 1) if scores else match_t
        members = [{
            "row_id": rid,
            "name": _display_name(by_id[rid]),
            "dob": by_id[rid].get("dob"),
            "score": cluster_score,
        } for rid in member_ids]
        clusters.append({
            "cluster_id": f"dup{cid}",
            "status": "match" if cluster_score >= match_t else "review",
            "score": cluster_score,
            "members": members,
        })

    clusters.sort(key=lambda c: c["score"], reverse=True)
    return clusters


def _display_name(r: dict[str, Any]) -> str:
    first = r.get("first_name") or ""
    last = r.get("last_name") or ""
    return f"{first} {last}".strip() or (r.get("patient_id") or r["_row_id"])


class _UnionFind:
    """Tiny union-find to merge transitive duplicate pairs into clusters."""
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> Optional[str]:
        if x not in self.parent:
            return None
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        self.parent.setdefault(a, a)
        self.parent.setdefault(b, b)
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra
