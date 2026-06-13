"""Tune recommend_by_song fusion weights toward MUSICAL similarity.

Objective: maximise NDCG@10 against the MUSICAL-similarity GT
(var/runtime/backtest/ground_truth/similar_musical_gt_v1.json — built by
tools/backtest_v2/ground_truth/similar_musical_gt.py, an LLM judge that scores
musical/acoustic resemblance with lyrics demoted to a minor cue).

Design (reuses the proven Phase-4 machinery, NON-invasively):
- 8-signal MERT vector [timbral, rhythmic, tonal, lyrics, va, emotion, mood, mert].
- Freeze the redundant/degenerate signals to 0:
    timbral/rhythmic/tonal (idx 0,1,2) — Essentia scalars degenerate (already 0);
    emotion (idx 5) — redundant audio→colour→emotion re-encoding of V-A;
    mood   (idx 6) — noisy same-label bonus.
  Optimise ONLY lyrics (3), va (4), mert (7).
- SLSQP, Σw=1, ILD_lyrics >= 0.95×baseline (diversity floor), per-axis bounds.
- Per-seed paired bootstrap (each seed = independent query) for the CI gate.

Reuses tools.backtest_v2.improve.weight_opt._ndcg_mean / _ild_lyrics_mean,
tools.backtest_v2.stats.cluster_paired_bootstrap, metrics.accuracy.ndcg_at_k.

Does NOT edit config.py — prints the verdict + optimal weights for human review.

Usage:
    python -m tools.tune_musical_weights [--max-opt-queries N]
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

# Signal layout for the 8-dim MERT weight vector.
SIGNALS = ["timbral", "rhythmic", "tonal", "lyrics", "va", "emotion", "mood", "mert"]
FREEZE_IDX = [0, 1, 2, 5, 6]          # everything except lyrics(3), va(4), mert(7)
# Per-axis bounds for the FREE signals (let MERT dominate if the GT supports it).
BOUNDS = [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.60),
          (0.0, 0.35), (0.0, 0.0), (0.0, 0.0), (0.0, 0.90)]


def _zero_renorm(v: np.ndarray) -> np.ndarray:
    v = np.array(v, dtype=float)
    for i in FREEZE_IDX:
        v[i] = 0.0
    s = v.sum()
    return v / s if s > 0 else v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-opt-queries", type=int, default=200)
    args = ap.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    import config as cfg
    from scipy.optimize import minimize
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.improve.weight_opt import _ndcg_mean, _ild_lyrics_mean
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.stats import cluster_paired_bootstrap
    from tools.backtest_v2.ground_truth.similar_musical_gt import (
        load_similar_musical_gt, build_query_gt_mapping, GT_FILE,
    )

    if not os.path.exists(GT_FILE):
        print(f"[tune] Musical GT not found: {GT_FILE}")
        print("[tune] Run: python -m tools.backtest_v2.ground_truth.similar_musical_gt")
        return 1

    print("[tune] Loading catalog…")
    catalog = Catalog.load()

    gt = load_similar_musical_gt()
    gt_mapping = build_query_gt_mapping(gt)
    print(f"[tune] Musical GT: {len(gt)} seeds, {len(gt_mapping)} with ≥1 relevant")
    if len(gt_mapping) < 8:
        print("[tune] STOP: <8 usable seeds — GT too small for a meaningful tune. Build more seeds.")
        return 1

    # --- Baseline (current production) weights ---
    x0 = np.array(cfg.RECO_SONG_WEIGHTS_MERT["with_lyrics"], dtype=float)
    x0 = x0 / x0.sum()

    # --- 80/20 seed split (each seed is an independent query) ---
    seeds = list(gt_mapping.keys())
    rng = np.random.default_rng(42)
    rng.shuffle(seeds)
    n_opt = max(4, round(len(seeds) * 0.8))
    opt_seeds = seeds[:n_opt]
    val_seeds = seeds[n_opt:]
    opt_gt = {s: gt_mapping[s] for s in opt_seeds}
    val_gt = {s: gt_mapping[s] for s in val_seeds}
    if len(opt_gt) > args.max_opt_queries:
        sub = [opt_seeds[i] for i in sorted(rng.choice(len(opt_seeds), args.max_opt_queries, replace=False))]
        opt_gt = {s: gt_mapping[s] for s in sub}
    print(f"[tune] split: {len(opt_gt)} optimise / {len(val_gt)} validate")

    baseline_ild = _ild_lyrics_mean(x0, catalog, list(opt_gt.keys()), top_k=10)
    ild_floor = baseline_ild * 0.95
    print(f"[tune] baseline ILD_lyrics={baseline_ild:.5f}  floor={ild_floor:.5f}")

    calls = [0]

    def objective(w):
        calls[0] += 1
        wn = np.clip(w, 0.0, None)
        s = float(wn.sum())
        if s < 1e-10:
            return 0.0
        wn = wn / s
        ndcg = _ndcg_mean(wn, catalog, opt_gt, top_k=10)
        if calls[0] % 20 == 0:
            print(f"  [iter {calls[0]:3d}] NDCG={ndcg:.5f} w={np.round(wn,3).tolist()}")
        return -ndcg

    def con_sum(w):
        return float(np.sum(w)) - 1.0

    def con_ild(w):
        wn = np.clip(w, 0.0, None)
        s = float(wn.sum())
        if s < 1e-10:
            return -baseline_ild
        return _ild_lyrics_mean(wn / s, catalog, list(opt_gt.keys()), top_k=10) - ild_floor

    constraints = [{"type": "eq", "fun": con_sum}, {"type": "ineq", "fun": con_ild}]
    opts = {"maxiter": 20, "ftol": 1e-4, "disp": False, "eps": 0.05}

    # Multistart: current baseline + a MERT-heavy init (the musical hypothesis).
    starts = [
        _zero_renorm(x0),
        _zero_renorm(np.array([0, 0, 0, 0.15, 0.05, 0, 0, 0.80], dtype=float)),
        _zero_renorm(np.array([0, 0, 0, 0.30, 0.05, 0, 0, 0.65], dtype=float)),
    ]
    best = None
    for i, xi in enumerate(starts):
        print(f"  [start {i+1}/{len(starts)}] x0={np.round(xi,3).tolist()}")
        r = minimize(objective, xi, method="SLSQP", bounds=BOUNDS,
                     constraints=constraints, options=opts)
        print(f"    → success={r.success} fun={r.fun:.6f}")
        if best is None or r.fun < best.fun:
            best = r

    w_opt = _zero_renorm(np.clip(best.x, 0.0, None))

    # --- Reference points on the FULL GT ---
    def ndcg_full(w):
        return _ndcg_mean(np.array(w, float), catalog, gt_mapping, top_k=10)

    ref = {
        "baseline (current)": (x0, ndcg_full(x0)),
        "mert_only":   ([0,0,0,0,0,0,0,1.0],  ndcg_full([0,0,0,0,0,0,0,1.0])),
        "lyrics_only": ([0,0,0,1.0,0,0,0,0],  ndcg_full([0,0,0,1.0,0,0,0,0])),
        "OPTIMAL":     (w_opt, ndcg_full(w_opt)),
    }

    # --- Per-seed paired bootstrap: baseline vs optimal (full GT) ---
    sc_base, sc_new = {}, {}
    for s, rel in gt_mapping.items():
        rs = set(rel)
        rb = catalog.recommend_by_song(s, top_k=10, weights=list(x0))
        rn = catalog.recommend_by_song(s, top_k=10, weights=list(w_opt))
        sc_base[s] = ndcg_at_k(rb, rs, 10) if rb else 0.0
        sc_new[s]  = ndcg_at_k(rn, rs, 10) if rn else 0.0
    clusters = [[s] for s in gt_mapping]          # each seed independent
    delta, ci_low, ci_high = cluster_paired_bootstrap(sc_base, sc_new, clusters)
    val_base = _ndcg_mean(x0,    catalog, val_gt, 10) if val_gt else float("nan")
    val_opt  = _ndcg_mean(w_opt, catalog, val_gt, 10) if val_gt else float("nan")
    update = bool(ci_low > 0 and delta > 0)

    print("\n" + "=" * 64)
    print("  MUSICAL-SIMILARITY WEIGHT TUNE")
    print("=" * 64)
    print(f"  {'Signal':<10} {'baseline':>10} {'OPTIMAL':>10} {'Δ':>9}")
    print("  " + "-" * 42)
    for i, s in enumerate(SIGNALS):
        print(f"  {s:<10} {x0[i]:>10.4f} {w_opt[i]:>10.4f} {w_opt[i]-x0[i]:>+9.4f}")
    print("\n  NDCG@10 on full musical GT:")
    for name, (_, v) in ref.items():
        print(f"    {name:<20} = {v:.5f}")
    if val_gt:
        print(f"\n  Held-out validate split ({len(val_gt)} seeds): "
              f"baseline={val_base:.5f}  optimal={val_opt:.5f}  Δ={val_opt-val_base:+.5f}")
    print(f"\n  Paired bootstrap (N={len(gt_mapping)} seeds, 10k resamples):")
    print(f"    Δ NDCG@10 = {delta:+.5f}  CI95=[{ci_low:+.5f}, {ci_high:+.5f}]")
    status = "✅ IMPROVEMENT (CI95>0)" if update else "❌ NO SIGNIFICANT IMPROVEMENT"
    print(f"\n  {status}")
    print(f"  → suggested RECO_SONG_WEIGHTS_MERT['with_lyrics'] = "
          f"[{', '.join(f'{w:.4f}' for w in w_opt)}]")
    print("=" * 64)
    print("\n[tune] config.py NOT modified — apply manually after review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
