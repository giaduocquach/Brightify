"""Bước 5 — Popularity stratification + debias decision.

No external play-count data → use RECOMMENDATION FREQUENCY as popularity proxy
(standard in algorithmic-fairness literature: exposure ∝ de-facto popularity).
Method mirrors Kowald et al. 2020 (ECIR) and Abdollahpouri et al. 2021 (UMUAI).

Steps:
  1. Large-scale simulation: 1000 random seeds × top-10 recs → exposure per song.
  2. Tier by exposure quantile: head (top 20%), mid (60%), tail (bottom 20%).
     Unexposed songs are a 4th stratum (never recommended).
  3. Per-tier: mean exposure, catalog share, NDCG@10 (editorial GT), ILD.
  4. Artist-level Gini over exposure (finer than song-level).
  5. Debias decision: is inequality severe enough to warrant action?

Thresholds (literature-informed):
  • Gini ≥ 0.80 → strong popularity bias (Kowald 2020 reports 0.85+ for CF).
  • Never-exposed fraction ≥ 40% → severe long-tail neglect.
  • Tail NDCG < 0.5 × Head NDCG → systematic quality gap (actionable).

Usage: python -m tools.popularity_stratification
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from typing import Dict, List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT   = "var/runtime/backtest/reports/popularity_stratification.json"
TOP_K = 10
N_SIM_SEEDS = 1000   # large enough for stable exposure estimates


def _gini(counts: np.ndarray) -> float:
    """Gini coefficient of an exposure array (0=equal, 1=all to one)."""
    counts = np.sort(counts.astype(float))
    n = len(counts)
    if n == 0 or counts.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * (idx * counts).sum() / (n * counts.sum())) - (n + 1) / n)


def main() -> int:
    import config as cfg
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        load_editorial_gt, build_query_gt_mapping)
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.metrics.property import ild_lyrics

    cat    = Catalog.load()
    df     = cat.df
    n      = cat.n
    rng    = np.random.default_rng(42)
    ed_gt  = build_query_gt_mapping(load_editorial_gt())

    # ── Step 1: Exposure simulation ──────────────────────────────────────────
    print(f"[Step 1] Simulating {N_SIM_SEEDS} seeds × top-{TOP_K}…")
    seeds = rng.choice(n, size=N_SIM_SEEDS, replace=True)  # with replacement for stability
    exposure: Counter = Counter()
    all_recs_lists: List[List[int]] = []
    for s in seeds:
        recs = cat.recommend_by_song(int(s), top_k=TOP_K)
        exposure.update(recs)
        all_recs_lists.append(recs)

    # Song-level exposure array (all n songs, 0 if never recommended)
    exp_arr = np.array([exposure.get(i, 0) for i in range(n)], float)
    total_exp = exp_arr.sum()
    n_exposed = (exp_arr > 0).sum()
    n_never   = n - n_exposed
    coverage  = n_exposed / n

    song_gini = _gini(exp_arr)

    print(f"  catalog coverage: {coverage:.1%}  ({n_exposed}/{n} songs ever recommended)")
    print(f"  never-exposed:    {n_never} songs ({n_never/n:.1%})")
    print(f"  song-level Gini:  {song_gini:.3f}")

    # ── Step 2: Tier assignment ───────────────────────────────────────────────
    exposed_mask = exp_arr > 0
    exposed_exp  = exp_arr[exposed_mask]
    q20 = float(np.percentile(exposed_exp, 80))   # top-20% threshold
    q60 = float(np.percentile(exposed_exp, 20))   # bottom-20% threshold

    def tier(i: int) -> str:
        e = exp_arr[i]
        if e == 0:           return "never"
        if e >= q20:         return "head"
        if e <= q60:         return "tail"
        return "mid"

    tiers = np.array([tier(i) for i in range(n)])
    tier_counts = {t: int((tiers == t).sum()) for t in ("head", "mid", "tail", "never")}
    print(f"\n  Tiers: {tier_counts}")

    # ── Step 3: Per-tier NDCG + ILD ─────────────────────────────────────────
    print("\n[Step 3] Per-tier NDCG@10 on editorial GT…")
    tier_ndcg:  Dict[str, List[float]] = {t: [] for t in ("head", "mid", "tail")}
    tier_ild:   Dict[str, List[float]] = {t: [] for t in ("head", "mid", "tail")}

    # Only use editorial seeds whose recs fall predominantly in one tier
    # (simpler: just report mean NDCG for seeds that ARE in each tier)
    # Approach: stratify SEEDS by their tier label
    for seed, relevant in ed_gt.items():
        R    = set(relevant)
        recs = cat.recommend_by_song(seed, top_k=TOP_K)
        if not recs:
            continue
        seed_tier = tier(seed)
        if seed_tier == "never":
            continue
        ndcg_val = ndcg_at_k(recs, R, TOP_K)
        ild_val  = ild_lyrics(recs, cat)
        tier_ndcg[seed_tier].append(ndcg_val)
        tier_ild[seed_tier].append(ild_val)

    print(f"  {'Tier':<6} {'N_seeds':>8} {'NDCG@10':>9} {'ILD':>8} {'CatalogShare':>13}")
    print(f"  {'-'*48}")
    tier_summary = {}
    for t in ("head", "mid", "tail"):
        nd = tier_ndcg[t]
        il = tier_ild[t]
        cat_share = tier_counts[t] / n
        summary = {
            "n_songs": tier_counts[t],
            "catalog_share": round(cat_share, 4),
            "n_seeds_in_gt": len(nd),
            "ndcg_at_10": round(float(np.mean(nd)), 5) if nd else 0.0,
            "ild_lyrics":  round(float(np.mean(il)), 5) if il else 0.0,
            "mean_exposure": round(float(exp_arr[tiers == t].mean()), 2),
            "exposure_share": round(float(exp_arr[tiers == t].sum() / total_exp), 4),
        }
        tier_summary[t] = summary
        print(f"  {t:<6} {len(nd):>8}  {summary['ndcg_at_10']:>9.5f}  "
              f"{summary['ild_lyrics']:>8.5f}  {cat_share:>13.1%}")

    # ── Step 4: Artist-level Gini ─────────────────────────────────────────────
    artist_col = cat.artist_col
    artist_gini_val = 0.0
    top_artists = []
    if artist_col:
        artist_exp: Counter = Counter()
        for recs_list in all_recs_lists:
            for idx in recs_list:
                a = str(df.iloc[idx].get(artist_col, "") or "")
                if a:
                    artist_exp[a] += 1
        n_artists = len(set(df[artist_col].dropna()))
        artist_arr = np.array([artist_exp.get(a, 0)
                               for a in df[artist_col].dropna().unique()], float)
        artist_gini_val = _gini(artist_arr)
        top_artists = artist_exp.most_common(10)
        print(f"\n  Artist-level Gini: {artist_gini_val:.3f}  ({n_artists} unique artists)")
        print(f"  Top-5 by exposure: {top_artists[:5]}")

    # ── Step 5: Debias decision ───────────────────────────────────────────────
    head_ndcg = tier_summary["head"]["ndcg_at_10"]
    tail_ndcg = tier_summary["tail"]["ndcg_at_10"]
    tail_head_ratio = tail_ndcg / head_ndcg if head_ndcg > 0 else 1.0

    flag_gini    = song_gini    >= 0.80
    flag_never   = (n_never / n) >= 0.40
    flag_quality = tail_head_ratio < 0.50

    print(f"\n[Step 5] Debias decision thresholds:")
    print(f"  song Gini ≥ 0.80     : {song_gini:.3f}   {'⚠️ FLAG' if flag_gini else '✅ OK'}")
    print(f"  never-exposed ≥ 40%  : {n_never/n:.1%}   {'⚠️ FLAG' if flag_never else '✅ OK'}")
    print(f"  tail/head NDCG < 0.5 : {tail_head_ratio:.3f}   {'⚠️ FLAG' if flag_quality else '✅ OK'}")

    n_flags = sum([flag_gini, flag_never, flag_quality])
    if n_flags == 0:
        debias_verdict = ("NO DEBIAS NEEDED — Gini and coverage within acceptable bounds. "
                          "Bias exists but is typical for content-based recommenders.")
    elif n_flags == 1:
        debias_verdict = ("OPTIONAL DEBIAS — one threshold flagged; impact likely small. "
                          "Consider lightweight popularity-penalty in _fast_rank.")
    else:
        debias_verdict = ("DEBIAS RECOMMENDED — multiple thresholds flagged; "
                          "implement popularity-calibrated re-ranking.")

    print(f"\n  VERDICT: {debias_verdict}")

    # ── Save ──────────────────────────────────────────────────────────────────
    report = {
        "n_sim_seeds":    N_SIM_SEEDS,
        "top_k":          TOP_K,
        "catalog_size":   n,
        "exposure": {
            "n_exposed":         int(n_exposed),
            "n_never_exposed":   int(n_never),
            "coverage_pct":      round(float(coverage) * 100, 2),
            "song_gini":         round(song_gini, 4),
            "artist_gini":       round(artist_gini_val, 4),
            "top_10_artists":    [(a, int(c)) for a, c in top_artists],
        },
        "tiers": tier_summary,
        "tier_thresholds": {"head_min_exposure": round(q20, 2),
                            "tail_max_exposure": round(q60, 2)},
        "debias_flags": {
            "song_gini_flag":      flag_gini,
            "never_exposed_flag":  flag_never,
            "tail_quality_flag":   flag_quality,
            "n_flags":             n_flags,
        },
        "tail_head_ndcg_ratio": round(tail_head_ratio, 4),
        "verdict": debias_verdict,
    }
    def _safe(v):
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return None
        return v

    def _sanitize(obj):
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(x) for x in obj]
        if isinstance(obj, tuple):
            return [_sanitize(x) for x in obj]
        if isinstance(obj, (np.floating, float)):
            return _safe(float(obj))
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        return obj

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(_sanitize(report), open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\n  report → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
