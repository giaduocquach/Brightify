"""SANITY-ONLY ground truth: V-A proximity floor (tagged engine-derived). §4.1 & §7 — Phase 3.

Engine-derived: use ONLY as a sanity floor, never as headline accuracy.
Tautology risk: V-A is an input to recommend_by_song → cannot be used to rank versions.

Usage: detect catastrophic failures (e.g. random recommendations scoring ~0 here
while the engine scores ~1). If the engine scores low on its OWN input, something
broke severely.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


VA_SANITY_FILE = "var/runtime/backtest/ground_truth/va_sanity_v1.json"

# Proximity threshold: two songs are "VA-relevant" if their Euclidean V-A
# distance is <= this value (√2 ≈ max possible dist in [0,1]² space).
VA_PROXIMITY_THRESHOLD = 0.25  # ~top 25% closest V-A neighbours


def build_va_sanity_gt(
    catalog: Any,
    n_queries: int = 200,
    seed: int = 42,
    threshold: float = VA_PROXIMITY_THRESHOLD,
    save_path: Optional[str] = "var/runtime/backtest/ground_truth/va_sanity_v1.json",
) -> Tuple[Dict[int, List[int]], Dict[str, Any]]:
    """Build engine-derived VA sanity GT.

    For each sampled seed, find all songs within VA_PROXIMITY_THRESHOLD
    Euclidean distance in V-A space. These form the "relevant" set.

    Returns:
        gt_mapping  — {seed_idx: [relevant_idx, ...]}
        meta        — metadata dict (validity, threshold, etc.)
    """
    from tools.backtest_v2.stats import stratified_sample

    queries = stratified_sample(catalog.df, n=n_queries, seed=seed)
    song_va = catalog.song_va  # (n_songs, 2)

    gt_mapping: Dict[int, List[int]] = {}
    for seed_idx in queries:
        q_va = song_va[seed_idx]
        dists = np.sqrt(np.sum((song_va - q_va) ** 2, axis=1))
        relevant = [
            int(i) for i in np.where(dists <= threshold)[0]
            if i != seed_idx
        ]
        if relevant:
            gt_mapping[seed_idx] = relevant

    meta = {
        "validity": "engine-derived",
        "warning": (
            "SANITY FLOOR ONLY — V-A is an input to recommend_by_song. "
            "Do NOT use to rank or compare engine versions. "
            "Only use to detect catastrophic failure (score near 0 = broken engine)."
        ),
        "va_proximity_threshold": threshold,
        "n_queries_sampled": n_queries,
        "n_queries_with_relevant": len(gt_mapping),
        "seed": seed,
    }

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        payload = {
            "meta": meta,
            "gt_mapping": {str(k): v for k, v in gt_mapping.items()},
        }
        with open(save_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"[va_sanity] Saved to {save_path}  ({len(gt_mapping)} queries)")

    return gt_mapping, meta


def load_va_sanity_gt(
    path: str = "var/runtime/backtest/ground_truth/va_sanity_v1.json",
) -> Tuple[Dict[int, List[int]], Dict[str, Any]]:
    """Load previously saved VA sanity GT."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    gt_mapping = {int(k): v for k, v in d["gt_mapping"].items()}
    return gt_mapping, d["meta"]


def evaluate_va_sanity(
    system: Any,
    gt_mapping: Dict[int, List[int]],
    top_k: int = 10,
) -> Dict[str, Any]:
    """Run NDCG@top_k against VA sanity GT.

    Returns result dict with validity='engine-derived' label.
    """
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k

    scores: List[float] = []
    for seed_idx, relevant_list in gt_mapping.items():
        relevant = set(relevant_list)
        ranked = system.recommend(seed_idx, top_k=top_k)
        scores.append(ndcg_at_k(ranked, relevant, top_k))

    mean_val = float(np.mean(scores)) if scores else 0.0
    return {
        "ndcg_at_10_va_sanity": {
            "value": round(mean_val, 6),
            "n": len(scores),
            "validity": "engine-derived",
            "ground_truth": "va_sanity_v1",
            "warning": "SANITY FLOOR ONLY — engine-derived, cannot rank versions",
        }
    }
