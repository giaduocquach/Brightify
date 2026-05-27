"""Audio-only baseline: cosine similarity on Essentia audio features. §9 — Phase 1."""

from __future__ import annotations

from typing import List

import numpy as np


class AudioOnlyBaseline:
    """Top-K by cosine similarity on the normalised audio feature matrix."""

    def __init__(self, catalog) -> None:
        self.catalog = catalog
        # Pre-normalise rows once
        raw = catalog.audio_matrix
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._norm_matrix = raw / norms

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        q = self._norm_matrix[seed_idx]
        sims = self._norm_matrix @ q
        sims[seed_idx] = -np.inf
        top = np.argsort(sims)[::-1][:top_k]
        return top.tolist()
