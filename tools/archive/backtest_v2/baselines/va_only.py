"""V-A only baseline: nearest neighbours by Euclidean distance in valence-arousal space. §9."""

from __future__ import annotations

from typing import List

import numpy as np


class VAOnlyBaseline:
    """Top-K by smallest Euclidean distance in the 2-dim V-A space."""

    def __init__(self, catalog) -> None:
        self.catalog = catalog

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        q = self.catalog.song_va[seed_idx]
        dists = np.linalg.norm(self.catalog.song_va - q, axis=1)
        dists[seed_idx] = np.inf
        top = np.argsort(dists)[:top_k]
        return top.tolist()
