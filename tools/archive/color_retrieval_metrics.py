"""L2 — End-to-end retrieval metrics for recommend_by_colors, on INDEPENDENT ground truth.

Scores production recommend_by_colors() against two non-circular ground truths built from
sources outside the ranker's V-A pipeline:
  * editorial  (color_editorial_gt) — human-curated mood playlists. validity=external.
  * llm        (color_llm_gt)       — qwen3 judge of lyrics vs the colour's human mood,
                                       TREC-pooled. validity=semi-independent.

Metrics: NDCG@10 / P@10 / Recall@10 / mAP@10 / MRR + bootstrap-CI over colours, vs a
baseline (random-over-catalog for editorial; random-within-judged-pool for llm, the
honest "beat picking randomly from the pool" contrast).

Unlike the old circular GT (100% by construction), these can — and should — be < 1.

Usage: python -m tools.color_retrieval_metrics
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = "var/runtime/backtest/reports/color_retrieval_metrics.json"
TOP_K = 10


def _boot_ci(vals, n_boot=10000, seed=42):
    vals = np.asarray(vals, dtype=float)
    if len(vals) == 0:
        return (0.0, 0.0, 0.0)
    rng = np.random.default_rng(seed)
    means = [vals[rng.integers(0, len(vals), len(vals))].mean() for _ in range(n_boot)]
    return (round(float(vals.mean()), 4),
            round(float(np.percentile(means, 2.5)), 4),
            round(float(np.percentile(means, 97.5)), 4))


def _score_block(per_color):
    """per_color: list of dicts with keys ndcg,p,rec,ap,rr -> aggregate with CI."""
    keys = ("ndcg", "p", "rec", "ap", "rr")
    return {k: _boot_ci([c[k] for c in per_color]) for k in keys}


def main() -> int:
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.metrics.accuracy import (
        ndcg_at_k, precision_at_k, recall_at_k, average_precision_at_k, mrr)

    cat = Catalog.load()
    rng = np.random.default_rng(42)
    report = {"top_k": TOP_K, "sources": {}}

    def eval_one(recs, R):
        return {"ndcg": ndcg_at_k(recs, R, TOP_K), "p": precision_at_k(recs, R, TOP_K),
                "rec": recall_at_k(recs, R, TOP_K), "ap": average_precision_at_k(recs, R, TOP_K),
                "rr": mrr(recs, R)}

    # ---------------- editorial GT (external) ----------------
    try:
        from tools.backtest_v2.ground_truth.color_editorial_gt import load_color_editorial_gt
        ed = load_color_editorial_gt()["colors"]
        prod, rand = [], []
        for hexv, e in ed.items():
            R = set(e["relevant"])
            if len(R) < 3:
                continue
            prod.append(eval_one(cat.recommend_by_colors([hexv], top_k=TOP_K), R))
            rand.append(eval_one(rng.choice(cat.n, TOP_K, replace=False).tolist(), R))
        report["sources"]["editorial"] = {
            "validity": "external", "n_colors": len(prod),
            "production": _score_block(prod), "random_baseline": _score_block(rand),
            "note": "human mood-playlist GT, but VN mood playlists are BROAD+NOISY (a 'vui' "
                    "playlist holds many sad ballads) and sparse -> absolute P/NDCG are low "
                    "BY CONSTRUCTION and a broad relevant set can favour random over a precise "
                    "ranker. Use for RELATIVE A/B only, not absolute quality (cf. similar_song).",
        }
    except FileNotFoundError:
        report["sources"]["editorial"] = {"error": "GT not built yet"}

    # ---------------- LLM-judge GT (semi-independent, pooled) ----------------
    try:
        from tools.backtest_v2.ground_truth.color_llm_gt import load_color_llm_gt, REL_THRESHOLD
        llm = load_color_llm_gt()
        prod, randpool, grades = [], [], []
        for hexv, e in llm.items():
            judged = {int(k): v for k, v in e["judged"].items() if v >= 0}  # drop unjudgeable
            R = set(i for i, v in judged.items() if v >= REL_THRESHOLD)
            pool = list(judged)
            if len(R) < 2 or len(pool) < TOP_K:
                continue
            recs = cat.recommend_by_colors([hexv], top_k=TOP_K)
            prod.append(eval_one(recs, R))
            # graded: mean judged relevance (0..3) of production's top-10 that were judged
            g = [judged[i] for i in recs if i in judged]
            grades.append(float(np.mean(g)) if g else 0.0)
            # honest baseline: random pick from the judged pool
            rp = rng.choice(pool, TOP_K, replace=False).tolist()
            randpool.append(eval_one(rp, R))
        report["sources"]["llm_judge"] = {
            "validity": "semi-independent", "n_colors": len(prod),
            "rel_threshold": REL_THRESHOLD,
            "production": _score_block(prod),
            "random_in_pool_baseline": _score_block(randpool),
            "production_mean_graded_relevance_top10": round(float(np.mean(grades)), 3) if grades else None,
            "note": "TREC-pooled (prod top-20 + random negatives); P@10 is the honest "
                    "headline, recall/NDCG are pool-limited.",
        }
    except FileNotFoundError:
        report["sources"]["llm_judge"] = {"error": "GT not built yet"}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)

    print("\n=== L2 — COLOUR RETRIEVAL (independent GT, NON-circular) ===")
    for src, blk in report["sources"].items():
        if "error" in blk:
            print(f"\n  [{src}] {blk['error']}"); continue
        p = blk["production"]
        base_key = "random_baseline" if "random_baseline" in blk else "random_in_pool_baseline"
        b = blk[base_key]
        print(f"\n  [{src}] validity={blk['validity']}  n_colors={blk['n_colors']}")
        print(f"    PROD     NDCG@10 {p['ndcg'][0]} CI{list(p['ndcg'][1:])}  P@10 {p['p'][0]} CI{list(p['p'][1:])}"
              f"  Recall@10 {p['rec'][0]}  mAP {p['ap'][0]}  MRR {p['rr'][0]}")
        print(f"    {base_key:24s} NDCG@10 {b['ndcg'][0]}  P@10 {b['p'][0]}  Recall@10 {b['rec'][0]}")
        if blk.get("production_mean_graded_relevance_top10") is not None:
            print(f"    mean judged relevance of top-10 (0..3): {blk['production_mean_graded_relevance_top10']}")
        print(f"    note: {blk['note']}")
    print(f"\n  saved -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
