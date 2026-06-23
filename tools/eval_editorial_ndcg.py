"""Editorial-playlist NDCG@10 for similar-song — reproducible standalone harness.

Replaces the drifted `backtest_v2.measure_full_accuracy` (which is tied to the
removed pillar architecture). Uses the committed editorial ground truth
(var/runtime/backtest/ground_truth/editorial_playlists_v1.json), the live
recommender, and the project's own ndcg_at_k. Reflects the CURRENT config
(AUDIO_BACKBONE + EMBEDDINGS_FILE).

Reports the production recommender against two non-personalised baselines so the
absolute NDCG has context (Dacrema 2021 ACM TOIS — strong baselines mandatory):
  random      — 10 random songs per seed (mean over REPEATS passes, fixed seed)
  popularity  — global top-10 by artist-frequency proxy (same proxy as
                color_eval_rigor), identical for every seed
The "× random" column expresses each method as a multiple of the random floor.

Run: python -m tools.eval_editorial_ndcg
"""
from __future__ import annotations
import os, sys, statistics
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SEED = 42
RANDOM_REPEATS = 20   # average random draws over multiple passes to shrink variance


def main() -> int:
    from tools.backtest_v2.ground_truth.editorial import (
        build_query_gt_mapping, load_editorial_gt, GT_FILE)
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from core.recommendation_engine import get_recommender
    import config as cfg

    playlists = load_editorial_gt(GT_FILE)
    gt = build_query_gt_mapping(playlists)
    # Keep only seeds with a non-empty relevant set; freeze order for reproducibility.
    queries = [(int(s), set(rel)) for s, rel in gt.items() if rel]

    print(f"[editorial-ndcg] backbone={cfg.AUDIO_BACKBONE}  lyrics={os.path.basename(cfg.EMBEDDINGS_FILE)}")
    print(f"[editorial-ndcg] {len(playlists)} playlists, {len(queries)} seed queries")

    rec = get_recommender()
    n = rec.n_songs

    # ── Production recommender ────────────────────────────────────────────────
    prod = []
    for seed_idx, relevant in queries:
        try:
            df = rec.recommend_by_song(seed_idx, top_k=10)
            ranked = [int(i) for i in df["original_index"].tolist()]
        except Exception:
            ranked = []
        prod.append(ndcg_at_k(ranked, relevant, 10))
    prod_mean = statistics.mean(prod)

    # ── Baseline: popularity (artist-frequency proxy, same as color_eval_rigor) ─
    art_col = rec.artist_col or "artists"
    artists = rec.df[art_col].fillna("__unknown__").astype(str).values
    art_freq = Counter(artists)
    pop_order = sorted(range(n), key=lambda i: art_freq[artists[i]], reverse=True)
    pop_top = pop_order[:11]   # take 11 so dropping the seed still leaves ≥10
    pop = []
    for seed_idx, relevant in queries:
        ranked = [i for i in pop_top if i != seed_idx][:10]
        pop.append(ndcg_at_k(ranked, relevant, 10))
    pop_mean = statistics.mean(pop)

    # ── Baseline: random (fixed seed; averaged over REPEATS passes) ────────────
    rng = np.random.default_rng(SEED)
    rand = []
    for _ in range(RANDOM_REPEATS):
        for seed_idx, relevant in queries:
            cand = rng.choice(n, size=11, replace=False)
            ranked = [int(i) for i in cand if int(i) != seed_idx][:10]
            rand.append(ndcg_at_k(ranked, relevant, 10))
    rand_mean = statistics.mean(rand)

    # ── Report ────────────────────────────────────────────────────────────────
    base = rand_mean if rand_mean > 0 else float("nan")
    print(f"\n  {'method':<12}{'NDCG@10':>10}{'x random':>11}")
    print("  " + "-" * 31)
    for label, val in [("production", prod_mean), ("popularity", pop_mean), ("random", rand_mean)]:
        ratio = (val / base) if base == base else float("nan")
        print(f"  {label:<12}{val:>10.4f}{ratio:>10.1f}x")
    print(f"\n[editorial-ndcg] mean NDCG@10 = {prod_mean:.4f}  (n={len(queries)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
