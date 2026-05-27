"""Stratified sampling + paired bootstrap + CI. Phase 1 stub."""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple


def stratified_sample(items: Sequence[Any], strata: Sequence[Any], n: int, seed: int = 42) -> List[Any]:
    raise NotImplementedError("stratified_sample — Phase 1")


def paired_bootstrap(a: Sequence[float], b: Sequence[float], n_boot: int = 10000, seed: int = 42) -> Tuple[float, float, float]:
    """Return (delta_mean, ci_low, ci_high) for b - a. Phase 1 stub."""
    raise NotImplementedError("paired_bootstrap — Phase 1")
