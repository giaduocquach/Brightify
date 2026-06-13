"""Pillar E baseline — Brightify with CLAP zero-shot emotion labels.

The catalog is loaded with ENABLE_CLAP_EMOTION forced True/False so that
the same Catalog instance cannot be accidentally shared between the two arms.
"""

from __future__ import annotations

from typing import Any, List, Optional


class PillarEBaseline:
    """BrightifyBaseline backed by a CLAP-emotion-enabled catalog."""

    def __init__(self, catalog: Any, weights: Optional[Any] = None) -> None:
        self.catalog = catalog
        self.weights = weights

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        return self.catalog.recommend_by_song(seed_idx, top_k=top_k, weights=self.weights)
