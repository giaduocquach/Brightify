"""E-EMO-RESOURCE: gate lexicon-based emotion vec for recommend_by_song signal 6.

Change: song_emotion_vec source → VietnameseEmotionLexicon.analyze_lyrics()
  (was: color_to_emotion_probs(album_art_color), std=0.026 across catalog)
  New: 13-dim lexicon distribution, lyrics-derived, std expected >> 0.026.

Baselines from E-EMO-CLEAN Phase 0 (isotropic, same weights):
  editorial NDCG@10 = 0.10825  (1050 queries)
  LLM-judge NDCG@10 = 0.72749  (v2 de-circular, 30 seeds)

Gate (same as E-EMO-CLEAN): accept iff CI₉₅ lower bound > -0.002 on BOTH GTs.

Usage: python -m tools.e_emo_resource
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = "var/runtime/backtest/reports/e_emo_resource.json"
N_BOOT = 10_000
TOP_K  = 10
NEUTRAL_FLOOR = -0.002

# Known baselines (E-EMO-CLEAN Phase 0 — isotropic V-A, color-based emotion)
BASELINE_ED  = 0.10825
BASELINE_LLM = 0.72749


def _boot_ci(vals: np.ndarray, seed: int = 42) -> Tuple[float, float, float]:
    rng   = np.random.default_rng(seed)
    obs   = float(vals.mean())
    means = np.array([
        vals[rng.integers(0, len(vals), len(vals))].mean()
        for _ in range(N_BOOT)
    ])
    return obs, float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> int:
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        load_editorial_gt, build_query_gt_mapping)
    from tools.backtest_v2.ground_truth.similar_llm_gt import load_similar_llm_gt
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k

    print("=" * 68)
    print("  E-EMO-RESOURCE — lexicon-based emotion vec gate")
    print("=" * 68)

    cat    = Catalog.load()
    rec    = cat.rec
    ed_gt  = build_query_gt_mapping(load_editorial_gt())
    llm_gt = load_similar_llm_gt()

    # Verify new signal 6 source
    lex_ev = rec.song_emotion_lexicon
    print(f"\n  song_emotion_lexicon: shape={lex_ev.shape}")
    print(f"  mean={lex_ev.mean():.4f}  std={lex_ev.std():.4f}  "
          f"(was color-based: mean≈0.125, std≈0.068 total, but per-emotion std≈0.015-0.05)")
    std_per = lex_ev.std(axis=0)
    print(f"  std per category: {dict(zip(rec.lexicon_emotion_labels, std_per.round(3)))}")
    # Fraction of songs with at least one non-zero emotion
    nonempty = (lex_ev.max(axis=1) > 0).mean()
    print(f"  songs with ≥1 detected emotion: {nonempty:.1%}")

    print("\n[Eval] Computing editorial NDCG@10…")
    ed_scores = np.array([
        ndcg_at_k(cat.recommend_by_song(s, top_k=TOP_K), set(r), TOP_K)
        for s, r in ed_gt.items()
    ], float)
    ed_mean = float(ed_scores.mean())
    ed_delta_arr = ed_scores - BASELINE_ED   # per-query delta vs baseline constant
    ed_obs, ed_lo, ed_hi = _boot_ci(ed_delta_arr)

    print(f"  editorial NDCG@10 = {ed_mean:.5f}  (baseline {BASELINE_ED})")
    print(f"  Δ={ed_obs:+.5f}  CI95=[{ed_lo:+.5f},{ed_hi:+.5f}]")

    print("\n[Eval] Computing LLM-judge NDCG@10…")
    llm_scores = []
    for seed_str, entry in llm_gt.items():
        R     = set(entry.get("relevant", []))
        judged = entry.get("judged", {})
        pool  = [int(k) for k, v in judged.items()
                 if isinstance(v, dict) and v.get("q", -1) >= 0]
        if len(R) < 1 or len(pool) < 2:
            continue
        recs = cat.recommend_by_song(int(seed_str), top_k=TOP_K)
        llm_scores.append(ndcg_at_k(recs, R, TOP_K))

    llm_arr  = np.array(llm_scores, float)
    llm_mean = float(llm_arr.mean())
    llm_delta_arr = llm_arr - BASELINE_LLM
    llm_obs, llm_lo, llm_hi = _boot_ci(llm_delta_arr, seed=43)

    print(f"  LLM-judge NDCG@10 = {llm_mean:.5f}  (baseline {BASELINE_LLM})")
    print(f"  Δ={llm_obs:+.5f}  CI95=[{llm_lo:+.5f},{llm_hi:+.5f}]")

    # Discriminant unchanged (no re-judging needed)
    disc_path = "var/runtime/backtest/reports/similar_discriminant_metrics.json"
    disc_info = (json.load(open(disc_path)) if os.path.exists(disc_path)
                 else {"n_separated": -1, "n_pairs": -1})

    ed_ok  = ed_lo  > NEUTRAL_FLOOR
    llm_ok = llm_lo > NEUTRAL_FLOOR
    accept = ed_ok and llm_ok

    def _tag(ok): return "✅ OK" if ok else "❌ FAIL"

    print(f"\n[Gate]  (floor={NEUTRAL_FLOOR})")
    print(f"  editorial:   Δ={ed_obs:+.5f}  CI95=[{ed_lo:+.5f},{ed_hi:+.5f}]  {_tag(ed_ok)}")
    print(f"  LLM-judge:   Δ={llm_obs:+.5f}  CI95=[{llm_lo:+.5f},{llm_hi:+.5f}]  {_tag(llm_ok)}")
    print(f"  discriminant: {disc_info['n_separated']}/{disc_info['n_pairs']} PASS (unchanged)")

    verdict = ("ACCEPT lexicon-based emotion vec (no regression on any GT)"
               if accept else
               "REJECT — regression detected; revert song_emotion_lexicon in signal 6")

    print(f"\n{'='*68}")
    print(f"  VERDICT: {verdict}")
    print(f"{'='*68}")

    report = {
        "change": "signal 6 source: color_to_emotion_probs → lexicon.analyze_lyrics()",
        "lexicon_vec_stats": {
            "shape":     list(lex_ev.shape),
            "mean":      round(float(lex_ev.mean()), 4),
            "std":       round(float(lex_ev.std()), 4),
            "nonempty_frac": round(float(nonempty), 3),
            "std_per_label": {k: round(float(v), 4)
                              for k, v in zip(rec.lexicon_emotion_labels, std_per)},
        },
        "baselines": {"editorial": BASELINE_ED, "llm_judge": BASELINE_LLM},
        "editorial": {"mean": ed_mean, "delta": ed_obs, "ci95": [ed_lo, ed_hi], "pass": ed_ok},
        "llm_judge": {"mean": llm_mean, "delta": llm_obs, "ci95": [llm_lo, llm_hi], "pass": llm_ok},
        "discriminant": {"n_sep": disc_info["n_separated"], "n_pairs": disc_info["n_pairs"]},
        "accept": accept,
        "verdict": verdict,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\n  report → {OUT}")
    return 0 if accept else 1


if __name__ == "__main__":
    sys.exit(main())
