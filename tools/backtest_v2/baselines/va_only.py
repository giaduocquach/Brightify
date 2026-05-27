"""V-A only baseline (Russell Circumplex proximity only). §9 — Phase 1."""

from __future__ import annotations

from typing import Any


class VAOnlyBaseline:
    def recommend(self, query: Any, top_k: int = 10):
        raise NotImplementedError("VAOnlyBaseline.recommend — Phase 1")
