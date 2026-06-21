"""Lyrics-only baseline: PhoBERT embedding cosine similarity. §9 — Phase 1."""

from __future__ import annotations

from typing import List

import numpy as np


class LyricsOnlyBaseline:
    """Top-K by cosine similarity on pre-normalised PhoBERT embeddings.

    Falls back to audio-only when embeddings are unavailable.
    """

    def __init__(self, catalog) -> None:
        self.catalog = catalog
        self._has_lyrics = catalog.embeddings_normalized is not None

        if not self._has_lyrics:
            # Fallback: audio matrix (normalised)
            raw = catalog.audio_matrix
            norms = np.linalg.norm(raw, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._fallback = raw / norms

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        if self._has_lyrics:
            emb = self.catalog.embeddings_normalized
            q = emb[seed_idx]
            sims = emb @ q
        else:
            q = self._fallback[seed_idx]
            sims = self._fallback @ q

        sims[seed_idx] = -np.inf
        top = np.argsort(sims)[::-1][:top_k]
        return top.tolist()
