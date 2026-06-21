"""Re-measure the FULL accuracy suite (NDCG / Precision / Recall / MAP / Hit / MRR)
for BOTH arms: clean v7.2 baseline and the CURRENT production config.

The shipped `run-full-system` command only stored NDCG@10 for production; this
script fills the gap so the backtest report can cite production precision/recall
with cluster-bootstrap confidence intervals (resample playlists, not queries).

Output: var/runtime/backtest/reports/iter_9_full_accuracy/report.json
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
from tools.backtest_v2.baselines.brightify import BrightifyBaseline
from tools.backtest_v2.ground_truth.editorial import (
    GT_FILE, build_query_gt_mapping, load_editorial_gt, build_cluster_seeds,
)
from tools.backtest_v2.metrics.accuracy import (
    ndcg_at_k, precision_at_k, recall_at_k, average_precision_at_k, hit_at_k, mrr,
)
from tools.backtest_v2.stats import cluster_paired_bootstrap
from tools.backtest_v2.cli import (
    V72_BASELINE_FLAGS, _pinned_recommend_flags, _recommend_time_subset,
)

TOP_K = 20
N_BOOT = 10_000


def per_query_metrics(system, gt_mapping):
    """Return {metric_name: {seed_idx: value}} for one already-built arm."""
    keys = ["ndcg_at_10", "precision_at_10", "recall_at_10",
            "map_at_10", "hit_at_10", "mrr"]
    out = {k: {} for k in keys}
    for seed_idx, relevant_indices in gt_mapping.items():
        relevant = set(relevant_indices)
        if not relevant:
            continue
        ranked = system.recommend(seed_idx, top_k=TOP_K)
        if not ranked:
            for k in keys:
                out[k][seed_idx] = 0.0
            continue
        out["ndcg_at_10"][seed_idx] = ndcg_at_k(ranked, relevant, 10)
        out["precision_at_10"][seed_idx] = precision_at_k(ranked, relevant, 10)
        out["recall_at_10"][seed_idx] = recall_at_k(ranked, relevant, 10)
        out["map_at_10"][seed_idx] = average_precision_at_k(ranked, relevant, 10)
        out["hit_at_10"][seed_idx] = hit_at_k(ranked, relevant, 10)
        out["mrr"][seed_idx] = mrr(ranked, relevant)
    return out


def main() -> int:
    if not os.path.exists(GT_FILE):
        print(f"[full_acc] GT file not found: {GT_FILE}")
        return 1

    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    clusters = build_cluster_seeds(playlists)
    print(f"[full_acc] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries, "
          f"{len(clusters)} clusters")

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
    print(f"[full_acc] Production flags: {prod_flags}")

    print("[full_acc] Building v7.2 baseline catalog (all pillars off)...")
    cat_base = Catalog.build_isolated(base_flags)
    print("[full_acc] Building production catalog (current config)...")
    cat_prod = Catalog.build_isolated(prod_flags)

    sys_base = BrightifyBaseline(cat_base)
    sys_prod = BrightifyBaseline(cat_prod)

    print("[full_acc] Evaluating v7.2 arm...")
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        base_pq = per_query_metrics(sys_base, gt_mapping)
    print("[full_acc] Evaluating production arm...")
    with _pinned_recommend_flags(**_recommend_time_subset(prod_flags)):
        prod_pq = per_query_metrics(sys_prod, gt_mapping)

    metrics = ["ndcg_at_10", "precision_at_10", "recall_at_10",
               "map_at_10", "hit_at_10", "mrr"]
    results = {}
    print("\n" + "=" * 78)
    print(f"  {'Metric':<16}{'v7.2':>12}{'production':>14}{'delta':>12}"
          f"{'   CI95 (cluster bootstrap)':<26}")
    print("=" * 78)
    for m in metrics:
        a = base_pq[m]
        b = prod_pq[m]
        mean_base = float(np.mean(list(a.values())))
        mean_prod = float(np.mean(list(b.values())))
        delta, ci_low, ci_high = cluster_paired_bootstrap(a, b, clusters, n_boot=N_BOOT)
        pct = (mean_prod / mean_base - 1.0) * 100 if mean_base > 0 else 0.0
        sig = ci_low > 0
        results[m] = {
            "v72": mean_base, "production": mean_prod,
            "delta": float(delta), "pct_change": pct,
            "ci95": [float(ci_low), float(ci_high)],
            "significant": bool(sig),
            "n_queries": len(a),
        }
        print(f"  {m:<16}{mean_base:>12.5f}{mean_prod:>14.5f}{delta:>+12.5f}"
              f"   [{ci_low:+.5f}, {ci_high:+.5f}] {'SIG' if sig else 'ns'}")
    print("=" * 78)

    report = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_9_full_accuracy",
            "n_catalog": cat_prod.n,
            "top_k_eval": TOP_K,
            "metric_cutoff": 10,
            "n_queries": len(gt_mapping),
            "n_clusters": len(clusters),
            "n_boots": N_BOOT,
            "ground_truth": "editorial_playlists_v1",
            "ci_method": "cluster_paired_bootstrap (resample playlists)",
            "base_flags": base_flags,
            "prod_flags": prod_flags,
        },
        "results": results,
    }
    out_dir = "var/runtime/backtest/reports/iter_9_full_accuracy"
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"\n[full_acc] Saved {out_dir}/report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
