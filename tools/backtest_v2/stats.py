"""Stratified sampling + paired bootstrap CI. §12 — Phase 1.

Stratification is over mood_quadrant. seed=42 throughout.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _extract_quadrant(value: Any) -> str:
    """Return 'Q1'/'Q2'/'Q3'/'Q4' from values like 'Q3: Sad/Depressed'."""
    if pd.isna(value):
        return 'Q3'
    s = str(value).strip()
    if s[:2] in ('Q1', 'Q2', 'Q3', 'Q4'):
        return s[:2]
    return 'Q3'


def stratified_sample(
    df: pd.DataFrame,
    n: int = 500,
    seed: int = 42,
) -> List[int]:
    """Proportional stratified sample of row indices by mood_quadrant.

    Returns a list of original_index integers (0-based row positions).
    Q2 may have fewer than its proportional share when the stratum is tiny.
    """
    rng = np.random.default_rng(seed)

    if 'mood_quadrant' not in df.columns:
        # Fallback: simple random
        return rng.choice(len(df), size=min(n, len(df)), replace=False).tolist()

    strata: Dict[str, List[int]] = {}
    for idx, val in enumerate(df['mood_quadrant']):
        q = _extract_quadrant(val)
        strata.setdefault(q, []).append(idx)

    total = len(df)
    selected: List[int] = []
    for q in sorted(strata.keys()):
        indices = strata[q]
        quota = max(1, round(n * len(indices) / total))
        quota = min(quota, len(indices))
        chosen = rng.choice(indices, size=quota, replace=False)
        selected.extend(chosen.tolist())

    # Trim or top-up to exactly n (trim from the largest stratum)
    if len(selected) > n:
        rng.shuffle(selected)
        selected = selected[:n]
    elif len(selected) < n:
        remaining = list(set(range(total)) - set(selected))
        if remaining:
            extra = rng.choice(
                remaining,
                size=min(n - len(selected), len(remaining)),
                replace=False,
            )
            selected.extend(extra.tolist())

    return selected


def quadrant_breakdown(df: pd.DataFrame, indices: List[int]) -> Dict[str, int]:
    """Count how many of the sampled indices fall in each quadrant."""
    counts: Dict[str, int] = {}
    for idx in indices:
        q = _extract_quadrant(df['mood_quadrant'].iloc[idx])
        counts[q] = counts.get(q, 0) + 1
    return counts


def paired_bootstrap(
    a: Sequence[float],
    b: Sequence[float],
    n_boot: int = 10_000,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Paired bootstrap for (b - a).

    Returns (delta_mean, ci_low, ci_high) at 95% level.
    Both sequences must be the same length (matched pairs).
    """
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    diffs = arr_b - arr_a
    observed = float(np.mean(diffs))

    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_boot)
    n = len(diffs)
    for i in range(n_boot):
        sample = rng.choice(diffs, size=n, replace=True)
        boot_means[i] = sample.mean()

    ci_low = float(np.percentile(boot_means, 2.5))
    ci_high = float(np.percentile(boot_means, 97.5))
    return observed, ci_low, ci_high


def ci_from_samples(
    values: Sequence[float],
    n_boot: int = 10_000,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Bootstrap CI for the mean of a single sequence.

    Returns (mean, ci_low, ci_high).
    """
    arr = np.asarray(values, dtype=float)
    observed = float(np.mean(arr))
    rng = np.random.default_rng(seed)
    n = len(arr)
    boot_means = np.array([
        rng.choice(arr, size=n, replace=True).mean()
        for _ in range(n_boot)
    ])
    ci_low = float(np.percentile(boot_means, 2.5))
    ci_high = float(np.percentile(boot_means, 97.5))
    return observed, ci_low, ci_high


def cluster_paired_bootstrap(
    scores_a: Dict[int, float],
    scores_b: Dict[int, float],
    clusters: List[List[int]],
    n_boot: int = 10_000,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Cluster bootstrap CI: resample playlists, not individual queries.

    Corrects pseudo-replication when multiple queries share the same playlist.
    clusters: list of seed-idx lists, one per playlist.
    Returns (observed_delta, ci_low, ci_high) at 95% level.
    """
    cluster_data: List[np.ndarray] = []
    for cluster_seeds in clusters:
        diffs = [
            scores_b[s] - scores_a[s]
            for s in cluster_seeds
            if s in scores_a and s in scores_b
        ]
        if diffs:
            cluster_data.append(np.array(diffs, dtype=float))

    if not cluster_data:
        return 0.0, 0.0, 0.0

    all_diffs = np.concatenate(cluster_data)
    observed = float(np.mean(all_diffs))

    rng = np.random.default_rng(seed)
    M = len(cluster_data)
    boot_means = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, M, size=M)
        resampled = np.concatenate([cluster_data[j] for j in idx])
        boot_means[i] = resampled.mean()

    ci_low  = float(np.percentile(boot_means, 2.5))
    ci_high = float(np.percentile(boot_means, 97.5))
    return observed, ci_low, ci_high
