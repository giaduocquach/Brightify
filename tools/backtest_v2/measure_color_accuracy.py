"""Full accuracy suite for the COLOR path (recommend_by_colors) — the multimodal
core of Brightify (fuses lyrics 0.35 + audio 0.25 + V-A 0.20 + emotion 0.20).

Compares clean v7.2 baseline vs CURRENT production config on the 24-color
engine-derived GT, reporting NDCG / Precision / Recall / MAP / Hit / MRR @10.

IMPORTANT — read before citing: the color GT defines "relevant" as V-A proximity,
and V-A is itself an INPUT to recommend_by_colors. So this measures INTERNAL
alignment / arm-vs-arm deltas, NOT external quality. See report for the caveat.

Output: var/runtime/backtest/reports/iter_10_color_accuracy/report.json
"""

from __future__ import annotations

import datetime
import json
import os
import sys

import numpy as np

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(project_root)
sys.path.insert(0, project_root)

import config as cfg
from tools.backtest_v2.catalog import Catalog
from tools.backtest_v2.ground_truth.color_emotion_gt import (
    build_color_gt, load_color_gt, GT_FILE as COLOR_GT_FILE,
)
from tools.backtest_v2.metrics.accuracy import (
    ndcg_at_k, precision_at_k, recall_at_k, average_precision_at_k, hit_at_k, mrr,
)
from tools.backtest_v2.stats import paired_bootstrap
from tools.backtest_v2.cli import V72_BASELINE_FLAGS, _pinned_recommend_flags, _recommend_time_subset

N_BOOT = 10_000


def per_color_metrics(catalog, colors, gt_mapping):
    keys = ["ndcg_at_10", "precision_at_10", "recall_at_10", "map_at_10", "hit_at_10", "mrr"]
    out = {k: [] for k in keys}
    for hex_color in colors:
        relevant = set(gt_mapping[hex_color])
        recs = catalog.recommend_by_colors(hex_color, top_k=10)
        if not recs:
            for k in keys:
                out[k].append(0.0)
            continue
        out["ndcg_at_10"].append(ndcg_at_k(recs, relevant, 10))
        out["precision_at_10"].append(precision_at_k(recs, relevant, 10))
        out["recall_at_10"].append(recall_at_k(recs, relevant, 10))
        out["map_at_10"].append(average_precision_at_k(recs, relevant, 10))
        out["hit_at_10"].append(hit_at_k(recs, relevant, 10))
        out["mrr"].append(mrr(recs, relevant))
    return out


def main() -> int:
    base_flags = dict(V72_BASELINE_FLAGS)
    prod_flags = {
        "ENABLE_PILLAR_B":     cfg.ENABLE_PILLAR_B,
        "ENABLE_MERT":         cfg.ENABLE_MERT,
        "ENABLE_KG":           cfg.ENABLE_KG,
        "ENABLE_CLAP_EMOTION": cfg.ENABLE_CLAP_EMOTION,
        "ENABLE_RRF":          cfg.ENABLE_RRF,
        "ENABLE_VN_CONTEXT":   cfg.ENABLE_VN_CONTEXT,
        "DIVERSITY_METHOD":    cfg.DIVERSITY_METHOD,
    }
    print(f"[color_acc] Production flags: {prod_flags}")

    print("[color_acc] Building v7.2 baseline catalog (all pillars off)...")
    cat_base = Catalog.build_isolated(base_flags)
    print("[color_acc] Building production catalog (current config)...")
    cat_prod = Catalog.build_isolated(prod_flags)

    # GT fixed: derived from the v7.2 baseline catalog's V-A (engine-derived).
    if os.path.exists(COLOR_GT_FILE):
        print(f"[color_acc] Loading color GT from {COLOR_GT_FILE}")
        gt_mapping, gt_meta = load_color_gt(COLOR_GT_FILE)
    else:
        print("[color_acc] Building color GT from baseline catalog...")
        gt_mapping, gt_meta = build_color_gt(cat_base, save_path=COLOR_GT_FILE)
    colors = list(gt_mapping.keys())
    rel_sizes = [len(v) for v in gt_mapping.values()]
    print(f"[color_acc] {len(colors)} color queries; relevant-set size "
          f"mean={np.mean(rel_sizes):.0f} (={np.mean(rel_sizes)/cat_base.n*100:.0f}% of catalog)")

    print("[color_acc] Evaluating v7.2 arm...")
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        base_pq = per_color_metrics(cat_base, colors, gt_mapping)
    print("[color_acc] Evaluating production arm...")
    with _pinned_recommend_flags(**_recommend_time_subset(prod_flags)):
        prod_pq = per_color_metrics(cat_prod, colors, gt_mapping)

    metrics = ["ndcg_at_10", "precision_at_10", "recall_at_10", "map_at_10", "hit_at_10", "mrr"]
    results = {}
    print("\n" + "=" * 80)
    print(f"  {'Metric':<16}{'v7.2':>12}{'production':>14}{'delta':>12}   CI95 (paired bootstrap)")
    print("=" * 80)
    for m in metrics:
        a, b = base_pq[m], prod_pq[m]
        mean_base, mean_prod = float(np.mean(a)), float(np.mean(b))
        delta, ci_low, ci_high = paired_bootstrap(a, b, n_boot=N_BOOT)
        pct = (mean_prod / mean_base - 1.0) * 100 if mean_base > 0 else 0.0
        sig = ci_low > 0
        results[m] = {
            "v72": mean_base, "production": mean_prod,
            "delta": float(delta), "pct_change": pct,
            "ci95": [float(ci_low), float(ci_high)],
            "significant": bool(sig), "n_queries": len(a),
        }
        print(f"  {m:<16}{mean_base:>12.5f}{mean_prod:>14.5f}{delta:>+12.5f}"
              f"   [{ci_low:+.5f}, {ci_high:+.5f}] {'SIG' if sig else 'ns'}")
    print("=" * 80)

    report = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_10_color_accuracy",
            "n_catalog": cat_prod.n,
            "n_color_queries": len(colors),
            "metric_cutoff": 10,
            "n_boots": N_BOOT,
            "ground_truth": "color_emotion_gt_v1",
            "gt_validity": "engine-derived-color",
            "gt_warning": gt_meta["warning"],
            "mean_relevant_set_size": float(np.mean(rel_sizes)),
            "ci_method": "standard paired bootstrap (24 colors are independent)",
            "base_flags": base_flags,
            "prod_flags": prod_flags,
            "fusion_weights": {"lyrics": 0.35, "audio": 0.25, "valence_arousal": 0.20, "emotion": 0.20},
        },
        "results": results,
    }
    out_dir = "var/runtime/backtest/reports/iter_10_color_accuracy"
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"\n[color_acc] Saved {out_dir}/report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
