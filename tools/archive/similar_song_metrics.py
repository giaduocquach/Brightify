"""Full offline-metric report for recommend_by_song (Similar Song).

Surfaces the WHOLE metric panel that already lives in tools/backtest_v2/metrics/ but was
not in the headline report: accuracy (NDCG/P/Recall/mAP/MRR) + diversity (ILD, same_artist)
+ beyond-accuracy (serendipity, catalog coverage, artist Gini). On the editorial-playlist
ground truth (1050 seed queries). Prints a table and saves a JSON report.

NOTE on absolute values: editorial co-membership GT is very sparse (a song is "relevant"
only if it shares an editorial playlist with the seed), so absolute NDCG/Recall are low by
construction — they are meaningful for RELATIVE A/B (with the bootstrap CI in weight_opt),
not as absolute quality scores. Diversity/coverage/Gini are absolute and interpretable.

Usage: python -m tools.similar_song_metrics
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = "var/runtime/backtest/reports/similar_song_metrics.json"


def main() -> int:
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE, load_editorial_gt, build_query_gt_mapping)
    from tools.backtest_v2.metrics.accuracy import (
        ndcg_at_k, precision_at_k, recall_at_k, average_precision_at_k, mrr)
    from tools.backtest_v2.metrics import property as P

    cat = Catalog.load()
    gt = build_query_gt_mapping(load_editorial_gt(GT_FILE))
    acc = {k: [] for k in ("ndcg", "p", "rec", "ap", "rr")}
    div = {k: [] for k in ("ild", "sa", "ser")}
    all_recs = []
    for seed in gt:
        recs = cat.recommend_by_song(seed, top_k=10)
        if not recs:
            continue
        R = set(gt[seed])
        acc["ndcg"].append(ndcg_at_k(recs, R, 10))
        acc["p"].append(precision_at_k(recs, R, 10))
        acc["rec"].append(recall_at_k(recs, R, 10))
        acc["ap"].append(average_precision_at_k(recs, R, 10))
        acc["rr"].append(mrr(recs, R))
        div["ild"].append(P.ild_lyrics(recs, cat))
        div["sa"].append(P.same_artist_at_k(recs, seed, cat))
        div["ser"].append(P.serendipity_proxy(recs, seed, cat))
        all_recs.append(recs)

    m = lambda xs: round(float(np.mean(xs)), 4)
    report = {
        "n_queries": len(all_recs),
        "ground_truth": "editorial_playlists_v1 (co-membership, sparse — relative use)",
        "accuracy": {
            "ndcg_at_10": m(acc["ndcg"]), "precision_at_10": m(acc["p"]),
            "recall_at_10": m(acc["rec"]), "map_at_10": m(acc["ap"]), "mrr": m(acc["rr"]),
        },
        "diversity": {
            "ild_lyrics": m(div["ild"]),
            "same_artist_at_10": m(div["sa"]),
            "distinct_artist_per_10": round(10 * (1 - np.mean(div["sa"])), 1),
        },
        "beyond_accuracy": {
            "serendipity": m(div["ser"]),
            "catalog_coverage": round(P.catalog_coverage(all_recs, len(cat.df)), 4),
            "artist_gini": round(P.artist_gini(all_recs, cat), 4),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)

    print("\n=== SIMILAR-SONG — FULL OFFLINE METRIC REPORT ===")
    print(f"  ({report['n_queries']} editorial queries; GT sparse → accuracy is relative)")
    a, d, b = report["accuracy"], report["diversity"], report["beyond_accuracy"]
    print(f"\n  ACCURACY   NDCG@10 {a['ndcg_at_10']}  P@10 {a['precision_at_10']}  "
          f"Recall@10 {a['recall_at_10']}  mAP@10 {a['map_at_10']}  MRR {a['mrr']}")
    print(f"  DIVERSITY  ILD_lyrics {d['ild_lyrics']}  same_artist@10 {d['same_artist_at_10']}  "
          f"(~{d['distinct_artist_per_10']}/10 distinct artists)")
    print(f"  BEYOND     serendipity {b['serendipity']}  coverage {b['catalog_coverage']}  "
          f"artist_gini {b['artist_gini']}")
    print(f"\n  saved → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
