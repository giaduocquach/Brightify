"""Group A property metrics (no ground truth needed). §8 Group A — Phase 1.

Planned: ILD (4 spaces), Coverage, Artist Gini, MoodCoherence, TempoCoherence,
ColorCoherence, Calibration, similar-song symmetry, serendipity_proxy.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence


def intra_list_diversity(recs: Sequence[Any], space: str) -> float:
    raise NotImplementedError("intra_list_diversity — Phase 1")


def catalog_coverage(all_recs: Sequence[Sequence[Any]], n_catalog: int) -> float:
    raise NotImplementedError("catalog_coverage — Phase 1")


def artist_gini(all_recs: Sequence[Sequence[Any]]) -> float:
    raise NotImplementedError("artist_gini — Phase 1")


def mood_coherence(recs: Sequence[Any]) -> float:
    raise NotImplementedError("mood_coherence — Phase 1")


def tempo_coherence(recs: Sequence[Any]) -> float:
    raise NotImplementedError("tempo_coherence — Phase 1")


def color_coherence(recs: Sequence[Any]) -> float:
    raise NotImplementedError("color_coherence — Phase 1")


def calibration(recs: Sequence[Any], query: Any) -> float:
    raise NotImplementedError("calibration — Phase 1")


def similar_song_symmetry(catalog: Any, sample: Sequence[Any]) -> float:
    """Salvaged idea from legacy backtest: A in sim(B) ⇔ B in sim(A)."""
    raise NotImplementedError("similar_song_symmetry — Phase 1")


def serendipity_proxy(recs: Sequence[Any], query: Any) -> float:
    raise NotImplementedError("serendipity_proxy — Phase 1")
