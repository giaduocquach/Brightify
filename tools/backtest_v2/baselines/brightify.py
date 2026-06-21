"""Full Brightify engine baseline (v7.2 locked). §9 — Phase 1.

Weights from config.RECO_SONG_WEIGHTS are used by default.
Pass `weights` to override (for ablation / weight optimizer).

The v7.2 reference snapshot is locked by saving weights to the report at
run time; the actual computation always goes through the live recommender.
"""

from __future__ import annotations

from typing import Any, List, Optional


class BrightifyBaseline:
    """Full engine with injectable weights for ablation / optimisation."""

    def __init__(self, catalog: Any, weights: Optional[Any] = None) -> None:
        self.catalog = catalog
        self.weights = weights  # None → use config defaults (v7.2)

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        return self.catalog.recommend_by_song(seed_idx, top_k=top_k, weights=self.weights)
