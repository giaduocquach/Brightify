"""Group A+ operational metrics: latency p50/p95/p99 per method. §8 — Phase 1."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Sequence

import numpy as np


def _timed_call(fn: Callable, *args, **kwargs) -> float:
    """Return wall-clock time in milliseconds for a single call."""
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000.0


def latency_percentiles(
    fn: Callable,
    call_args: Sequence,
    n: int = 200,
    warmup: int = 3,
) -> Dict[str, float]:
    """Return {'p50':..,'p95':..,'p99':..} in ms.

    Args:
        fn: callable to benchmark (e.g. recommender.recommend_by_song)
        call_args: list of argument tuples — cycled over n measurements.
        n: number of timed calls.
        warmup: unjitted runs before measurement starts.
    """
    if not call_args:
        return {'p50': 0.0, 'p95': 0.0, 'p99': 0.0}

    # Warm-up
    for i in range(warmup):
        args = call_args[i % len(call_args)]
        if not isinstance(args, (tuple, list)):
            args = (args,)
        fn(*args)

    times_ms: List[float] = []
    for i in range(n):
        args = call_args[i % len(call_args)]
        if not isinstance(args, (tuple, list)):
            args = (args,)
        times_ms.append(_timed_call(fn, *args))

    arr = np.array(times_ms)
    return {
        'p50': float(np.percentile(arr, 50)),
        'p95': float(np.percentile(arr, 95)),
        'p99': float(np.percentile(arr, 99)),
    }


def measure_all_methods(catalog: Any, seed_indices: Sequence[int], n: int = 200) -> Dict[str, Dict[str, float]]:
    """Measure latency for all supported recommend methods.

    Uses a fixed set of seed_indices (cycled) for reproducibility.
    Methods that require external inputs (image URL) use a safe fallback.
    """
    rec = catalog.rec
    seeds = list(seed_indices[:50])  # up to 50 distinct seeds to cycle
    if not seeds:
        seeds = [0]

    # Build call_args for each method
    results: Dict[str, Dict[str, float]] = {}

    # recommend_by_song
    results['recommend_by_song'] = latency_percentiles(
        lambda idx: rec.recommend_by_song(idx, top_k=10),
        seeds, n=n,
    )

    # recommend_by_colors
    colors = ['#d2c317', '#4a90d9', '#c0392b', '#27ae60', '#8e44ad']
    results['recommend_by_colors'] = latency_percentiles(
        lambda c: rec.recommend_by_colors(c, top_k=10),
        colors, n=n,
    )

    return results
