"""Pillar C — RRF hybrid retrieval (Cormack et al. 2009, SIGIR).

score(d) = Σ w_i / (k + rank_i(d))

RRF is a rank-fusion technique that combines multiple ranked lists without
requiring score calibration across signals.  k=60 is the paper default
(prevents very early ranks from dominating).
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np


def reciprocal_rank_fusion(
    rank_lists: List[List[int]],
    k: int = 60,
    weights: Optional[List[float]] = None,
    top_n: Optional[int] = None,
) -> List[int]:
    """
    Fuse ranked lists using Reciprocal Rank Fusion.

    Args:
        rank_lists: each sub-list is document indices ordered best → worst.
        k: RRF dampening constant (Cormack 2009 recommends 60).
        weights: per-list importance multipliers (default: uniform 1.0).
        top_n: return only top-n documents; None returns all.

    Returns:
        Document indices ordered by descending RRF score.
    """
    if not rank_lists:
        return []

    if weights is None:
        weights = [1.0] * len(rank_lists)

    scores: dict = {}
    for w, ranked in zip(weights, rank_lists):
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + w / (k + rank + 1)

    sorted_docs = sorted(scores, key=lambda d: -scores[d])
    return sorted_docs[:top_n] if top_n is not None else sorted_docs


def scores_to_rank_list(scores: np.ndarray, top_n: Optional[int] = None) -> List[int]:
    """Convert a score array to a list of indices ordered best → worst."""
    ranked = np.argsort(scores)[::-1]
    if top_n is not None:
        ranked = ranked[:top_n]
    return ranked.tolist()
