"""E2 (V16) — tune config.COLOR_SCORE_WEIGHTS on the non-circular L2-LLM NDCG.

Grid-sweeps (lyrics, va, emotion) on the simplex (Σ=1), ranks by mean NDCG@10 over
the LLM-judge GT colours, and runs a paired bootstrap of the best vs the current
default. Prints a verdict + the config snippet — does NOT write config (review-gated).

σ / boost / penalty are held at their config values (tuning 3 weights on ~12 colours
is already at the edge of overfitting; widening the search would invite it).

Usage: python -m tools.color_weight_opt [step]   (default step 0.10)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import core.recommendation_engine as eng
from tools.backtest_v2.catalog import Catalog
from tools.backtest_v2.metrics.accuracy import ndcg_at_k
from tools.backtest_v2.stats import paired_bootstrap
from tools.backtest_v2.ground_truth.color_llm_gt import load_color_llm_gt, REL_THRESHOLD

TOP_K = 10
DEFAULT = (0.40, 0.30, 0.30)  # (lyrics, va, emotion) — current config


def per_color_ndcg(cat, gt, w):
    """NDCG@10 per LLM-judged colour for weight tuple w=(lyrics, va, emotion)."""
    eng.COLOR_SCORE_WEIGHTS = {'lyrics': w[0], 'va': w[1], 'emotion': w[2]}
    out = []
    for hexv, e in gt.items():
        judged = {int(k): v for k, v in e['judged'].items() if v >= 0}
        R = set(i for i, v in judged.items() if v >= REL_THRESHOLD)
        pool = list(judged)
        if len(R) < 2 or len(pool) < TOP_K:
            continue
        recs = cat.recommend_by_colors(hexv, top_k=TOP_K)
        out.append(ndcg_at_k(recs, R, TOP_K))
    return out


def main() -> int:
    step = float(sys.argv[1]) if len(sys.argv) > 1 else 0.10
    cat = Catalog.load()
    gt = load_color_llm_gt()

    vals = [round(i * step, 3) for i in range(int(round(1 / step)) + 1)]
    grid = []
    for lyr in vals:
        for va in vals:
            emo = round(1.0 - lyr - va, 3)
            if -1e-9 <= emo <= 1.0 + 1e-9:
                grid.append((lyr, va, max(0.0, emo)))

    base = per_color_ndcg(cat, gt, DEFAULT)
    base_mean = float(np.mean(base))
    n_colors = len(base)

    results = []
    for w in grid:
        scores = per_color_ndcg(cat, gt, w)
        results.append((w, float(np.mean(scores)), scores))
    results.sort(key=lambda r: -r[1])

    print(f"\n=== E2 — COLOUR WEIGHT TUNING (L2-LLM NDCG@{TOP_K}, n_colors={n_colors}) ===")
    print(f"  grid step={step}  points={len(grid)}")
    print(f"\n  DEFAULT (lyr={DEFAULT[0]}, va={DEFAULT[1]}, emo={DEFAULT[2]})  mean NDCG@10 = {base_mean:.4f}")
    print("\n  top-8 weight settings by mean NDCG@10:")
    for w, m, _ in results[:8]:
        print(f"    lyr={w[0]:.2f} va={w[1]:.2f} emo={w[2]:.2f}   NDCG@10 = {m:.4f}")

    best_w, best_mean, best_scores = results[0]
    delta, lo, hi = paired_bootstrap(base, best_scores)
    sig = lo > 0
    print(f"\n  BEST  lyr={best_w[0]:.2f} va={best_w[1]:.2f} emo={best_w[2]:.2f}  NDCG@10 = {best_mean:.4f}")
    print(f"  paired bootstrap Δ(best−default) = {delta:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]")
    if sig:
        print(f"  VERDICT: best is SIGNIFICANTLY better (CI excludes 0) → adopt {best_w}.")
    else:
        print("  VERDICT: NOT significant on this GT (CI includes 0). Keep DEFAULT unless")
        print("           another gate (editorial A/B, L3) favours the candidate.")
        print(f"           (Note: E2's real win — album-art noise → content signal — is already in.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
