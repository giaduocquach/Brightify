"""Audio-only baseline (single modality). §9 — Phase 1."""

from __future__ import annotations

from typing import Any


class AudioOnlyBaseline:
    def recommend(self, query: Any, top_k: int = 10):
        raise NotImplementedError("AudioOnlyBaseline.recommend — Phase 1")
