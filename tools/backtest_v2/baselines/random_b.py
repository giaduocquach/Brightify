"""Random baseline (lower bound). §9 — Phase 1."""

from __future__ import annotations

from typing import Any


class RandomBaseline:
    def recommend(self, query: Any, top_k: int = 10):
        raise NotImplementedError("RandomBaseline.recommend — Phase 1")
