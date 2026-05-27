"""Full Brightify engine wrapper, with injectable weights. §9 — Phase 1.

v7.2 weights get LOCKED as the reference baseline for gating.
"""

from __future__ import annotations

from typing import Any, Optional


class BrightifyBaseline:
    def __init__(self, recommender: Any = None, weights: Optional[Any] = None):
        self.recommender = recommender
        self.weights = weights

    def recommend(self, query: Any, top_k: int = 10):
        raise NotImplementedError("BrightifyBaseline.recommend — Phase 1")
