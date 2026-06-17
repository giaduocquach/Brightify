"""Pillar B baseline — Brightify with SimCSE lyrics embeddings.

Loads a separate Catalog backed by EMBEDDINGS_FILE_PILLAR_B.
The recommendation engine is identical to BrightifyBaseline; only the
lyrics embedding matrix differs (SimCSE vs PhoBERT).
"""

from __future__ import annotations

from typing import Any, List, Optional


class PillarBBaseline:
    """Brightify engine using Pillar B (SimCSE dangvantuan/vietnamese-embedding) embeddings."""

    def __init__(self, catalog: Any, weights: Optional[Any] = None) -> None:
        self.catalog = catalog
        self.weights = weights

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        return self.catalog.recommend_by_song(seed_idx, top_k=top_k, weights=self.weights)
