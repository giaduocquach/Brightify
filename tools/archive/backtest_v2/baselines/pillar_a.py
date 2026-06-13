"""Pillar A baseline — brightify with MERT signal #8 enabled.

Loads the engine with MERT embeddings and ENABLE_MERT=True so that
_fast_rank() uses the 8-signal RECO_SONG_WEIGHTS_MERT fusion.
"""

from __future__ import annotations

from typing import Any, List, Optional


class PillarABaseline:
    """BrightifyBaseline with MERT signal active."""

    def __init__(self, catalog: Any, weights: Optional[Any] = None) -> None:
        self.catalog = catalog
        self.weights = weights

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        return self.catalog.recommend_by_song(seed_idx, top_k=top_k, weights=self.weights)
