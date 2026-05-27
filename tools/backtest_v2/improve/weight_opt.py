"""Weight optimization for config.RECO_SONG_WEIGHTS. §11.1 — Phase 4.

scipy SLSQP: maximize NDCG@10 (external GT on 80% split),
constraint: ILD_lyrics >= baseline_ild * 0.95, Σw = 1.
Bounds: [0, 0.5] per weight.

Split editorial GT 80% optimize / 20% validate to guard against overfitting.
Paired bootstrap on full GT decides whether to accept new weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


SIGNALS = ["timbral", "rhythmic", "tonal", "lyrics", "va", "emotion", "mood"]


@dataclass
class WeightOptResult:
    optimal_weights: List[float]
    baseline_weights: List[float]
    signals: List[str]
    opt_split: Dict[str, Any]
    val_split: Dict[str, Any]
    optimizer: Dict[str, Any]
    bootstrap: Dict[str, Any]
    verdict: str
    update_config: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ndcg_mean(
    w_norm: np.ndarray,
    catalog: Any,
    gt_mapping: Dict[int, List[int]],
    top_k: int = 10,
) -> float:
    """Mean NDCG@K over all queries in gt_mapping (no bootstrap — just point estimate)."""
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k

    w_list = list(w_norm)
    total = 0.0
    n = 0
    for seed_idx, relevant in gt_mapping.items():
        rel_set = set(relevant)
        ranked = catalog.recommend_by_song(seed_idx, top_k=top_k, weights=w_list)
        total += ndcg_at_k(ranked, rel_set, k=top_k) if ranked else 0.0
        n += 1
    return total / n if n else 0.0


def _ild_lyrics_mean(
    w_norm: np.ndarray,
    catalog: Any,
    seed_indices: List[int],
    top_k: int = 10,
) -> float:
    """Mean ILD_lyrics over a list of seed indices."""
    from tools.backtest_v2.metrics.property import ild_lyrics

    w_list = list(w_norm)
    scores: List[float] = []
    for s in seed_indices:
        recs = catalog.recommend_by_song(s, top_k=top_k, weights=w_list)
        if recs:
            scores.append(ild_lyrics(recs, catalog))
    return float(np.mean(scores)) if scores else 0.0


# ---------------------------------------------------------------------------
# Playlist split
# ---------------------------------------------------------------------------

def split_playlists(
    playlists: List[Any],
    optimize_frac: float = 0.8,
    seed: int = 42,
):
    """Shuffle then split playlists 80/20 optimize/validate."""
    rng = np.random.default_rng(seed)
    idx = np.arange(len(playlists))
    rng.shuffle(idx)
    n_opt = max(1, round(len(playlists) * optimize_frac))
    opt_pls = [playlists[int(i)] for i in sorted(idx[:n_opt].tolist())]
    val_pls = [playlists[int(i)] for i in sorted(idx[n_opt:].tolist())]
    return opt_pls, val_pls


# ---------------------------------------------------------------------------
# Main optimizer
# ---------------------------------------------------------------------------

def optimize_weights(
    catalog: Any,
    playlists: List[Any],
    baseline_ild: float,
    top_k: int = 10,
    max_opt_queries: int = 200,
    verbose: bool = True,
) -> WeightOptResult:
    """SLSQP weight optimization.

    Objective: maximize NDCG@10 on 80% optimize split.
    Constraint: ILD_lyrics >= baseline_ild * 0.95.
    Constraint: Σw = 1.
    Bounds: [0.0, 0.5] per weight.

    After optimization:
    - Validate on held-out 20%.
    - Paired bootstrap (10 000 resample) on full GT.
    - update_config = True iff CI₉₅ of delta is entirely positive.
    """
    from scipy.optimize import minimize
    from tools.backtest_v2.ground_truth.editorial import build_query_gt_mapping
    from tools.backtest_v2.stats import paired_bootstrap
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    import config as cfg

    # --- 80/20 split ---
    opt_pls, val_pls = split_playlists(playlists, optimize_frac=0.8, seed=42)
    opt_gt = build_query_gt_mapping(opt_pls)
    val_gt = build_query_gt_mapping(val_pls)
    full_gt = build_query_gt_mapping(playlists)

    if verbose:
        print(f"[weight_opt] Split: {len(opt_pls)} opt-playlists "
              f"({len(opt_gt)} queries)  |  "
              f"{len(val_pls)} val-playlists ({len(val_gt)} queries)")
        print(f"[weight_opt] Full GT: {len(full_gt)} queries")

    # --- Cap optimizer subset (speed) ---
    opt_seeds = list(opt_gt.keys())
    if len(opt_seeds) > max_opt_queries:
        rng = np.random.default_rng(42)
        chosen = rng.choice(len(opt_seeds), size=max_opt_queries, replace=False)
        opt_seeds_sub = [opt_seeds[int(i)] for i in sorted(chosen.tolist())]
    else:
        opt_seeds_sub = opt_seeds
    opt_gt_sub = {k: opt_gt[k] for k in opt_seeds_sub}

    ild_threshold = baseline_ild * 0.95
    if verbose:
        print(f"[weight_opt] Optimizer uses {len(opt_gt_sub)} queries per eval")
        print(f"[weight_opt] ILD constraint: ILD_lyrics >= {ild_threshold:.6f} "
              f"(= {baseline_ild:.6f} × 0.95)")

    # --- Initial weights ---
    x0 = np.array(cfg.RECO_SONG_WEIGHTS["with_lyrics"], dtype=float)
    x0 /= x0.sum()

    call_count = [0]

    def objective(w: np.ndarray) -> float:
        call_count[0] += 1
        wn = np.clip(w, 0.0, None)
        s = float(wn.sum())
        if s < 1e-10:
            return 0.0
        wn = wn / s
        ndcg = _ndcg_mean(wn, catalog, opt_gt_sub, top_k)
        if verbose and call_count[0] % 20 == 0:
            print(f"  [iter {call_count[0]:3d}] NDCG={ndcg:.5f}  "
                  f"w={np.round(wn, 3).tolist()}")
        return -ndcg

    def con_sum(w: np.ndarray) -> float:
        return float(np.sum(w)) - 1.0

    def con_ild(w: np.ndarray) -> float:
        wn = np.clip(w, 0.0, None)
        s = float(wn.sum())
        if s < 1e-10:
            return -baseline_ild
        wn = wn / s
        ild = _ild_lyrics_mean(wn, catalog, opt_seeds_sub, top_k)
        return ild - ild_threshold

    constraints = [
        {"type": "eq",   "fun": con_sum},
        {"type": "ineq", "fun": con_ild},
    ]
    bounds = [(0.0, 0.5)] * 7

    # NDCG is a discrete metric — default finite-difference eps (1.5e-8) produces
    # zero gradients (tiny perturbations never change rankings).
    # eps=0.05 shifts each weight by ~5%, reliably changing which songs rank.
    # maxiter=15: for a 7-dim problem SLSQP typically converges in <15 steps.
    # With 30 queries per eval, each major iteration costs ~1s (fast).
    # Full validation uses all GT queries after optimization.
    SLSQP_OPTS = {"maxiter": 15, "ftol": 1e-4, "disp": False, "eps": 0.05}

    if verbose:
        print(f"\n[weight_opt] Running SLSQP (maxiter=15, ftol=1e-4, eps=0.05)…")

    # Multi-start: baseline weights + lyrics-upweighted init.
    starts = [x0]
    x1 = np.array([0.08, 0.07, 0.06, 0.50, 0.12, 0.12, 0.05], dtype=float)
    x1 /= x1.sum()
    starts.append(x1)

    best_val = np.inf
    best_res = None
    for i_start, x_init in enumerate(starts):
        if verbose:
            print(f"  [start {i_start+1}/{len(starts)}] "
                  f"x0={np.round(x_init, 3).tolist()}")
        r = minimize(
            objective, x_init,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options=SLSQP_OPTS,
        )
        if verbose:
            print(f"    → success={r.success}  fun={r.fun:.6f}  "
                  f"msg={r.message!r}")
        if r.fun < best_val:
            best_val = r.fun
            best_res = r

    res = best_res
    w_opt = np.clip(res.x, 0.0, 0.5)
    w_opt /= w_opt.sum()

    if verbose:
        print(f"[weight_opt] Done: success={res.success}  calls={call_count[0]}")
        print(f"[weight_opt] msg: {res.message!r}")
        print(f"[weight_opt] Optimal w: {np.round(w_opt, 4).tolist()}")

    # --- Full eval on both splits ---
    if verbose:
        print("\n[weight_opt] Evaluating on full splits…")
    opt_ndcg   = _ndcg_mean(w_opt, catalog, opt_gt, top_k)
    base_opt   = _ndcg_mean(x0,    catalog, opt_gt, top_k)
    val_ndcg   = _ndcg_mean(w_opt, catalog, val_gt, top_k)
    base_val   = _ndcg_mean(x0,    catalog, val_gt, top_k)

    # --- Paired bootstrap on full GT ---
    if verbose:
        print("[weight_opt] Paired bootstrap on full GT (10 000 resamples)…")
    ndcg_base_pq: List[float] = []
    ndcg_new_pq:  List[float] = []
    w_opt_list = list(w_opt)
    x0_list    = list(x0)
    for seed_idx, relevant in full_gt.items():
        rel_set = set(relevant)
        rb = catalog.recommend_by_song(seed_idx, top_k=top_k, weights=x0_list)
        rn = catalog.recommend_by_song(seed_idx, top_k=top_k, weights=w_opt_list)
        ndcg_base_pq.append(ndcg_at_k(rb, rel_set, top_k) if rb else 0.0)
        ndcg_new_pq.append(ndcg_at_k(rn, rel_set, top_k) if rn else 0.0)

    delta, ci_low, ci_high = paired_bootstrap(ndcg_base_pq, ndcg_new_pq)
    update_config = bool(ci_low > 0 and delta > 0)

    verdict = (
        "IMPROVEMENT CONFIRMED: CI₉₅ > 0 and delta > 0 → update config.RECO_SONG_WEIGHTS"
        if update_config else
        "NO SIGNIFICANT IMPROVEMENT: CI₉₅ contains 0 or delta ≤ 0 → weights already near-optimal, keep v7.2"
    )

    if verbose:
        print(f"\n[weight_opt] Bootstrap result:")
        print(f"  baseline mean NDCG@10 = {float(np.mean(ndcg_base_pq)):.5f}")
        print(f"  optimal  mean NDCG@10 = {float(np.mean(ndcg_new_pq)):.5f}")
        print(f"  delta = {delta:+.5f}  CI95=[{ci_low:+.5f}, {ci_high:+.5f}]")
        print(f"  update_config = {update_config}")
        print(f"  verdict: {verdict}")

    return WeightOptResult(
        optimal_weights=w_opt.tolist(),
        baseline_weights=x0.tolist(),
        signals=SIGNALS,
        opt_split={
            "n_playlists": len(opt_pls),
            "n_queries": len(opt_gt),
            "ndcg_at_10_baseline": float(base_opt),
            "ndcg_at_10_optimal":  float(opt_ndcg),
            "delta": float(opt_ndcg - base_opt),
        },
        val_split={
            "n_playlists": len(val_pls),
            "n_queries": len(val_gt),
            "ndcg_at_10_baseline": float(base_val),
            "ndcg_at_10_optimal":  float(val_ndcg),
            "delta": float(val_ndcg - base_val),
        },
        optimizer={
            "success": bool(res.success),
            "message": str(res.message),
            "n_calls": call_count[0],
            "n_opt_queries_used": len(opt_gt_sub),
        },
        bootstrap={
            "n_queries": len(ndcg_base_pq),
            "n_boots": 10_000,
            "mean_ndcg_at_10_baseline": float(np.mean(ndcg_base_pq)),
            "mean_ndcg_at_10_optimal":  float(np.mean(ndcg_new_pq)),
            "delta": float(delta),
            "ci95": [float(ci_low), float(ci_high)],
        },
        verdict=verdict,
        update_config=update_config,
    )
