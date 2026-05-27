"""Pillar C baseline — brightify with ENABLE_RRF=True + optional cross-encoder.

Monkey-patches the module-level ENABLE_RRF / ENABLE_RERANKER flags so the
same catalog instance can be tested with both settings within one process.
"""

from __future__ import annotations

from typing import Any, List, Optional


class PillarCBaseline:
    """BrightifyBaseline with RRF hybrid retrieval active."""

    def __init__(
        self,
        catalog: Any,
        weights: Optional[Any] = None,
        enable_reranker: bool = False,
    ) -> None:
        self.catalog = catalog
        self.weights = weights
        self.enable_reranker = enable_reranker

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        import core.recommendation_engine as _eng
        old_rrf = _eng.ENABLE_RRF
        old_rr = _eng.ENABLE_RERANKER
        _eng.ENABLE_RRF = True
        _eng.ENABLE_RERANKER = self.enable_reranker
        try:
            return self.catalog.recommend_by_song(seed_idx, top_k=top_k, weights=self.weights)
        finally:
            _eng.ENABLE_RRF = old_rrf
            _eng.ENABLE_RERANKER = old_rr
