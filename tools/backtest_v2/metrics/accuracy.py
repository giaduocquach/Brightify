"""Group B accuracy metrics (need external/semi ground truth). §8 — Phase 2+.

Planned: NDCG@K, Precision@K, Recall@K, MAP, MRR, Hit@K.
"""

from __future__ import annotations

from typing import Any, Sequence, Set


def ndcg_at_k(ranked: Sequence[Any], relevant: Set[Any], k: int = 10) -> float:
    raise NotImplementedError("ndcg_at_k — Phase 2")


def precision_at_k(ranked, relevant, k: int = 10) -> float:
    raise NotImplementedError("precision_at_k — Phase 2")


def recall_at_k(ranked, relevant, k: int = 50) -> float:
    raise NotImplementedError("recall_at_k — Phase 2")


def average_precision(ranked, relevant, k: int = 10) -> float:
    raise NotImplementedError("average_precision — Phase 2")


def mrr(ranked, relevant) -> float:
    raise NotImplementedError("mrr — Phase 2")


def hit_at_k(ranked, relevant, k: int = 10) -> float:
    raise NotImplementedError("hit_at_k — Phase 2")
