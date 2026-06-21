"""Random baseline (lower bound). §9 — Phase 1.

Samples top_k songs uniformly at random from the catalog, excluding seed.
"""

from __future__ import annotations

from typing import List

import numpy as np


class RandomBaseline:
    """Recommend top_k uniformly random songs (excluding seed)."""

    def __init__(self, catalog, seed: int = 42) -> None:
        self.catalog = catalog
        self._rng = np.random.default_rng(seed)

    def recommend(self, seed_idx: int, top_k: int = 10) -> List[int]:
        indices = list(range(self.catalog.n))
        indices.pop(seed_idx)  # exclude seed
        chosen = self._rng.choice(indices, size=min(top_k, len(indices)), replace=False)
        return chosen.tolist()
