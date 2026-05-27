"""Weight optimization for config.RECO_SONG_WEIGHTS. §11.1 — Phase 4.

scipy.optimize SLSQP, objective = maximize NDCG@10 (external GT),
constraint = ILD_lyrics >= baseline * 0.95. Requires editorial_playlists_v1.
Split 80/20 optimize/validate to guard against overfitting.
"""

from __future__ import annotations

from typing import Any


def optimize_weights(runner: Any, ground_truth: Any, baseline_ild: float):
    raise NotImplementedError("optimize_weights — Phase 4")
