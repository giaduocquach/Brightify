"""Pillar F baseline — Brightify with KG embeddings + VN context active."""

from __future__ import annotations

from typing import Any, List, Optional


class PillarFBaseline:
    """BrightifyBaseline backed by a KG+context-enabled catalog."""

    def __init__(self, catalog: Any, weights: Optional[Any] = None) -> None:
        self.catalog = catalog
        self.weights = weights

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        return self.catalog.recommend_by_song(seed_idx, top_k=top_k, weights=self.weights)
