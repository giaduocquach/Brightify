"""Lyrics-only baseline (PhoBERT embeddings only). §9 — Phase 1."""

from __future__ import annotations

from typing import Any


class LyricsOnlyBaseline:
    def recommend(self, query: Any, top_k: int = 10):
        raise NotImplementedError("LyricsOnlyBaseline.recommend — Phase 1")
