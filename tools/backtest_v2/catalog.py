"""Wrap MusicRecommender + map original_index for the backtest. Phase 1 stub."""

from __future__ import annotations

from typing import Any


class Catalog:
    """Adapter over core.recommendation_engine.MusicRecommender."""

    def __init__(self, recommender: Any = None):
        self.recommender = recommender

    @classmethod
    def load(cls) -> "Catalog":
        raise NotImplementedError("Catalog.load — Phase 1")
