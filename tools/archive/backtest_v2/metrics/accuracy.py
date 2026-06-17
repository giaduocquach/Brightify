"""Group B accuracy metrics — NDCG@K, Precision@K, Recall@K, MAP@K, MRR, Hit@K. §8.

K ∈ {5, 10, 20}.  NDCG@10 is the primary ranking metric for version comparison.

All functions take:
    ranked   — ordered list of catalog indices (system output, best-first)
    relevant — set of catalog indices that are ground-truth relevant for this query
    k        — cutoff
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Set, Any


def ndcg_at_k(ranked: Sequence[Any], relevant: Set[Any], k: int = 10) -> float:
    """Normalised Discounted Cumulative Gain at K.

    Gain is binary (0/1).  Formula: (2^rel − 1) / log2(i + 2), i=0-based.
    """
    if not relevant:
        return 0.0
    dcg = sum(
        1.0 / math.log2(i + 2)
        for i, item in enumerate(ranked[:k])
        if item in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def precision_at_k(ranked: Sequence[Any], relevant: Set[Any], k: int = 10) -> float:
    if k == 0:
        return 0.0
    hits = sum(1 for item in ranked[:k] if item in relevant)
    return hits / k


def recall_at_k(ranked: Sequence[Any], relevant: Set[Any], k: int = 10) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for item in ranked[:k] if item in relevant)
    return hits / len(relevant)


def average_precision_at_k(ranked: Sequence[Any], relevant: Set[Any], k: int = 10) -> float:
    """Mean of precision at each hit position up to k."""
    if not relevant:
        return 0.0
    hits = 0
    cumulative_precision = 0.0
    for i, item in enumerate(ranked[:k]):
        if item in relevant:
            hits += 1
            cumulative_precision += hits / (i + 1)
    if hits == 0:
        return 0.0
    return cumulative_precision / min(len(relevant), k)


def mrr(ranked: Sequence[Any], relevant: Set[Any]) -> float:
    """Mean Reciprocal Rank — 1 / rank of first hit (rank is 1-based)."""
    for i, item in enumerate(ranked):
        if item in relevant:
            return 1.0 / (i + 1)
    return 0.0


def hit_at_k(ranked: Sequence[Any], relevant: Set[Any], k: int = 10) -> float:
    """1.0 if any item in ranked[:k] is relevant, else 0.0."""
    return 1.0 if any(item in relevant for item in ranked[:k]) else 0.0


# ---------------------------------------------------------------------------
# Batch evaluation over a GT mapping
# ---------------------------------------------------------------------------

K_VALUES = (5, 10, 20)


def evaluate_system_accuracy(
    system,
    ground_truth: Dict[int, List[int]],
    top_k: int = 20,
    ground_truth_name: str = "editorial_playlists_v1",
) -> Dict[str, Any]:
    """Run accuracy metrics for one system over all GT queries.

    Args:
        system      — object with .recommend(seed_idx, top_k) → List[int]
        ground_truth — {seed_catalog_idx: [relevant_catalog_idx, ...]}
        top_k       — maximum recommendation depth (should be >= max K)

    Returns:
        dict of metric entries compatible with BacktestReport.systems format.
    """
    from tools.backtest_v2.core import _metric_entry

    per_query: Dict[str, List[float]] = {
        f"ndcg_at_{k}": [] for k in K_VALUES
    }
    for k in K_VALUES:
        per_query[f"precision_at_{k}"] = []
        per_query[f"recall_at_{k}"] = []
        per_query[f"map_at_{k}"] = []
        per_query[f"hit_at_{k}"] = []
    per_query["mrr"] = []

    for seed_idx, relevant_indices in ground_truth.items():
        relevant = set(relevant_indices)
        if not relevant:
            continue
        ranked = system.recommend(seed_idx, top_k=top_k)
        if not ranked:
            # System returned nothing — all metrics = 0
            for key in per_query:
                per_query[key].append(0.0)
            continue

        for k in K_VALUES:
            per_query[f"ndcg_at_{k}"].append(ndcg_at_k(ranked, relevant, k))
            per_query[f"precision_at_{k}"].append(precision_at_k(ranked, relevant, k))
            per_query[f"recall_at_{k}"].append(recall_at_k(ranked, relevant, k))
            per_query[f"map_at_{k}"].append(average_precision_at_k(ranked, relevant, k))
            per_query[f"hit_at_{k}"].append(hit_at_k(ranked, relevant, k))
        per_query["mrr"].append(mrr(ranked, relevant))

    result: Dict[str, Any] = {}
    for metric_name, values in per_query.items():
        result[metric_name] = _metric_entry(
            values,
            validity="external",
            ground_truth=ground_truth_name,
        )
    return result
