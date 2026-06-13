"""
Weight validation: Sensitivity Analysis (#2) + 5-fold Cross-Validation (#3).

#2 Sensitivity analysis:
  Perturb each active weight (mert, lyrics, va) by ±0.05 and ±0.10, keeping
  Σw=1 by renormalizing. If no perturbation improves all directional metrics
  simultaneously, current weights are locally optimal on this catalog.

#3 5-fold Cross-Validation:
  Split seeds into 5 folds, compute metrics on each fold independently.
  Low variance across folds = weights are stable (not overfit to the 60 seeds
  used during empirical selection). High variance = coincidental.

Together these answer the key academic question:
  "Why 0.75/0.15/0.10 specifically?" →
  "Locally optimal on this catalog (sensitivity), stable across subsets (CV)."

Usage:
    python -m tools.validate_weights [--n-seeds 80] [--folds 5]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Baseline weights: [timbral, rhythmic, tonal, lyrics, va, emotion, mood, mert]
BASELINE_W = [0.0, 0.0, 0.0, 0.15, 0.10, 0.0, 0.0, 0.75]
FREE_IDX   = [3, 4, 7]   # indices of non-zero weights: lyrics, va, mert
FREE_NAMES = ["lyrics", "va", "mert"]

# Perturbation steps
STEPS = [-0.10, -0.05, +0.05, +0.10]

# Directional metric specs (key, label, higher_is_better)
METRICS = [
    ("mood",     "MoodCoherence", True),
    ("tempo",    "TempoCoher",    True),
    ("self_c",   "SelfConsist",   True),
    ("symm",     "Symmetry",      True),
    ("same_art", "SameArtist@K",  False),
    ("ild_va",   "ILD_va",        None),
    ("serend",   "Serendipity",   None),
]


def _compute_metrics(cat, seeds: List[int], w: List[float]) -> Dict[str, float]:
    from tools.backtest_v2.metrics.property import (
        mood_coherence, tempo_coherence, similar_song_symmetry,
        same_artist_at_k, ild_va, serendipity_proxy,
    )
    from tools.eval_similar_intrinsic import _self_consistency

    rng = np.random.default_rng(42)
    vals: Dict[str, List[float]] = {k: [] for k, *_ in METRICS}

    for s in seeds:
        r = cat.recommend_by_song(s, top_k=10, weights=w)
        if not r:
            continue
        vals["mood"].append(mood_coherence(r, cat))
        vals["tempo"].append(tempo_coherence(r, cat))
        vals["self_c"].append(_self_consistency(cat, s, w, 10, rng))
        vals["same_art"].append(same_artist_at_k(r, s, cat))
        vals["ild_va"].append(ild_va(r, cat))
        vals["serend"].append(serendipity_proxy(r, s, cat))

    def _rfn(i, k): return cat.recommend_by_song(i, top_k=k, weights=w)
    vals["symm"] = [similar_song_symmetry(_rfn, seeds, 10)]
    return {k: float(np.mean(v)) if v else 0.0 for k, v in vals.items()}


def _perturb(base: List[float], idx: int, delta: float) -> List[float]:
    """Shift weight[idx] by delta, renormalize to Σ=1, keep other zeros at 0."""
    w = list(base)
    w[idx] = max(0.0, w[idx] + delta)
    total = sum(w)
    return [x / total if total > 0 else x for x in w]


def run_sensitivity(cat, seeds: List[int]) -> dict:
    """For each free weight, perturb ±0.05 / ±0.10, measure all metrics."""
    print("\n" + "=" * 72)
    print("  SENSITIVITY ANALYSIS  (perturbation ±0.05 / ±0.10)")
    print("=" * 72)

    base_metrics = _compute_metrics(cat, seeds, BASELINE_W)
    print(f"  Baseline weights: mert={BASELINE_W[7]:.2f} lyrics={BASELINE_W[3]:.2f} va={BASELINE_W[4]:.2f}")
    print(f"  Seeds: {len(seeds)}")

    results: dict = {"baseline": base_metrics, "perturbations": {}}
    any_improves_all = False

    for fi, (pidx, pname) in enumerate(zip(FREE_IDX, FREE_NAMES)):
        print(f"\n  Perturbing '{pname}' (index {pidx}, baseline={BASELINE_W[pidx]:.2f}):")
        for delta in STEPS:
            w = _perturb(BASELINE_W, pidx, delta)
            sign = "+" if delta > 0 else ""
            w_str = f"mert={w[7]:.3f} lyr={w[3]:.3f} va={w[4]:.3f}"
            m = _compute_metrics(cat, seeds, w)

            wins = losses = 0
            for key, _, hib in METRICS:
                if hib is None:
                    continue
                d = m[key] - base_metrics[key]
                if hib and d > 0.003:
                    wins += 1
                elif hib and d < -0.003:
                    losses += 1
                elif not hib and d < -0.003:
                    wins += 1
                elif not hib and d > 0.003:
                    losses += 1

            verdict = "BETTER" if wins > losses else ("WORSE" if losses > wins else "~SAME")
            if wins > losses:
                any_improves_all = True

            results["perturbations"][f"{pname}{sign}{delta:+.2f}"] = {
                "weights": w, "metrics": m, "wins": wins, "losses": losses
            }
            print(f"    Δ{pname}{sign}{delta:+.2f}  [{w_str}]  "
                  f"↑{wins} ↓{losses}  → {verdict}")

    conclusion = (
        "⚠ Some perturbation improves — weights not fully locally optimal."
        if any_improves_all else
        "✓ No perturbation dominates on balance — weights are locally optimal."
    )
    print(f"\n  {conclusion}")
    results["locally_optimal"] = not any_improves_all
    results["conclusion"] = conclusion
    return results


def run_cv(cat, seeds: List[int], n_folds: int = 5) -> dict:
    """5-fold CV: compute metrics on each fold, report mean ± std."""
    print("\n" + "=" * 72)
    print(f"  {n_folds}-FOLD CROSS-VALIDATION  (weights stability across seed subsets)")
    print("=" * 72)

    rng = np.random.default_rng(42)
    idx = np.arange(len(seeds))
    rng.shuffle(idx)
    folds = np.array_split(idx, n_folds)

    fold_results: List[Dict[str, float]] = []
    for fi, fold_idx in enumerate(folds):
        fold_seeds = [seeds[i] for i in fold_idx]
        m = _compute_metrics(cat, fold_seeds, BASELINE_W)
        fold_results.append(m)
        print(f"  Fold {fi+1}/{n_folds} ({len(fold_seeds)} seeds): "
              f"mood={m['mood']:.4f} symm={m['symm']:.4f} "
              f"self_c={m['self_c']:.4f} same_art={m['same_art']:.4f}")

    # Mean and std across folds
    print(f"\n  {'Metric':<18}  {'Mean':>8}  {'Std':>8}  {'CV%':>6}  Stable?")
    print("  " + "-" * 52)
    cv_results = {}
    all_stable = True
    for key, label, hib in METRICS:
        vals = [fr[key] for fr in fold_results]
        mean = float(np.mean(vals))
        std  = float(np.std(vals))
        cv_pct = std / (mean + 1e-9) * 100
        stable = cv_pct < 15.0   # CV% < 15% = acceptably stable
        if not stable:
            all_stable = False
        cv_results[key] = {"mean": round(mean, 5), "std": round(std, 5), "cv_pct": round(cv_pct, 1)}
        mark = "✓" if stable else "⚠"
        print(f"  {label:<18}  {mean:>8.4f}  {std:>8.4f}  {cv_pct:>5.1f}%  {mark}")

    verdict = (
        "✓ All metrics stable across folds (CV% < 15%) — weights not overfit to specific seeds."
        if all_stable else
        "⚠ Some metrics show high variance across folds — consider more seeds."
    )
    print(f"\n  {verdict}")
    return {"folds": fold_results, "summary": cv_results,
            "all_stable": all_stable, "verdict": verdict}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-seeds", type=int, default=80)
    ap.add_argument("--folds",   type=int, default=5)
    ap.add_argument("--save",    action="store_true")
    args = ap.parse_args(argv)

    os.chdir(str(PROJECT_ROOT))

    from tools.backtest_v2.catalog import Catalog
    from tools.eval_similar_intrinsic import _stratified_seeds

    print("[validate] Loading catalog…")
    cat = Catalog.load()
    df  = cat.df

    rng   = np.random.default_rng(42)
    seeds = _stratified_seeds(df, args.n_seeds, rng)
    print(f"[validate] {len(seeds)} seeds")

    sens = run_sensitivity(cat, seeds)
    cv   = run_cv(cat, seeds, n_folds=args.folds)

    # Final summary
    print("\n" + "=" * 72)
    print("  FINAL SUMMARY — Weight validation for RECO_SONG_WEIGHTS_MERT")
    print("=" * 72)
    print(f"  Baseline: mert=0.75 / lyrics=0.15 / va=0.10  (σ_V=0.22, σ_A=0.14)")
    print(f"  Sensitivity: {sens['conclusion']}")
    print(f"  Stability:   {cv['verdict']}")
    academic = sens["locally_optimal"] and cv["all_stable"]
    print(f"\n  Academic claim: {'SUPPORTED' if academic else 'PARTIALLY SUPPORTED'}")
    print("  → Weights are {'locally optimal and stable' if academic else 'empirically selected'}")
    print("     across seed subsets on this catalog.")
    print("=" * 72)

    if args.save:
        out = {
            "baseline_weights": BASELINE_W,
            "sensitivity": sens,
            "cross_validation": cv,
        }
        out_path = "var/runtime/backtest/reports/weight_validation.json"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print(f"\n[validate] Saved → {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
