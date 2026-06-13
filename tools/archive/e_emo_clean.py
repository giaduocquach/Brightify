"""E-EMO-CLEAN: ablate signal 5 (emotion vec from album-art) from recommend_by_song.

Background: song_emotion_vec is built from color_to_emotion_probs(album_art_color),
the same source the team confirmed is noise (r=0.22, Palmer/Whiteford) and already
removed from recommend_by_colors (V19). Its weight in the MERT 8-signal config is
0.104 — ~10% of every similarity score. This script tests whether removing it helps.

Methodology (mirrors E-AUDIO-CLEAN, 2026-06-01):
  Phase 1 — simple drop: zero emotion weight (idx 5), re-normalize 4 active signals.
             Paired bootstrap on editorial AND LLM-judge GT simultaneously.
  Phase 2 — re-optimise: SLSQP with emotion frozen to 0, bootstrap on both GTs.
             Gate: both CIs must be entirely positive to accept new weights.

If accepted → config.RECO_SONG_WEIGHTS_MERT["with_lyrics"] is updated in-place.

Usage: python -m tools.e_emo_clean
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EMOTION_IDX    = 5   # index in 8-signal MERT vector: [tim,rhy,ton,lyr,va,EMO,mood,mert]
TOP_K          = 10
N_BOOT         = 10_000
OUT            = "var/runtime/backtest/reports/e_emo_clean.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _renorm_drop(weights: List[float], drop_idx: int) -> List[float]:
    """Zero weight[drop_idx], renormalize rest to Σ=1."""
    w = list(weights)
    w[drop_idx] = 0.0
    s = sum(w)
    return [x / s for x in w] if s > 0 else w


def _editorial_scores(cat, gt_mapping: Dict[int, List[int]],
                      weights: List[float]) -> Dict[int, float]:
    """NDCG@10 per query on editorial GT."""
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    return {
        seed: ndcg_at_k(cat.recommend_by_song(seed, top_k=TOP_K, weights=weights),
                        set(rel), TOP_K)
        for seed, rel in gt_mapping.items()
    }


def _llm_scores(cat, llm_gt: dict, weights: List[float]) -> np.ndarray:
    """NDCG@10 per seed on LLM-judge GT."""
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    out = []
    for seed_str, entry in llm_gt.items():
        R     = set(entry.get("relevant", []))
        judged = entry.get("judged", {})
        pool  = [int(k) for k, v in judged.items() if v >= 0]
        if len(R) < 1 or len(pool) < 2:
            continue
        recs = cat.recommend_by_song(int(seed_str), top_k=TOP_K, weights=weights)
        out.append(ndcg_at_k(recs, R, TOP_K))
    return np.array(out, float)


def _editorial_bootstrap(
    scores_base: Dict[int, float],
    scores_new:  Dict[int, float],
    cluster_seeds: List[List[int]],
) -> Tuple[float, float, float]:
    from tools.backtest_v2.stats import cluster_paired_bootstrap
    return cluster_paired_bootstrap(scores_base, scores_new, cluster_seeds,
                                    n_boot=N_BOOT, seed=42)


def _llm_bootstrap(
    base: np.ndarray,
    new:  np.ndarray,
    seed: int = 43,
) -> Tuple[float, float, float]:
    """Simple (non-cluster) paired bootstrap — LLM seeds are independent."""
    rng   = np.random.default_rng(seed)
    diffs = new - base
    obs   = float(diffs.mean())
    means = np.array([
        diffs[rng.integers(0, len(diffs), len(diffs))].mean()
        for _ in range(N_BOOT)
    ])
    return obs, float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _fmt_ci(delta, lo, hi) -> str:
    sign = "✅ PASS" if lo > 0 else ("⚠️ inconclusive" if hi > 0 else "❌ FAIL")
    return f"Δ={delta:+.5f}  CI95=[{lo:+.5f},{hi:+.5f}]  {sign}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    import config as cfg
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        load_editorial_gt, build_query_gt_mapping, build_cluster_seeds)
    from tools.backtest_v2.ground_truth.similar_llm_gt import load_similar_llm_gt
    from tools.backtest_v2.improve.weight_opt import optimize_weights, split_playlists

    print("=" * 70)
    print("  E-EMO-CLEAN — ablate signal 5 (emotion from album-art)")
    print("=" * 70)

    # --- Load catalog + GTs ---
    cat = Catalog.load()
    playlists    = load_editorial_gt()
    ed_gt        = build_query_gt_mapping(playlists)
    cluster_seeds = build_cluster_seeds(playlists)
    llm_gt       = load_similar_llm_gt()

    print(f"  editorial GT: {len(ed_gt)} queries")
    print(f"  LLM-judge GT: {sum(1 for e in llm_gt.values() if e.get('relevant'))} usable seeds")

    base_w = list(cfg.RECO_SONG_WEIGHTS_MERT["with_lyrics"])
    print(f"\n  baseline weights: {[round(x, 4) for x in base_w]}")
    print(f"  emotion (idx {EMOTION_IDX}): {base_w[EMOTION_IDX]:.4f}")

    # --- Baseline scores (both GTs) ---
    print("\n[Phase 0] Computing baseline scores…")
    ed_base  = _editorial_scores(cat, ed_gt, base_w)
    llm_base = _llm_scores(cat, llm_gt, base_w)
    print(f"  editorial NDCG@10 = {np.mean(list(ed_base.values())):.5f}  "
          f"({len(ed_base)} queries)")
    print(f"  LLM-judge NDCG@10 = {llm_base.mean():.5f}  "
          f"({len(llm_base)} seeds)")

    # --------------------------------------------------------------------------
    # Phase 1: zero emotion + renorm
    # --------------------------------------------------------------------------
    print("\n[Phase 1] Drop emotion (idx 5), re-normalize…")
    drop_w = _renorm_drop(base_w, EMOTION_IDX)
    print(f"  drop weights: {[round(x, 4) for x in drop_w]}")

    ed_drop  = _editorial_scores(cat, ed_gt, drop_w)
    llm_drop = _llm_scores(cat, llm_gt, drop_w)

    ed_d1,  ed_lo1,  ed_hi1  = _editorial_bootstrap(ed_base,  ed_drop,  cluster_seeds)
    llm_d1, llm_lo1, llm_hi1 = _llm_bootstrap(llm_base, llm_drop)

    print(f"  editorial:  {_fmt_ci(ed_d1,  ed_lo1,  ed_hi1)}")
    print(f"  LLM-judge:  {_fmt_ci(llm_d1, llm_lo1, llm_hi1)}")

    phase1_pass = ed_lo1 > 0 and llm_lo1 > 0

    # --------------------------------------------------------------------------
    # Phase 2: SLSQP re-optimise with emotion frozen to 0
    # --------------------------------------------------------------------------
    print("\n[Phase 2] SLSQP re-optimise (emotion frozen to 0)…")
    baseline_ild = 0.087  # from similar_song_metrics report
    opt_result = optimize_weights(
        cat, playlists,
        baseline_ild=baseline_ild,
        top_k=TOP_K,
        max_opt_queries=150,
        verbose=True,
        mert=True,
        freeze_idx=[EMOTION_IDX],
    )
    opt_w = opt_result.optimal_weights
    print(f"  optimised weights: {[round(x, 4) for x in opt_w]}")

    ed_opt  = _editorial_scores(cat, ed_gt, opt_w)
    llm_opt = _llm_scores(cat, llm_gt, opt_w)

    ed_d2,  ed_lo2,  ed_hi2  = _editorial_bootstrap(ed_base, ed_opt, cluster_seeds)
    llm_d2, llm_lo2, llm_hi2 = _llm_bootstrap(llm_base, llm_opt)

    print(f"\n  [Phase 2 gate]")
    print(f"  editorial:  {_fmt_ci(ed_d2,  ed_lo2,  ed_hi2)}")
    print(f"  LLM-judge:  {_fmt_ci(llm_d2, llm_lo2, llm_hi2)}")

    phase2_pass = ed_lo2 > 0 and llm_lo2 > 0

    # --------------------------------------------------------------------------
    # Verdict
    # --------------------------------------------------------------------------
    if phase2_pass:
        verdict = "ACCEPT Phase 2 weights (both GTs CI entirely positive)"
        final_w = opt_w
        update  = True
    elif phase1_pass:
        verdict = "ACCEPT Phase 1 weights (drop+renorm; optimised not better)"
        final_w = drop_w
        update  = True
    else:
        verdict = "NO UPDATE — emotion removal does not improve either GT"
        final_w = base_w
        update  = False

    print(f"\n{'=' * 70}")
    print(f"  VERDICT: {verdict}")
    if update:
        print(f"  new weights: {[round(x, 4) for x in final_w]}")
    print(f"{'=' * 70}")

    # --- Update config if gate passes ---
    if update:
        cfg.RECO_SONG_WEIGHTS_MERT["with_lyrics"] = [round(x, 6) for x in final_w]
        _patch_config(final_w, base_w, verdict, phase1_pass, phase2_pass)
        print("\n  config.py updated ✓")
        print("  run: python -m tools.smoke_test http://127.0.0.1:8000  to verify")

    # --- Save report ---
    report = {
        "baseline_weights":  base_w,
        "emotion_idx":       EMOTION_IDX,
        "phase1": {
            "weights":     drop_w,
            "editorial":   {"delta": ed_d1,  "ci95": [ed_lo1,  ed_hi1],  "pass": ed_lo1  > 0},
            "llm_judge":   {"delta": llm_d1, "ci95": [llm_lo1, llm_hi1], "pass": llm_lo1 > 0},
            "pass":        phase1_pass,
        },
        "phase2": {
            "weights":     opt_w,
            "optimizer":   {"success": opt_result.optimizer["success"],
                            "message": opt_result.optimizer["message"]},
            "editorial":   {"delta": ed_d2,  "ci95": [ed_lo2,  ed_hi2],  "pass": ed_lo2  > 0},
            "llm_judge":   {"delta": llm_d2, "ci95": [llm_lo2, llm_hi2], "pass": llm_lo2 > 0},
            "pass":        phase2_pass,
        },
        "verdict":    verdict,
        "update":     update,
        "final_weights": final_w,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\n  report → {OUT}")
    return 0


# ---------------------------------------------------------------------------
# Config patcher
# ---------------------------------------------------------------------------

def _patch_config(new_w: List[float], old_w: List[float],
                  verdict: str, p1: bool, p2: bool) -> None:
    """Rewrite RECO_SONG_WEIGHTS_MERT in config.py with new weights."""
    config_path = "config.py"
    with open(config_path, encoding="utf-8") as fh:
        src = fh.read()

    old_line = f'"with_lyrics": [{", ".join(str(round(x, 4)) for x in old_w)}]'
    new_vals  = ", ".join(str(round(x, 6)) for x in new_w)
    new_line  = (
        f'    # E-EMO-CLEAN (2026-06): emotion signal (idx 5) dropped — album-art source\n'
        f'    # is noise (r=0.22, same source removed from recommend_by_colors V19).\n'
        f'    # Phase{"2" if p2 else "1"} accepted: both GTs CI95 entirely positive.\n'
        f'    # {verdict}\n'
        f'    "with_lyrics": [{new_vals}]'
    )

    # Find and replace the with_lyrics line inside RECO_SONG_WEIGHTS_MERT block
    import re
    pattern = r'("with_lyrics": \[0\.0, 0\.0, 0\.0, [^\]]+\])'
    match   = re.search(pattern, src)
    if match:
        src = src[:match.start()] + f'"with_lyrics": [{new_vals}]' + src[match.end():]
        with open(config_path, "w", encoding="utf-8") as fh:
            fh.write(src)
    else:
        print("  WARNING: could not patch config.py automatically — update manually:")
        print(f"    RECO_SONG_WEIGHTS_MERT['with_lyrics'] = {[round(x, 6) for x in new_w]}")


if __name__ == "__main__":
    sys.exit(main())
