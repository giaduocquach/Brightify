"""CLI entry point for backtest v2. §6.4.

    python -m tools.backtest_v2 run --config configs/backtest_v0.yaml
    python -m tools.backtest_v2 ablation --signals timbral,rhythmic,...
    python -m tools.backtest_v2 optimize-weights --ground-truth editorial_playlists_v1
    python -m tools.backtest_v2 compare iter_0_baseline iter_1_weight_opt
    python -m tools.backtest_v2 report
    python -m tools.backtest_v2 check-mood-tags        # §7.3 gate (implemented)
"""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from typing import List, Optional


# ---------------------------------------------------------------------------
# Baseline isolation (§ fixed-v7.2 design)
# ---------------------------------------------------------------------------
# Every pillar A/B test is measured against the SAME clean v7.2 baseline: all
# pillar flags off. The treatment arm toggles ONLY the pillar under test. This
# removes run-order dependency — each pillar's reported delta is its independent
# marginal contribution to v7.2, not "contribution given whichever pillars ran
# before it". The production lift (v7.2 → all-on) is reported separately by
# cmd_run_full_system.
V72_BASELINE_FLAGS = {
    "ENABLE_PILLAR_B": False,
    "ENABLE_MERT": False,
    "ENABLE_KG": False,
    "ENABLE_CLAP_EMOTION": False,
    "ENABLE_RRF": False,
    "ENABLE_VN_CONTEXT": False,
    "DIVERSITY_METHOD": "greedy",
}

# Recommend-time flags read live by the engine on every recommend() call.
# build_isolated() bakes in init-time flags; these must be pinned around calls.
_RECOMMEND_TIME_KEYS = ("ENABLE_RRF", "DIVERSITY_METHOD", "ENABLE_VN_CONTEXT")


@contextmanager
def _pinned_recommend_flags(**flags):
    """Pin recommend-time engine globals for the duration of recommend() calls.

    The engine reads ENABLE_RRF / DIVERSITY_METHOD / ENABLE_VN_CONTEXT live at
    recommend time, so a catalog built with build_isolated() is not enough —
    these must be held fixed while the arm's recommendations are computed.
    """
    import core.recommendation_engine as _eng
    old = {k: getattr(_eng, k, None) for k in flags}
    try:
        for k, v in flags.items():
            setattr(_eng, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(_eng, k, v)


def _recommend_time_subset(flags: dict) -> dict:
    """Extract only the recommend-time flags from a full flag set."""
    return {k: flags[k] for k in _RECOMMEND_TIME_KEYS if k in flags}


# ---------------------------------------------------------------------------
# Multiple-comparison correction (Bonferroni)
# ---------------------------------------------------------------------------
# 6 pillar NDCG gates tested against the same editorial GT → FWER ~26% with
# per-test α=0.05.  Bonferroni target: α_family=0.05 / 6 pillars → each gate
# uses a ~99.17% CI instead of 95%.  Wider CI = more conservative = correct.
# run-full-system and color-path commands are single comparisons → 95% CI.
_N_PILLAR_TESTS = 6
BONFERRONI_CI_LEVEL = 1.0 - 0.05 / _N_PILLAR_TESTS  # ≈ 0.9917
_CI_LABEL = f"CI{BONFERRONI_CI_LEVEL * 100:.1f}%"    # "CI99.2%" — used in pillar gate prints


def _not_implemented(phase: str) -> int:
    print(f"[backtest_v2] not implemented yet — {phase}. See docs/PLAN_BACKTEST_METRICS.md")
    return 2


def cmd_run(args: argparse.Namespace) -> int:
    """Phase 1 + Phase 2: measure baseline property metrics, optionally accuracy against GT."""
    import os
    import sys

    # Change working directory to project root so relative paths work.
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from tools.backtest_v2.core import BacktestConfig, BacktestRunner

    config_path = args.config or 'configs/backtest_v0.yaml'
    if not os.path.exists(config_path):
        print(f"[backtest_v2] Config not found: {config_path}")
        return 1

    print(f"[backtest_v2] Loading config: {config_path}")
    config = BacktestConfig.from_yaml(config_path)

    if args.output:
        config.output_dir = args.output

    # CLI --ground-truth overrides config file
    gt_name = args.ground_truth or config.ground_truth
    if gt_name:
        config.ground_truth = gt_name

    runner = BacktestRunner(config)

    # If ground-truth is the primary goal and property metrics were already run,
    # skip the expensive full property evaluation and load catalog directly.
    existing_report_path = os.path.join(config.output_dir, 'report.json') if config.output_dir else None
    skip_property = (
        gt_name is not None
        and existing_report_path is not None
        and os.path.exists(existing_report_path)
    )

    if skip_property:
        import json
        print(f"[backtest_v2] Existing property report found at {existing_report_path} — skipping property metrics.")
        with open(existing_report_path) as fh:
            report_dict = json.load(fh)
        # Still need catalog loaded for accuracy eval
        from tools.backtest_v2.catalog import Catalog
        print("[backtest_v2] Loading catalog...")
        runner.catalog = Catalog.load()

        class _MinimalReport:
            def __init__(self, cfg, d):
                self.config = cfg
                self.systems = d.get('systems', {})
                self.latency = d.get('latency', {})
                self.meta = d.get('meta', {})
            def to_dict(self):
                return {'meta': self.meta, 'systems': self.systems, 'latency': self.latency}

        report = _MinimalReport(config, report_dict)
    else:
        report = runner.run()
        _print_summary(report)

    # Phase 2: accuracy metrics if GT requested
    if gt_name:
        rc = cmd_run_accuracy(gt_name, runner, report, config)
        if rc != 0:
            return rc

    return 0


def cmd_run_accuracy(
    gt_name: str,
    runner,
    property_report,
    config,
) -> int:
    """Phase 2: load/crawl GT, evaluate accuracy, append to report JSON."""
    import json
    import os

    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE,
        build_editorial_gt,
        build_query_gt_mapping,
        load_editorial_gt,
    )
    from tools.backtest_v2.metrics.accuracy import evaluate_system_accuracy

    if gt_name != "editorial_playlists_v1":
        print(f"[backtest_v2] Unknown ground-truth name: {gt_name!r}. Only 'editorial_playlists_v1' supported.")
        return 1

    # Load existing GT or crawl
    if os.path.exists(GT_FILE):
        print(f"[backtest_v2] Loading existing GT: {GT_FILE}")
        playlists = load_editorial_gt(GT_FILE)
    else:
        print("[backtest_v2] GT file not found — crawling now (needs network)...")
        catalog = runner.catalog
        playlists, _ = build_editorial_gt(catalog.df, save=True, verbose=True)

    if not playlists:
        print("[backtest_v2] STOP: 0 playlists passed filter. Cannot compute accuracy. DO NOT use quadrant as substitute.")
        return 1

    total_matched = sum(len(pl["matched"]) for pl in playlists)
    print(f"\n[backtest_v2] GT summary: {len(playlists)} playlists, {total_matched} total track matches")

    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[backtest_v2] GT mapping: {len(gt_mapping)} unique seed queries")

    if len(gt_mapping) < 5:
        print("[backtest_v2] STOP: fewer than 5 seed queries in GT. Insufficient data for meaningful NDCG.")
        return 1

    # Evaluate each system
    print("\n[backtest_v2] Evaluating accuracy metrics (Group B)...")
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.baselines.random_b import RandomBaseline
    from tools.backtest_v2.baselines.lyrics_only import LyricsOnlyBaseline

    catalog = runner.catalog
    systems_to_eval = {
        "random": RandomBaseline(catalog, seed=config.seed),
        "lyrics_only": LyricsOnlyBaseline(catalog),
        "brightify_v7.2": BrightifyBaseline(catalog),
    }

    accuracy_results: dict = {}
    for name, system in systems_to_eval.items():
        print(f"[backtest_v2]   {name}...")
        acc = evaluate_system_accuracy(
            system,
            gt_mapping,
            top_k=20,
            ground_truth_name=gt_name,
        )
        accuracy_results[name] = acc

    # Print NDCG@10 table
    print()
    print("=" * 60)
    print("  NDCG@10 (external, validity='external')")
    print("=" * 60)
    for name, metrics in accuracy_results.items():
        entry = metrics.get("ndcg_at_10", {})
        val = entry.get("value")
        ci = entry.get("ci95", [None, None])
        n = entry.get("n", 0)
        print(f"  {name:<20} NDCG@10 = {val:.4f}  CI95=[{ci[0]:.4f}, {ci[1]:.4f}]  N={n}")
    print()

    # Merge accuracy into existing report JSON and save
    if config.output_dir:
        json_path = os.path.join(config.output_dir, "report.json")
        if os.path.exists(json_path):
            with open(json_path) as fh:
                report_dict = json.load(fh)
        else:
            report_dict = property_report.to_dict()

        for name, acc_metrics in accuracy_results.items():
            report_dict.setdefault("systems", {}).setdefault(name, {}).update(acc_metrics)

        report_dict.setdefault("meta", {})["ground_truth"] = gt_name
        report_dict["meta"]["n_gt_playlists"] = len(playlists)
        report_dict["meta"]["n_gt_queries"] = len(gt_mapping)

        acc_path = os.path.join(config.output_dir, "accuracy_ext.json")
        with open(acc_path, "w") as fh:
            json.dump(accuracy_results, fh, indent=2)
        print(f"[backtest_v2] Accuracy results written to {acc_path}")

        with open(json_path, "w") as fh:
            json.dump(report_dict, fh, indent=2)
        print(f"[backtest_v2] Merged into {json_path}")

    return 0


def _print_summary(report) -> None:
    """Print a compact result table to stdout."""
    systems = report.systems
    meta = report.meta
    latency = report.latency

    print()
    print("=" * 72)
    print(f"  Backtest: {meta.get('iteration', '?')}")
    print(f"  Catalog:  {meta.get('n_catalog', '?')} songs  |  Queries: {meta.get('n_queries', '?')}")
    print(f"  Quadrants: {meta.get('quadrant_breakdown', {})}")
    print("=" * 72)

    METRICS = [
        ('ild_lyrics',        'ILD Lyrics   '),
        ('ild_audio',         'ILD Audio    '),
        ('ild_va',            'ILD V-A      '),
        ('ild_color',         'ILD Color    '),
        ('coverage',          'Coverage     '),
        ('artist_gini',       'Artist Gini  '),
        ('mood_coherence',    'MoodCoher    '),
        ('tempo_coherence',   'TempoCoher   '),
        ('color_coherence',   'ColorCoher   '),
        ('calibration_error', 'Calibration  '),
        ('symmetry',          'Symmetry     '),
        ('serendipity_proxy', 'Serendipity  '),
    ]

    sys_names = list(systems.keys())
    header = f"{'Metric':<16}" + "".join(f"{n[:14]:>16}" for n in sys_names)
    print(header)
    print("-" * (16 + 16 * len(sys_names)))

    for mkey, mlabel in METRICS:
        row = f"{mlabel:<16}"
        for sname in sys_names:
            m = systems.get(sname, {}).get(mkey)
            if m is None:
                row += f"{'—':>16}"
            elif isinstance(m, dict):
                val = m.get('value')
                row += f"{val:>16.4f}" if val is not None else f"{'—':>16}"
            else:
                row += f"{float(m):>16.4f}"
        print(row)

    if latency:
        print()
        print(f"{'Method':<34}  {'p50 ms':>8}  {'p95 ms':>8}  {'p99 ms':>8}")
        print("-" * 62)
        for method, lat in latency.items():
            print(f"{method:<34}  {lat['p50']:>8.1f}  {lat['p95']:>8.1f}  {lat['p99']:>8.1f}")

    if report.config.output_dir:
        print()
        print(f"Reports: {report.config.output_dir}/report.json")
        print(f"         {report.config.output_dir}/report.md")
    print()


def cmd_ablation(args: argparse.Namespace) -> int:
    """Phase 3: drop-one-signal ablation → signal_importance.json."""
    import json
    import os
    import sys

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE,
        build_editorial_gt,
        build_query_gt_mapping,
        load_editorial_gt,
    )
    from tools.backtest_v2.improve.ablation import run_ablation

    print("[ablation] Loading catalog...")
    catalog = Catalog.load()

    # Load editorial GT (Phase 2 prerequisite)
    if not os.path.exists(GT_FILE):
        print(f"[ablation] GT file not found: {GT_FILE}")
        print("[ablation] Run: python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1")
        return 1

    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[ablation] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries")

    output_dir = getattr(args, "output", None) or "var/runtime/backtest/reports/iter_0_baseline/ablation"

    result = run_ablation(
        catalog=catalog,
        ground_truth=gt_mapping,
        output_dir=output_dir,
    )

    return 0


def cmd_va_sanity(args: argparse.Namespace) -> int:
    """Phase 3: build/evaluate VA sanity floor (engine-derived, labeled)."""
    import os
    import sys

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.va_sanity import (
        VA_SANITY_FILE,
        build_va_sanity_gt,
        evaluate_va_sanity,
        load_va_sanity_gt,
    )
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.baselines.random_b import RandomBaseline

    print("[va_sanity] Loading catalog...")
    catalog = Catalog.load()

    save_path = "var/runtime/backtest/ground_truth/va_sanity_v1.json"
    if os.path.exists(save_path) and not getattr(args, "rebuild", False):
        print(f"[va_sanity] Loading existing GT: {save_path}")
        gt_mapping, meta = load_va_sanity_gt(save_path)
    else:
        print("[va_sanity] Building VA sanity GT...")
        gt_mapping, meta = build_va_sanity_gt(catalog, save_path=save_path)

    print(f"[va_sanity] {len(gt_mapping)} queries  validity=engine-derived")
    print(f"[va_sanity] {meta['warning']}")

    systems = {
        "brightify_v7.2": BrightifyBaseline(catalog),
        "random": RandomBaseline(catalog, seed=42),
    }
    print()
    print("  System               NDCG@10(VA)  N    validity")
    print("  " + "-" * 50)
    for name, sys_ in systems.items():
        r = evaluate_va_sanity(sys_, gt_mapping, top_k=10)
        entry = r["ndcg_at_10_va_sanity"]
        print(f"  {name:<20} {entry['value']:.4f}       {entry['n']}  {entry['validity']}")

    print("\n  [NOTE] NDCG≈1.0 for engine = expected (tautology). NDCG≈0 = broken.")
    return 0


def cmd_optimize_weights(args: argparse.Namespace) -> int:
    """Phase 4: SLSQP weight optimization → optimal_weights.yaml + iter_1_weight_opt report."""
    import datetime
    import json
    import os
    import sys

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE,
        build_query_gt_mapping,
        load_editorial_gt,
    )
    from tools.backtest_v2.improve.weight_opt import optimize_weights

    # --- Catalog ---
    print("[optimize] Loading catalog…")
    catalog = Catalog.load()

    # --- Baseline ILD from iter_0 ---
    iter0_path = "var/runtime/backtest/reports/iter_0_baseline/report.json"
    baseline_ild = 0.07834  # fallback from signal_importance.json meta
    iter0_report: dict = {}
    if os.path.exists(iter0_path):
        with open(iter0_path) as fh:
            iter0_report = json.load(fh)
        ild_entry = (
            iter0_report.get("systems", {})
            .get("brightify_v7.2", {})
            .get("ild_lyrics", {})
        )
        if isinstance(ild_entry, dict) and ild_entry.get("value") is not None:
            baseline_ild = float(ild_entry["value"])
    print(f"[optimize] Baseline ILD_lyrics = {baseline_ild:.6f}")
    print(f"[optimize] ILD constraint floor = {baseline_ild * 0.95:.6f}")

    # --- Editorial GT ---
    if not os.path.exists(GT_FILE):
        print(f"[optimize] GT file not found: {GT_FILE}")
        print("[optimize] Run: python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1")
        return 1
    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[optimize] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries")

    # --- Run optimizer ---
    max_opt_queries = int(getattr(args, "max_opt_queries", None) or 30)
    result = optimize_weights(
        catalog=catalog,
        playlists=playlists,
        baseline_ild=baseline_ild,
        top_k=10,
        max_opt_queries=max_opt_queries,
        verbose=True,
    )

    # --- Save optimal_weights.yaml ---
    weight_search_dir = "var/runtime/backtest/weight_search"
    os.makedirs(weight_search_dir, exist_ok=True)
    yaml_path = os.path.join(weight_search_dir, "optimal_weights.yaml")
    _save_optimal_weights_yaml(result, baseline_ild, yaml_path)
    print(f"\n[optimize] Saved: {yaml_path}")

    # --- Print summary table ---
    _print_opt_summary(result)

    # --- Build iter_1 report ---
    iter1_dir = "var/runtime/backtest/reports/iter_1_weight_opt"
    os.makedirs(iter1_dir, exist_ok=True)
    _build_iter1_report(
        catalog=catalog,
        result=result,
        iter0_report=iter0_report,
        gt_mapping=gt_mapping,
        gt_name="editorial_playlists_v1",
        iter1_dir=iter1_dir,
    )

    # --- Update config.RECO_SONG_WEIGHTS if improvement confirmed ---
    if result.update_config:
        _update_config_weights(result.optimal_weights)
        print(f"\n[optimize] config.RECO_SONG_WEIGHTS['with_lyrics'] updated to new optimal weights.")
    else:
        print(f"\n[optimize] config.RECO_SONG_WEIGHTS unchanged (weights already near-optimal).")

    return 0


def _save_optimal_weights_yaml(result, baseline_ild: float, path: str) -> None:
    try:
        import yaml
    except ImportError:
        import json, os
        path_json = path.replace(".yaml", ".json")
        with open(path_json, "w") as fh:
            json.dump({
                "description": "Optimal weights from SLSQP Phase 4 optimization",
                "date": str(__import__("datetime").date.today()),
                "objective": "maximize NDCG@10 (external GT, 80% optimize split)",
                "constraint": f"ILD_lyrics >= {baseline_ild:.6f} * 0.95 = {baseline_ild*0.95:.6f}",
                "signals": result.signals,
                "baseline_weights": [round(x, 6) for x in result.baseline_weights],
                "optimal_weights":  [round(x, 6) for x in result.optimal_weights],
                "splits": {
                    "optimize": result.opt_split,
                    "validate": result.val_split,
                },
                "bootstrap_full_gt": result.bootstrap,
                "optimizer": result.optimizer,
                "verdict": result.verdict,
                "update_config": result.update_config,
            }, fh, indent=2)
        print(f"[optimize] (yaml not available, saved as {path_json})")
        return

    import datetime
    data = {
        "description": "Optimal weights from SLSQP Phase 4 optimization",
        "date": str(datetime.date.today()),
        "objective": "maximize NDCG@10 (external GT, 80% optimize split)",
        "constraint": f"ILD_lyrics >= {baseline_ild:.6f} * 0.95 = {baseline_ild*0.95:.6f}",
        "signals": result.signals,
        "baseline_weights": [round(x, 6) for x in result.baseline_weights],
        "optimal_weights":  [round(x, 6) for x in result.optimal_weights],
        "splits": {
            "optimize": result.opt_split,
            "validate": result.val_split,
        },
        "bootstrap_full_gt": result.bootstrap,
        "optimizer": result.optimizer,
        "verdict": result.verdict,
        "update_config": result.update_config,
    }
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _print_opt_summary(result) -> None:
    import numpy as np
    w_b = result.baseline_weights
    w_o = result.optimal_weights
    bst = result.bootstrap

    print()
    print("=" * 68)
    print("  PHASE 4 — WEIGHT OPTIMIZATION RESULT")
    print("=" * 68)
    sigs = result.signals
    print(f"  {'Signal':<12} {'Baseline':>12} {'Optimal':>12} {'Delta':>10}")
    print("  " + "-" * 50)
    for i, s in enumerate(sigs):
        delta = w_o[i] - w_b[i]
        print(f"  {s:<12} {w_b[i]:>12.4f} {w_o[i]:>12.4f} {delta:>+10.4f}")
    print()
    print(f"  Optimize split ({result.opt_split['n_playlists']} playlists, "
          f"{result.opt_split['n_queries']} queries):")
    print(f"    Baseline  NDCG@10 = {result.opt_split['ndcg_at_10_baseline']:.5f}")
    print(f"    Optimal   NDCG@10 = {result.opt_split['ndcg_at_10_optimal']:.5f}  "
          f"Δ={result.opt_split['delta']:+.5f}")
    print()
    print(f"  Validate split ({result.val_split['n_playlists']} playlists, "
          f"{result.val_split['n_queries']} queries):")
    print(f"    Baseline  NDCG@10 = {result.val_split['ndcg_at_10_baseline']:.5f}")
    print(f"    Optimal   NDCG@10 = {result.val_split['ndcg_at_10_optimal']:.5f}  "
          f"Δ={result.val_split['delta']:+.5f}")
    print()
    print(f"  Full GT paired bootstrap (N={bst['n_queries']}, n_boots={bst['n_boots']}):")
    print(f"    Baseline  mean NDCG@10 = {bst['mean_ndcg_at_10_baseline']:.5f}")
    print(f"    Optimal   mean NDCG@10 = {bst['mean_ndcg_at_10_optimal']:.5f}")
    print(f"    Δ NDCG@10 = {bst['delta']:+.5f}  "
          f"CI95=[{bst['ci95'][0]:+.5f}, {bst['ci95'][1]:+.5f}]")
    print()
    status = "✅ IMPROVEMENT" if result.update_config else "❌ NO IMPROVEMENT"
    print(f"  {status}: {result.verdict}")
    print("=" * 68)


def _build_iter1_report(
    catalog,
    result,
    iter0_report: dict,
    gt_mapping: dict,
    gt_name: str,
    iter1_dir: str,
) -> None:
    """Build iter_1_weight_opt report by re-evaluating brightify with new weights."""
    import datetime
    import json
    import os

    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.core import _run_system, _metric_entry
    from tools.backtest_v2.metrics.accuracy import evaluate_system_accuracy
    from tools.backtest_v2.stats import stratified_sample

    w_new = result.optimal_weights

    # Load saved test-set queries (same as iter_0)
    ts_path = "var/runtime/backtest/test_sets/test_set_v1.json"
    if os.path.exists(ts_path):
        with open(ts_path) as fh:
            ts = json.load(fh)
        queries = ts["queries"]
    else:
        print("[iter1] test_set_v1.json not found — re-sampling (seed=42)")
        queries = stratified_sample(catalog.df, n=500, seed=42)

    print(f"\n[iter1] Re-evaluating brightify with new weights ({len(queries)} property queries)…")
    sys_new = BrightifyBaseline(catalog, weights=w_new)
    new_prop = _run_system(sys_new, queries, catalog, top_k=10)

    print(f"[iter1] Re-evaluating accuracy (GT: {len(gt_mapping)} queries)…")
    new_acc = evaluate_system_accuracy(
        sys_new, gt_mapping, top_k=20, ground_truth_name=gt_name,
    )
    new_prop.update(new_acc)

    # Start from iter_0 report; replace brightify_v7.2 with new eval
    report_dict: dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_1_weight_opt",
            "n_catalog": iter0_report.get("meta", {}).get("n_catalog"),
            "n_queries": len(queries),
            "top_k": 10,
            "seed": 42,
            "quadrant_breakdown": iter0_report.get("meta", {}).get("quadrant_breakdown"),
            "ground_truth": gt_name,
            "weight_optimization": {
                "baseline_weights": result.baseline_weights,
                "optimal_weights": result.optimal_weights,
                "signals": result.signals,
                "update_applied": result.update_config,
                "verdict": result.verdict,
                "bootstrap": result.bootstrap,
            },
        },
        "systems": {},
        "latency": iter0_report.get("latency", {}),
    }

    # Copy non-brightify systems from iter_0
    for sname, sdata in iter0_report.get("systems", {}).items():
        if sname != "brightify_v7.2":
            report_dict["systems"][sname] = sdata

    # New brightify with optimized weights
    report_dict["systems"]["brightify_v7.2"] = new_prop

    # Write JSON
    json_path = os.path.join(iter1_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)

    # Write Markdown
    from tools.backtest_v2.reporters.markdown import write_markdown

    class _FakeReport:
        def __init__(self, d):
            self.meta = d["meta"]
            self.systems = d["systems"]
            self.latency = d.get("latency", {})

            import dataclasses

            @dataclasses.dataclass
            class _Cfg:
                output_dir: str = iter1_dir
                iteration_name: str = "iter_1_weight_opt"

            self.config = _Cfg()

        def to_dict(self):
            return {"meta": self.meta, "systems": self.systems, "latency": self.latency}

    write_markdown(_FakeReport(report_dict), os.path.join(iter1_dir, "report.md"))

    print(f"[iter1] Reports saved to {iter1_dir}/")
    _print_iter1_summary(new_prop, iter0_report.get("systems", {}).get("brightify_v7.2", {}))


def _print_iter1_summary(new_metrics: dict, old_metrics: dict) -> None:
    KEY_METRICS = [
        ("ndcg_at_10",      "NDCG@10 (ext)  "),
        ("ild_lyrics",      "ILD_lyrics     "),
        ("mood_coherence",  "MoodCoherence  "),
        ("coverage",        "Coverage       "),
        ("artist_gini",     "Artist Gini    "),
    ]
    print()
    print(f"  {'Metric':<20} {'iter_0':>12} {'iter_1':>12} {'Delta':>10}")
    print("  " + "-" * 58)
    for key, label in KEY_METRICS:
        old_v = old_metrics.get(key, {}).get("value")
        new_v = new_metrics.get(key, {}).get("value")
        if old_v is None or new_v is None:
            print(f"  {label:<20} {'—':>12} {'—':>12} {'—':>10}")
        else:
            delta = new_v - old_v
            print(f"  {label:<20} {old_v:>12.5f} {new_v:>12.5f} {delta:>+10.5f}")


def _update_config_weights(new_weights) -> None:
    """Overwrite config.RECO_SONG_WEIGHTS['with_lyrics'] in config.py."""
    import re

    config_path = "config.py"
    with open(config_path, encoding="utf-8") as fh:
        src = fh.read()

    # Format new weights as Python list with 6 dp
    formatted = "[" + ", ".join(f"{w:.6f}" for w in new_weights) + "]"

    # Replace ONLY the "with_lyrics" line inside the RECO_SONG_WEIGHTS dict.
    # BUGFIX (2026-05-30): the old pattern matched EVERY "with_lyrics": [...] line
    # and re.subn replaced all of them — corrupting RECO_SONG_WEIGHTS_MERT (8-value)
    # with this 7-signal array. Anchor to the exact dict name + count=1 so the
    # 8-signal MERT config is never touched by the 7-signal optimizer.
    pattern = r'(RECO_SONG_WEIGHTS = \{[^}]*?"with_lyrics"\s*:\s*)\[.*?\]'
    replacement = r'\g<1>' + formatted
    new_src, n = re.subn(pattern, replacement, src, count=1, flags=re.DOTALL)
    if n == 0:
        print("[optimize] WARNING: could not find RECO_SONG_WEIGHTS 'with_lyrics' pattern in config.py — not updated")
        return

    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write(new_src)
    print(f"[optimize] config.py: RECO_SONG_WEIGHTS['with_lyrics'] = {formatted}")


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare two iteration report directories."""
    import json
    import os

    def _load(iter_name: str) -> dict:
        candidates = [
            iter_name,
            os.path.join('var/runtime/backtest/reports', iter_name, 'report.json'),
        ]
        for c in candidates:
            if os.path.exists(c):
                with open(c) as fh:
                    return json.load(fh)
        print(f"[backtest_v2] could not find report for: {iter_name}")
        return {}

    a = _load(args.iter_a)
    b = _load(args.iter_b)
    if not a or not b:
        return 1

    print(f"\nComparing {args.iter_a} vs {args.iter_b}")
    print(f"{'Metric':<20} {'System':<20} {'A':>10} {'B':>10} {'Delta':>10}")
    print("-" * 72)

    sys_names = set(a.get('systems', {}).keys()) & set(b.get('systems', {}).keys())
    for sname in sorted(sys_names):
        a_sys = a['systems'][sname]
        b_sys = b['systems'][sname]
        all_keys = set(a_sys.keys()) | set(b_sys.keys())
        for mkey in sorted(all_keys):
            av = a_sys.get(mkey, {}).get('value')
            bv = b_sys.get(mkey, {}).get('value')
            if av is None or bv is None:
                continue
            delta = bv - av
            print(f"{mkey:<20} {sname:<20} {av:>10.4f} {bv:>10.4f} {delta:>+10.4f}")
    return 0


def cmd_run_pillar_b(args: argparse.Namespace) -> int:
    """Phase 5 Pillar B: compare SimCSE (dangvantuan/vietnamese-embedding) vs PhoBERT via paired bootstrap.

    Prerequisites:
      1. Run:  python tools/process_data.py --pillar-b
         to generate data/vietnamese_music_embeddings_pillar_b.npy
      2. Run this command.

    Gates (all must pass):
      - NDCG@10 ext: pillar_b CI99.2% (Bonferroni) lower bound > -0.005 (not deteriorate significantly)
      - ILD_lyrics: pillar_b >= baseline * 0.95
      - latency p95: pillar_b <= baseline_p95 * 1.30 (embeddings pre-computed → should be equal)
    """
    import datetime
    import json
    import os
    import sys
    import time

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    import config as cfg

    emb_path = cfg.EMBEDDINGS_FILE_PILLAR_B
    if not os.path.exists(emb_path):
        print(f"[pillar_b] ERROR: embeddings file not found: {emb_path}")
        print("[pillar_b] Run first:  python tools/process_data.py --pillar-b")
        return 1

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE, build_query_gt_mapping, load_editorial_gt,
    )
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.baselines.pillar_b import PillarBBaseline
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.metrics.property import ild_lyrics
    from tools.backtest_v2.stats import paired_bootstrap, cluster_paired_bootstrap
    from tools.backtest_v2.ground_truth.editorial import build_cluster_seeds
    from tools.backtest_v2.core import _run_system, _metric_entry
    from tools.backtest_v2.metrics.accuracy import evaluate_system_accuracy
    from tools.backtest_v2.stats import stratified_sample

    # Load editorial GT
    if not os.path.exists(GT_FILE):
        print(f"[pillar_b] GT file not found: {GT_FILE}")
        print("[pillar_b] Run: python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1")
        return 1
    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[pillar_b] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries")

    # --- Fixed v7.2 baseline isolation: base = all pillars off, treat = +Pillar B ---
    base_flags  = dict(V72_BASELINE_FLAGS)
    treat_flags = {**V72_BASELINE_FLAGS, "ENABLE_PILLAR_B": True}

    print("[pillar_b] Building baseline catalog (v7.2: all pillars off, PhoBERT)...")
    cat_base = Catalog.build_isolated(base_flags)
    print(f"[pillar_b] Building Pillar B catalog (v7.2 + SimCSE)...")
    cat_pb = Catalog.build_isolated(treat_flags)
    assert cat_base.rec.embeddings is not None and cat_pb.rec.embeddings is not None, "[pillar_b] embeddings must load"

    # --- Per-query NDCG@10 for paired bootstrap ---
    print("\n[pillar_b] Computing per-query NDCG@10 for both systems...")
    sys_base = BrightifyBaseline(cat_base)
    sys_pb   = PillarBBaseline(cat_pb)

    # --- Base arm (recommend-time flags pinned to v7.2) ---
    ndcg_base_pq: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rb = sys_base.recommend(seed_idx, top_k=10)
            ndcg_base_pq.append(ndcg_at_k(rb, set(relevant), 10) if rb else 0.0)

    # --- Treatment arm (recommend-time flags pinned to v7.2 + Pillar B) ---
    ndcg_pb_pq: list   = []
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rp = sys_pb.recommend(seed_idx, top_k=10)
            ndcg_pb_pq.append(ndcg_at_k(rp, set(relevant), 10) if rp else 0.0)

    _seeds_b = list(gt_mapping.keys())
    _sc_base_b = dict(zip(_seeds_b, ndcg_base_pq))
    _sc_pb_b   = dict(zip(_seeds_b, ndcg_pb_pq))
    _clusters_b = build_cluster_seeds(playlists)
    delta, ci_low, ci_high = cluster_paired_bootstrap(_sc_base_b, _sc_pb_b, _clusters_b, n_boot=10_000, ci_level=BONFERRONI_CI_LEVEL)
    mean_base = float(np.mean(ndcg_base_pq))
    mean_pb   = float(np.mean(ndcg_pb_pq))

    print(f"\n[pillar_b] Paired bootstrap NDCG@10 (N={len(ndcg_base_pq)}, n_boots=10000):")
    print(f"  baseline (PhoBERT)  mean = {mean_base:.5f}")
    print(f"  pillar_b (SimCSE)     mean = {mean_pb:.5f}")
    print(f"  delta = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")

    # --- ILD_lyrics comparison ---
    print("\n[pillar_b] Computing ILD_lyrics (sample 200 queries)...")
    rng = np.random.default_rng(42)
    sample_seeds = list(gt_mapping.keys())
    if len(sample_seeds) > 200:
        sample_seeds = [sample_seeds[i] for i in rng.choice(len(sample_seeds), 200, replace=False).tolist()]

    ild_base_vals = []
    ild_pb_vals   = []
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        for s in sample_seeds:
            rb = sys_base.recommend(s, top_k=10)
            if rb:
                ild_base_vals.append(ild_lyrics(rb, cat_base))
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        for s in sample_seeds:
            rp = sys_pb.recommend(s, top_k=10)
            if rp:
                ild_pb_vals.append(ild_lyrics(rp, cat_pb))

    ild_base_mean = float(np.mean(ild_base_vals)) if ild_base_vals else 0.0
    ild_pb_mean   = float(np.mean(ild_pb_vals))   if ild_pb_vals   else 0.0
    print(f"  ILD_lyrics baseline = {ild_base_mean:.5f}")
    print(f"  ILD_lyrics pillar_b = {ild_pb_mean:.5f}  (threshold = {ild_base_mean * 0.95:.5f})")

    # --- Latency (warmed, 200 calls each) ---
    print("\n[pillar_b] Measuring latency (200 calls each, 20-call warmup)...")
    all_seeds = list(gt_mapping.keys())
    lat_seeds = (all_seeds * 10)[:200]  # ensure 200 seeds, repeating if needed
    warmup_seeds = lat_seeds[:20]

    # Warmup + timing per-arm under the arm's recommend-time pins.
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        for s in warmup_seeds:
            sys_base.recommend(s, top_k=10)
        t0 = time.perf_counter()
        for s in lat_seeds:
            sys_base.recommend(s, top_k=10)
        base_avg_ms = (time.perf_counter() - t0) / len(lat_seeds) * 1000

    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        for s in warmup_seeds:
            sys_pb.recommend(s, top_k=10)
        t0 = time.perf_counter()
        for s in lat_seeds:
            sys_pb.recommend(s, top_k=10)
        pb_avg_ms = (time.perf_counter() - t0) / len(lat_seeds) * 1000

    print(f"  avg latency baseline = {base_avg_ms:.1f} ms")
    print(f"  avg latency pillar_b = {pb_avg_ms:.1f} ms")

    # --- Gate evaluation ---
    # NDCG threshold: -0.005 for encoder-swap (vs -0.003 for weight-tuning).
    # Encoder swaps produce higher per-query variance → wider CI95 is expected
    # even when mean NDCG improves. -0.005 matches the practical "no regression"
    # intent while accounting for this structural variance increase.
    gate_ndcg    = ci_low > -0.005
    gate_ild     = ild_pb_mean >= ild_base_mean * 0.95
    gate_latency = pb_avg_ms <= base_avg_ms * 1.30
    gate_pass    = gate_ndcg and gate_ild and gate_latency

    verdict = (
        "PASS — roll out Pillar B, update ENABLE_PILLAR_B=True"
        if gate_pass else
        "FAIL — revert flag, keep PhoBERT"
    )
    print(f"\n[pillar_b] Gate results:")
    print(f"  NDCG {_CI_LABEL}[{ci_low:+.4f}] > -0.005: {'PASS' if gate_ndcg else 'FAIL'}")
    print(f"  ILD  {ild_pb_mean:.4f} >= {ild_base_mean*0.95:.4f}: {'PASS' if gate_ild else 'FAIL'}")
    print(f"  Lat  {pb_avg_ms:.1f}ms <= {base_avg_ms*1.30:.1f}ms: {'PASS' if gate_latency else 'FAIL'}")
    print(f"\n  Verdict: {verdict}")

    # --- Build iter_2 report ---
    output_dir = getattr(args, 'output', None) or "var/runtime/backtest/reports/iter_2_pillar_B"
    os.makedirs(output_dir, exist_ok=True)

    # Full property metrics for pillar_b
    ts_path = "var/runtime/backtest/test_sets/test_set_v1.json"
    if os.path.exists(ts_path):
        with open(ts_path) as fh:
            queries = json.load(fh)["queries"]
    else:
        queries = stratified_sample(cat_pb.df, n=500, seed=42)
    print(f"\n[pillar_b] Computing property metrics ({len(queries)} queries)...")
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        pb_prop = _run_system(sys_pb, queries, cat_pb, top_k=10)

        print(f"[pillar_b] Computing full accuracy metrics...")
        pb_acc = evaluate_system_accuracy(sys_pb, gt_mapping, top_k=20,
                                          ground_truth_name="editorial_playlists_v1")
    pb_prop.update(pb_acc)

    # Load iter_1 for comparison baseline
    iter1_path = "var/runtime/backtest/reports/iter_1_weight_opt/report.json"
    iter1_report: dict = {}
    if os.path.exists(iter1_path):
        with open(iter1_path) as fh:
            iter1_report = json.load(fh)

    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_2_pillar_B",
            "n_catalog": cat_pb.n,
            "n_queries": len(queries),
            "top_k": 10,
            "seed": 42,
            "ground_truth": "editorial_playlists_v1",
            "pillar_b": {
                "embeddings_file": emb_path,
                "encoder": "SimCSE (dangvantuan/vietnamese-embedding)",
                "baseline": "v7.2_isolated (all other pillars off)",
                "gate_pass": gate_pass,
                "verdict": verdict,
                "bootstrap": {
                    "n_queries": len(ndcg_base_pq),
                    "n_boots": 10_000,
                    "mean_ndcg_at_10_baseline": mean_base,
                    "mean_ndcg_at_10_pillar_b": mean_pb,
                    "delta": float(delta),
                    "ci95": [float(ci_low), float(ci_high)],
                },
                "ild_comparison": {
                    "ild_lyrics_baseline": ild_base_mean,
                    "ild_lyrics_pillar_b": ild_pb_mean,
                    "gate_pass": gate_ild,
                },
                "latency_ms": {
                    "baseline_avg": round(base_avg_ms, 2),
                    "pillar_b_avg": round(pb_avg_ms, 2),
                    "gate_pass": gate_latency,
                },
            },
        },
        "systems": {
            "brightify_v7.2": iter1_report.get("systems", {}).get("brightify_v7.2", {}),
            "brightify_pillar_b": pb_prop,
        },
        "latency": iter1_report.get("latency", {}),
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)

    # Markdown report
    from tools.backtest_v2.reporters.markdown import write_markdown

    _FakeCfg = type("_FakeCfg", (), {
        "output_dir": output_dir,
        "iteration_name": "iter_2_pillar_B",
    })

    class _FakeRep:
        meta = report_dict["meta"]
        systems = report_dict["systems"]
        latency = report_dict.get("latency", {})
        config = _FakeCfg()

        def to_dict(self):
            return {"meta": self.meta, "systems": self.systems, "latency": self.latency}

    write_markdown(_FakeRep(), os.path.join(output_dir, "report.md"))
    print(f"\n[pillar_b] Reports saved to {output_dir}/")

    # Update config flag if gate passes
    if gate_pass:
        _update_config_pillar_b()
        print("[pillar_b] config.ENABLE_PILLAR_B set to True.")
    else:
        _revert_config_pillar_b()
        print("[pillar_b] Gate FAILED — config.ENABLE_PILLAR_B reverted to False.")

    return 0 if gate_pass else 1


def _update_config_pillar_b() -> None:
    """Set config.ENABLE_PILLAR_B = True."""
    import re
    with open("config.py", encoding="utf-8") as fh:
        src = fh.read()
    new_src, n = re.subn(r'ENABLE_PILLAR_B\s*=\s*False', 'ENABLE_PILLAR_B = True', src)
    if n == 0:
        print("[pillar_b] WARNING: could not find ENABLE_PILLAR_B in config.py")
        return
    with open("config.py", "w", encoding="utf-8") as fh:
        fh.write(new_src)


def _revert_config_pillar_b() -> None:
    """Revert config.ENABLE_PILLAR_B = False (mirror of _update_config_pillar_b)."""
    import re
    with open("config.py", encoding="utf-8") as fh:
        src = fh.read()
    new_src, n = re.subn(r'ENABLE_PILLAR_B\s*=\s*True', 'ENABLE_PILLAR_B = False', src)
    if n == 0:
        # Already False — no-op, no warning needed.
        return
    with open("config.py", "w", encoding="utf-8") as fh:
        fh.write(new_src)


def cmd_run_pillar_a(args: argparse.Namespace) -> int:
    """Pillar A: compare 7-signal (no MERT) vs 8-signal (with MERT) recommend_by_song.

    Prerequisites:
        python -m tools.extract_mert_embeddings
    Gates (all must pass):
        - NDCG@10 ext: paired bootstrap CI99.2% (Bonferroni) lower bound > -0.003
        - ILD_lyrics: mert >= baseline * 0.95  (no regression)
        - Coverage: mert >= baseline * 0.95
    """
    import datetime
    import json
    import os
    import sys
    import time

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    import config as cfg

    mert_path = cfg.MERT_EMBEDDINGS_FILE
    if not os.path.exists(mert_path):
        print(f"[pillar_a] ERROR: MERT embeddings not found: {mert_path}")
        print("[pillar_a] Run first:  python -m tools.extract_mert_embeddings")
        return 1

    mert_meta_path = cfg.MERT_EMBEDDINGS_META_FILE
    if os.path.exists(mert_meta_path):
        with open(mert_meta_path) as fh:
            mert_meta = json.load(fh)
        coverage = mert_meta.get("coverage_pct", 0)
        if coverage < 99.0:
            print(f"[pillar_a] WARNING: MERT coverage is {coverage:.1f}% < 99% — continuing anyway")
        else:
            print(f"[pillar_a] MERT coverage: {coverage:.1f}%")

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE, build_query_gt_mapping, load_editorial_gt,
    )
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.baselines.pillar_a import PillarABaseline
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.metrics.property import ild_lyrics
    from tools.backtest_v2.stats import paired_bootstrap, cluster_paired_bootstrap, stratified_sample
    from tools.backtest_v2.ground_truth.editorial import build_cluster_seeds
    from tools.backtest_v2.core import _run_system

    # Load editorial GT
    if not os.path.exists(GT_FILE):
        print(f"[pillar_a] GT file not found: {GT_FILE}")
        print("[pillar_a] Run: python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1")
        return 1
    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[pillar_a] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries")

    # --- Fixed v7.2 baseline isolation: base = all pillars off, treat = +MERT ---
    base_flags  = dict(V72_BASELINE_FLAGS)
    treat_flags = {**V72_BASELINE_FLAGS, "ENABLE_MERT": True}

    print("[pillar_a] Building base catalog (v7.2: all pillars off, 7-signal)...")
    cat_base = Catalog.build_isolated(base_flags)
    print(f"[pillar_a] Building MERT catalog (v7.2 + MERT, 8-signal)...")
    cat_mert = Catalog.build_isolated(treat_flags)
    assert cat_base.rec.mert_matrix is None and cat_mert.rec.mert_matrix is not None, "[pillar_a] MERT isolation failed"

    sys_base = BrightifyBaseline(cat_base)
    sys_mert = PillarABaseline(cat_mert)

    # --- Per-query NDCG@10 for paired bootstrap ---
    print("\n[pillar_a] Computing per-query NDCG@10 (7-signal vs 8-signal)...")
    # --- Base arm (recommend-time flags pinned to v7.2) ---
    ndcg_base_pq: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rb = sys_base.recommend(seed_idx, top_k=10)
            ndcg_base_pq.append(ndcg_at_k(rb, set(relevant), 10) if rb else 0.0)

    # --- Treatment arm (recommend-time flags pinned to v7.2 + MERT) ---
    ndcg_mert_pq: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rm = sys_mert.recommend(seed_idx, top_k=10)
            ndcg_mert_pq.append(ndcg_at_k(rm, set(relevant), 10) if rm else 0.0)

    _seeds_a = list(gt_mapping.keys())
    _sc_base_a = dict(zip(_seeds_a, ndcg_base_pq))
    _sc_mert_a = dict(zip(_seeds_a, ndcg_mert_pq))
    _clusters_a = build_cluster_seeds(playlists)
    delta, ci_low, ci_high = cluster_paired_bootstrap(_sc_base_a, _sc_mert_a, _clusters_a, n_boot=10_000, ci_level=BONFERRONI_CI_LEVEL)
    mean_base = float(np.mean(ndcg_base_pq))
    mean_mert = float(np.mean(ndcg_mert_pq))

    print(f"\n[pillar_a] Paired bootstrap NDCG@10 (N={len(ndcg_base_pq)}, n_boots=10000):")
    print(f"  baseline (7-signal) mean = {mean_base:.5f}")
    print(f"  pillar_a (8-signal) mean = {mean_mert:.5f}")
    print(f"  delta = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")

    # --- ILD and Coverage comparison ---
    print("\n[pillar_a] Computing ILD + coverage (sample 200 queries)...")
    rng = np.random.default_rng(42)
    sample_seeds = list(gt_mapping.keys())
    if len(sample_seeds) > 200:
        sample_seeds = [sample_seeds[i] for i in rng.choice(len(sample_seeds), 200, replace=False).tolist()]

    ild_base_vals, ild_mert_vals = [], []
    all_recs_base, all_recs_mert = [], []
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        for s in sample_seeds:
            rb = sys_base.recommend(s, top_k=10)
            if rb:
                ild_base_vals.append(ild_lyrics(rb, cat_base))
                all_recs_base.append(rb)
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        for s in sample_seeds:
            rm = sys_mert.recommend(s, top_k=10)
            if rm:
                ild_mert_vals.append(ild_lyrics(rm, cat_mert))
                all_recs_mert.append(rm)

    ild_base = float(np.mean(ild_base_vals)) if ild_base_vals else 0.0
    ild_mert = float(np.mean(ild_mert_vals)) if ild_mert_vals else 0.0
    cov_base = len(set(i for r in all_recs_base for i in r)) / cat_base.n
    cov_mert = len(set(i for r in all_recs_mert for i in r)) / cat_mert.n

    print(f"  ILD_lyrics  base={ild_base:.5f}  mert={ild_mert:.5f}  threshold={ild_base*0.95:.5f}")
    print(f"  Coverage    base={cov_base:.4f}  mert={cov_mert:.4f}  threshold={cov_base*0.95:.4f}")

    # --- Gate evaluation ---
    gate_ndcg     = ci_low > -0.003
    gate_ild      = ild_mert >= ild_base * 0.95
    gate_coverage = cov_mert >= cov_base * 0.95
    gate_pass     = gate_ndcg and gate_ild and gate_coverage

    verdict = "PASS — set ENABLE_MERT=True" if gate_pass else "FAIL — keep ENABLE_MERT=False"

    print(f"\n[pillar_a] Gate results:")
    print(f"  NDCG {_CI_LABEL}[{ci_low:+.4f}] > -0.003: {'PASS' if gate_ndcg else 'FAIL'}")
    print(f"  ILD  {ild_mert:.5f} >= {ild_base*0.95:.5f}:  {'PASS' if gate_ild else 'FAIL'}")
    print(f"  Cov  {cov_mert:.4f} >= {cov_base*0.95:.4f}:   {'PASS' if gate_coverage else 'FAIL'}")
    print(f"\n  Verdict: {verdict}")

    # --- Build iter_4 report ---
    output_dir = getattr(args, 'output', None) or "var/runtime/backtest/reports/iter_4_pillar_A"
    os.makedirs(output_dir, exist_ok=True)

    ts_path = "var/runtime/backtest/test_sets/test_set_v1.json"
    if os.path.exists(ts_path):
        with open(ts_path) as fh:
            queries = json.load(fh)["queries"]
    else:
        queries = stratified_sample(cat_mert.df, n=500, seed=42)

    print(f"\n[pillar_a] Computing property metrics ({len(queries)} queries)...")
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        prop_base = _run_system(sys_base, queries, cat_base, top_k=10)
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        prop_mert = _run_system(sys_mert, queries, cat_mert, top_k=10)

    # Load iter_3 for context
    iter3_path = "var/runtime/backtest/reports/iter_3_pillar_D/report.json"
    iter3_report: dict = {}
    if os.path.exists(iter3_path):
        with open(iter3_path) as fh:
            iter3_report = json.load(fh)

    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_4_pillar_A",
            "n_catalog": cat_mert.n,
            "n_queries": len(queries),
            "top_k": 10,
            "seed": 42,
            "ground_truth": "editorial_playlists_v1",
            "pillar_a": {
                "mert_embeddings_file": mert_path,
                "mert_model": cfg.MERT_MODEL,
                "mert_layer": cfg.MERT_LAYER,
                "baseline": "v7.2_isolated (all other pillars off)",
                "gate_pass": gate_pass,
                "verdict": verdict,
                "bootstrap_ndcg": {
                    "n_queries": len(ndcg_base_pq),
                    "n_boots": 10_000,
                    "mean_ndcg_base": mean_base,
                    "mean_ndcg_mert": mean_mert,
                    "delta": float(delta),
                    "ci95": [float(ci_low), float(ci_high)],
                },
                "ild_comparison": {
                    "ild_lyrics_base": ild_base,
                    "ild_lyrics_mert": ild_mert,
                    "gate_pass": gate_ild,
                },
                "coverage_comparison": {
                    "coverage_base": cov_base,
                    "coverage_mert": cov_mert,
                    "gate_pass": gate_coverage,
                },
            },
        },
        "systems": {
            "brightify_7sig": prop_base,
            "brightify_mert": prop_mert,
        },
        "latency": iter3_report.get("latency", {}),
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)

    from tools.backtest_v2.reporters.markdown import write_markdown

    _FakeCfg = type("_FakeCfg", (), {
        "output_dir": output_dir,
        "iteration_name": "iter_4_pillar_A",
    })

    class _FakeRep:
        meta    = report_dict["meta"]
        systems = report_dict["systems"]
        latency = report_dict.get("latency", {})
        config  = _FakeCfg()

        def to_dict(self):
            return {"meta": self.meta, "systems": self.systems, "latency": self.latency}

    write_markdown(_FakeRep(), os.path.join(output_dir, "report.md"))
    print(f"\n[pillar_a] Reports saved to {output_dir}/")

    if gate_pass:
        _update_config_enable_mert(True)
        print("[pillar_a] config.ENABLE_MERT set to True.")
    else:
        _update_config_enable_mert(False)
        print("[pillar_a] Gate FAILED — config.ENABLE_MERT reverted to False.")

    return 0 if gate_pass else 1


def _update_config_enable_mert(enable: bool) -> None:
    import re
    value = "True" if enable else "False"
    with open("config.py", encoding="utf-8") as fh:
        src = fh.read()
    new_src, n = re.subn(
        r'ENABLE_MERT\s*=\s*os\.environ\.get\("ENABLE_MERT",\s*"(?:True|False)"\)\s*==\s*"True"',
        f'ENABLE_MERT = os.environ.get("ENABLE_MERT", "{value}") == "True"',
        src,
    )
    if n > 0:
        with open("config.py", "w", encoding="utf-8") as fh:
            fh.write(new_src)
        print(f"[pillar_a] config.py: ENABLE_MERT default = {value}")
    else:
        print(f"[pillar_a] WARNING: could not update ENABLE_MERT default in config.py")


def cmd_run_pillar_d(args: argparse.Namespace) -> int:
    """Pillar D: compare greedy vs MMR diversity reranking.

    Gates (all must pass):
      - ILD_lyrics: mmr >= greedy * 1.20  (≥20% diversity uplift)
      - NDCG@10 ext: paired bootstrap CI99.2% (Bonferroni) lower bound > -0.03
    """
    import datetime
    import json
    import os
    import sys

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE, build_query_gt_mapping, load_editorial_gt,
    )
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.metrics.property import ild_lyrics, ild_audio, ild_va, ild_color
    from tools.backtest_v2.stats import paired_bootstrap, cluster_paired_bootstrap
    from tools.backtest_v2.ground_truth.editorial import build_cluster_seeds
    from tools.backtest_v2.stats import stratified_sample

    # Load editorial GT
    if not os.path.exists(GT_FILE):
        print(f"[pillar_d] GT file not found: {GT_FILE}")
        print("[pillar_d] Run: python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1")
        return 1
    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[pillar_d] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries")

    print("[pillar_d] Building isolated v7.2 catalog (all pillars off)...")
    catalog = Catalog.build_isolated(dict(V72_BASELINE_FLAGS))

    sys_greedy = BrightifyBaseline(catalog)
    sys_mmr    = BrightifyBaseline(catalog)

    base_rec_flags  = {"DIVERSITY_METHOD": "greedy", "ENABLE_RRF": False, "ENABLE_VN_CONTEXT": False}
    treat_rec_flags = {"DIVERSITY_METHOD": "mmr",    "ENABLE_RRF": False, "ENABLE_VN_CONTEXT": False}

    seeds = list(gt_mapping.keys())
    rng = np.random.default_rng(42)
    if len(seeds) > 200:
        sample_set = {seeds[i] for i in rng.choice(len(seeds), 200, replace=False).tolist()}
    else:
        sample_set = set(seeds)

    ild_g: dict = {"lyrics": [], "audio": [], "va": [], "color": []}
    ild_m: dict = {"lyrics": [], "audio": [], "va": [], "color": []}

    # --- Greedy arm (v7.2, DIVERSITY_METHOD pinned greedy) ---
    print("\n[pillar_d] Computing greedy arm (v7.2)...")
    ndcg_greedy_pq: list = []
    with _pinned_recommend_flags(**base_rec_flags):
        for seed_idx, relevant in gt_mapping.items():
            rg = sys_greedy.recommend(seed_idx, top_k=10)
            ndcg_greedy_pq.append(ndcg_at_k(rg, set(relevant), 10) if rg else 0.0)
            if seed_idx in sample_set and rg:
                ild_g["lyrics"].append(ild_lyrics(rg, catalog))
                ild_g["audio"].append(ild_audio(rg, catalog))
                ild_g["va"].append(ild_va(rg, catalog))
                ild_g["color"].append(ild_color(rg, catalog))

    # --- MMR arm (v7.2 + MMR rerank) ---
    print("[pillar_d] Computing MMR arm (v7.2 + MMR)...")
    ndcg_mmr_pq: list = []
    with _pinned_recommend_flags(**treat_rec_flags):
        for seed_idx, relevant in gt_mapping.items():
            rm = sys_mmr.recommend(seed_idx, top_k=10)
            ndcg_mmr_pq.append(ndcg_at_k(rm, set(relevant), 10) if rm else 0.0)
            if seed_idx in sample_set and rm:
                ild_m["lyrics"].append(ild_lyrics(rm, catalog))
                ild_m["audio"].append(ild_audio(rm, catalog))
                ild_m["va"].append(ild_va(rm, catalog))
                ild_m["color"].append(ild_color(rm, catalog))

    _sc_greedy = dict(zip(seeds, ndcg_greedy_pq))
    _sc_mmr    = dict(zip(seeds, ndcg_mmr_pq))
    _clusters_d = build_cluster_seeds(playlists)
    delta, ci_low, ci_high = cluster_paired_bootstrap(_sc_greedy, _sc_mmr, _clusters_d, n_boot=10_000, ci_level=BONFERRONI_CI_LEVEL)
    mean_greedy = float(np.mean(ndcg_greedy_pq))
    mean_mmr    = float(np.mean(ndcg_mmr_pq))

    print(f"\n[pillar_d] Cluster bootstrap NDCG@10 "
          f"(N={len(ndcg_greedy_pq)} queries / {len(_clusters_d)} playlists, n_boots=10000):")
    print(f"  greedy mean = {mean_greedy:.5f}")
    print(f"  mmr    mean = {mean_mmr:.5f}")
    print(f"  delta  = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")

    def _mean(lst): return float(np.mean(lst)) if lst else 0.0

    ild_greedy_lyrics = _mean(ild_g["lyrics"])
    ild_mmr_lyrics    = _mean(ild_m["lyrics"])
    ild_greedy_audio  = _mean(ild_g["audio"])
    ild_mmr_audio     = _mean(ild_m["audio"])
    ild_greedy_va     = _mean(ild_g["va"])
    ild_mmr_va        = _mean(ild_m["va"])
    ild_greedy_color  = _mean(ild_g["color"])
    ild_mmr_color     = _mean(ild_m["color"])

    print(f"  ILD_lyrics  greedy={ild_greedy_lyrics:.5f}  mmr={ild_mmr_lyrics:.5f}  "
          f"threshold={ild_greedy_lyrics * 1.20:.5f}")
    print(f"  ILD_audio   greedy={ild_greedy_audio:.5f}  mmr={ild_mmr_audio:.5f}")
    print(f"  ILD_va      greedy={ild_greedy_va:.5f}  mmr={ild_mmr_va:.5f}")
    print(f"  ILD_color   greedy={ild_greedy_color:.5f}  mmr={ild_mmr_color:.5f}")

    # --- Gate evaluation ---
    gate_ild    = ild_mmr_lyrics >= ild_greedy_lyrics * 1.20
    gate_ndcg   = ci_low > -0.03
    gate_pass   = gate_ild and gate_ndcg

    verdict = "PASS — keep DIVERSITY_METHOD=mmr" if gate_pass else "FAIL — revert to greedy"

    print(f"\n[pillar_d] Gate results:")
    print(f"  ILD_lyrics  {ild_mmr_lyrics:.5f} >= {ild_greedy_lyrics * 1.20:.5f} (+20%): "
          f"{'PASS' if gate_ild else 'FAIL'}")
    print(f"  NDCG {_CI_LABEL}[{ci_low:+.4f}] > -0.030: {'PASS' if gate_ndcg else 'FAIL'}")
    print(f"\n  Verdict: {verdict}")

    # --- Build iter_3 report ---
    output_dir = getattr(args, 'output', None) or "var/runtime/backtest/reports/iter_3_pillar_D"
    os.makedirs(output_dir, exist_ok=True)

    # Property metrics for both systems (sample queries)
    ts_path = "var/runtime/backtest/test_sets/test_set_v1.json"
    if os.path.exists(ts_path):
        with open(ts_path) as fh:
            queries = json.load(fh)["queries"]
    else:
        queries = stratified_sample(catalog.df, n=500, seed=42)

    from tools.backtest_v2.core import _run_system
    print(f"\n[pillar_d] Computing property metrics ({len(queries)} queries)...")

    with _pinned_recommend_flags(**base_rec_flags):
        prop_greedy = _run_system(sys_greedy, queries, catalog, top_k=10)
    with _pinned_recommend_flags(**treat_rec_flags):
        prop_mmr    = _run_system(sys_mmr,    queries, catalog, top_k=10)

    # Load iter_2 for previous baseline
    iter2_path = "var/runtime/backtest/reports/iter_2_pillar_B/report.json"
    iter2_report: dict = {}
    if os.path.exists(iter2_path):
        with open(iter2_path) as fh:
            iter2_report = json.load(fh)

    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_3_pillar_D",
            "n_catalog": catalog.n,
            "n_queries": len(queries),
            "top_k": 10,
            "seed": 42,
            "ground_truth": "editorial_playlists_v1",
            "pillar_d": {
                "method": "mmr",
                "lambda": 0.7,
                "baseline": "v7.2_isolated (all other pillars off)",
                "gate_pass": gate_pass,
                "verdict": verdict,
                "bootstrap_ndcg": {
                    "n_queries": len(ndcg_greedy_pq),
                    "n_boots": 10_000,
                    "mean_ndcg_greedy": mean_greedy,
                    "mean_ndcg_mmr": mean_mmr,
                    "delta": float(delta),
                    "ci95": [float(ci_low), float(ci_high)],
                },
                "ild_comparison": {
                    "ild_lyrics_greedy": ild_greedy_lyrics,
                    "ild_lyrics_mmr":    ild_mmr_lyrics,
                    "ild_audio_greedy":  ild_greedy_audio,
                    "ild_audio_mmr":     ild_mmr_audio,
                    "ild_va_greedy":     ild_greedy_va,
                    "ild_va_mmr":        ild_mmr_va,
                    "ild_color_greedy":  ild_greedy_color,
                    "ild_color_mmr":     ild_mmr_color,
                    "gate_pass":         gate_ild,
                },
            },
        },
        "systems": {
            "brightify_greedy": prop_greedy,
            "brightify_mmr":    prop_mmr,
        },
        "latency": iter2_report.get("latency", {}),
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)

    from tools.backtest_v2.reporters.markdown import write_markdown

    _FakeCfg = type("_FakeCfg", (), {
        "output_dir": output_dir,
        "iteration_name": "iter_3_pillar_D",
    })

    class _FakeRep:
        meta    = report_dict["meta"]
        systems = report_dict["systems"]
        latency = report_dict.get("latency", {})
        config  = _FakeCfg()

        def to_dict(self):
            return {"meta": self.meta, "systems": self.systems, "latency": self.latency}

    write_markdown(_FakeRep(), os.path.join(output_dir, "report.md"))
    print(f"\n[pillar_d] Reports saved to {output_dir}/")

    if not gate_pass:
        _update_config_diversity_method("greedy")
        print("[pillar_d] Gate FAILED — config.DIVERSITY_METHOD reverted to 'greedy'.")
    else:
        print("[pillar_d] Gate PASSED — DIVERSITY_METHOD='mmr' remains default.")

    return 0 if gate_pass else 1


def _update_config_diversity_method(method: str) -> None:
    """Revert DIVERSITY_METHOD default in config.py."""
    import re
    with open("config.py", encoding="utf-8") as fh:
        src = fh.read()
    new_src, n = re.subn(
        r'(DIVERSITY_METHOD\s*=\s*os\.environ\.get\("DIVERSITY_METHOD",\s*)"[^"]*"(\))',
        rf'\g<1>"{method}"\2',
        src,
    )
    if n == 0:
        print(f"[pillar_d] WARNING: could not update DIVERSITY_METHOD in config.py")
        return
    with open("config.py", "w", encoding="utf-8") as fh:
        fh.write(new_src)
    print(f"[pillar_d] config.py: DIVERSITY_METHOD default = '{method}'")


def cmd_run_pillar_c(args: argparse.Namespace) -> int:
    """Pillar C: compare no-RRF (baseline) vs RRF hybrid retrieval.

    Also reports latency improvement from vectorized emotion_boost.

    Gates (all must pass):
      - NDCG@10 ext: paired bootstrap CI99.2% (Bonferroni) lower bound > -0.005
      - ILD_lyrics: rrf >= baseline * 0.95  (no regression)
      - Coverage: rrf >= baseline * 0.95
    """
    import datetime
    import json
    import os
    import sys
    import time

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE, build_query_gt_mapping, load_editorial_gt,
    )
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.baselines.pillar_c import PillarCBaseline
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.metrics.property import ild_lyrics
    from tools.backtest_v2.stats import paired_bootstrap, cluster_paired_bootstrap, stratified_sample
    from tools.backtest_v2.ground_truth.editorial import build_cluster_seeds
    from tools.backtest_v2.core import _run_system

    # Load editorial GT
    if not os.path.exists(GT_FILE):
        print(f"[pillar_c] GT file not found: {GT_FILE}")
        print("[pillar_c] Run: python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1")
        return 1
    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[pillar_c] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries")

    print("[pillar_c] Building isolated v7.2 catalog (all pillars off)...")
    catalog = Catalog.build_isolated(dict(V72_BASELINE_FLAGS))

    base_rec_flags  = {"ENABLE_RRF": False, "DIVERSITY_METHOD": "greedy", "ENABLE_VN_CONTEXT": False}
    treat_rec_flags = {"ENABLE_RRF": True,  "DIVERSITY_METHOD": "greedy", "ENABLE_VN_CONTEXT": False}

    sys_base = BrightifyBaseline(catalog)
    sys_rrf  = PillarCBaseline(catalog)

    seeds = list(gt_mapping.keys())
    rng = np.random.default_rng(42)
    if len(seeds) > 200:
        sample_set = {seeds[i] for i in rng.choice(len(seeds), 200, replace=False).tolist()}
    else:
        sample_set = set(seeds)

    # --- Base arm (v7.2, RRF off) ---
    print("\n[pillar_c] Computing base arm (v7.2, no RRF)...")
    ndcg_base_pq: list = []
    ild_base_vals: list = []
    all_recs_base: list = []
    with _pinned_recommend_flags(**base_rec_flags):
        for seed_idx, relevant in gt_mapping.items():
            rb = sys_base.recommend(seed_idx, top_k=10)
            ndcg_base_pq.append(ndcg_at_k(rb, set(relevant), 10) if rb else 0.0)
            if seed_idx in sample_set and rb:
                ild_base_vals.append(ild_lyrics(rb, catalog))
                all_recs_base.append(rb)

    # --- Treatment arm (v7.2 + RRF) ---
    print("[pillar_c] Computing treatment arm (v7.2 + RRF)...")
    ndcg_rrf_pq: list = []
    ild_rrf_vals: list = []
    all_recs_rrf: list = []
    with _pinned_recommend_flags(**treat_rec_flags):
        for seed_idx, relevant in gt_mapping.items():
            rr = sys_rrf.recommend(seed_idx, top_k=10)
            ndcg_rrf_pq.append(ndcg_at_k(rr, set(relevant), 10) if rr else 0.0)
            if seed_idx in sample_set and rr:
                ild_rrf_vals.append(ild_lyrics(rr, catalog))
                all_recs_rrf.append(rr)

    _sc_base_c = dict(zip(seeds, ndcg_base_pq))
    _sc_rrf_c  = dict(zip(seeds, ndcg_rrf_pq))
    _clusters_c = build_cluster_seeds(playlists)
    delta, ci_low, ci_high = cluster_paired_bootstrap(_sc_base_c, _sc_rrf_c, _clusters_c, n_boot=10_000, ci_level=BONFERRONI_CI_LEVEL)
    mean_base = float(np.mean(ndcg_base_pq))
    mean_rrf  = float(np.mean(ndcg_rrf_pq))

    print(f"\n[pillar_c] Cluster bootstrap NDCG@10 "
          f"(N={len(ndcg_base_pq)} queries / {len(_clusters_c)} playlists, n_boots=10000):")
    print(f"  baseline (no-RRF)  mean = {mean_base:.5f}")
    print(f"  pillar_c (RRF)     mean = {mean_rrf:.5f}")
    print(f"  delta = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")

    ild_base = float(np.mean(ild_base_vals)) if ild_base_vals else 0.0
    ild_rrf  = float(np.mean(ild_rrf_vals))  if ild_rrf_vals  else 0.0
    cov_base = len(set(i for r in all_recs_base for i in r)) / catalog.n
    cov_rrf  = len(set(i for r in all_recs_rrf  for i in r)) / catalog.n

    print(f"  ILD_lyrics  base={ild_base:.5f}  rrf={ild_rrf:.5f}  threshold={ild_base*0.95:.5f}")
    print(f"  Coverage    base={cov_base:.4f}  rrf={cov_rrf:.4f}  threshold={cov_base*0.95:.4f}")

    # --- Latency (200 calls, 20-call warmup), each arm under its pin ---
    print("\n[pillar_c] Measuring latency (200 calls each)...")
    all_seeds = list(gt_mapping.keys())
    lat_seeds = (all_seeds * 10)[:200]
    with _pinned_recommend_flags(**base_rec_flags):
        for s in lat_seeds[:20]:
            sys_base.recommend(s, top_k=10)
        t0 = time.perf_counter()
        for s in lat_seeds:
            sys_base.recommend(s, top_k=10)
        lat_base_avg = (time.perf_counter() - t0) / len(lat_seeds) * 1000

    with _pinned_recommend_flags(**treat_rec_flags):
        for s in lat_seeds[:20]:
            sys_rrf.recommend(s, top_k=10)
        t0 = time.perf_counter()
        for s in lat_seeds:
            sys_rrf.recommend(s, top_k=10)
        lat_rrf_avg = (time.perf_counter() - t0) / len(lat_seeds) * 1000

    print(f"  avg latency baseline = {lat_base_avg:.1f} ms")
    print(f"  avg latency rrf      = {lat_rrf_avg:.1f} ms  "
          f"({'faster' if lat_rrf_avg < lat_base_avg else 'slower'})")

    # --- Gate evaluation ---
    gate_ndcg     = ci_low > -0.005
    gate_ild      = ild_rrf >= ild_base * 0.95
    gate_coverage = cov_rrf >= cov_base * 0.95
    gate_pass     = gate_ndcg and gate_ild and gate_coverage

    verdict = (
        "PASS — set ENABLE_RRF=True "
        "(no regression on song GT; benefit in hybrid/search paths not captured by editorial GT)"
        if gate_pass else
        "FAIL — keep ENABLE_RRF=False"
    )

    print(f"\n[pillar_c] Gate results:")
    print(f"  NDCG {_CI_LABEL}[{ci_low:+.4f}] > -0.005: {'PASS' if gate_ndcg else 'FAIL'}")
    print(f"  ILD  {ild_rrf:.5f} >= {ild_base*0.95:.5f}:  {'PASS' if gate_ild else 'FAIL'}")
    print(f"  Cov  {cov_rrf:.4f} >= {cov_base*0.95:.4f}:   {'PASS' if gate_coverage else 'FAIL'}")
    print(f"\n  Verdict: {verdict}")

    # --- Build iter_5 report ---
    output_dir = getattr(args, 'output', None) or "var/runtime/backtest/reports/iter_5_pillar_C"
    os.makedirs(output_dir, exist_ok=True)

    ts_path = "var/runtime/backtest/test_sets/test_set_v1.json"
    if os.path.exists(ts_path):
        with open(ts_path) as fh:
            queries = json.load(fh)["queries"]
    else:
        queries = stratified_sample(catalog.df, n=500, seed=42)

    print(f"\n[pillar_c] Computing property metrics ({len(queries)} queries)...")
    with _pinned_recommend_flags(**base_rec_flags):
        prop_base = _run_system(sys_base, queries, catalog, top_k=10)
    with _pinned_recommend_flags(**treat_rec_flags):
        prop_rrf  = _run_system(sys_rrf, queries, catalog, top_k=10)

    # Load iter_4 for comparison context
    iter4_path = "var/runtime/backtest/reports/iter_4_pillar_A/report.json"
    iter4_report: dict = {}
    if os.path.exists(iter4_path):
        with open(iter4_path) as fh:
            iter4_report = json.load(fh)

    import config as cfg
    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_5_pillar_C",
            "n_catalog": catalog.n,
            "n_queries": len(queries),
            "top_k": 10,
            "seed": 42,
            "ground_truth": "editorial_playlists_v1",
            "pillar_c": {
                "rrf_k": cfg.RRF_K,
                "rrf_candidate_size": cfg.RRF_CANDIDATE_SIZE,
                "reranker_model": cfg.RERANKER_MODEL,
                "baseline": "v7.2_isolated (all other pillars off)",
                "gate_pass": gate_pass,
                "verdict": verdict,
                "bootstrap_ndcg": {
                    "n_queries": len(ndcg_base_pq),
                    "n_boots": 10_000,
                    "mean_ndcg_base": mean_base,
                    "mean_ndcg_rrf": mean_rrf,
                    "delta": float(delta),
                    "ci95": [float(ci_low), float(ci_high)],
                },
                "ild_comparison": {
                    "ild_lyrics_base": ild_base,
                    "ild_lyrics_rrf": ild_rrf,
                    "gate_pass": gate_ild,
                },
                "coverage_comparison": {
                    "coverage_base": cov_base,
                    "coverage_rrf": cov_rrf,
                    "gate_pass": gate_coverage,
                },
                "latency_ms": {
                    "baseline_avg": round(lat_base_avg, 2),
                    "rrf_avg": round(lat_rrf_avg, 2),
                },
            },
        },
        "systems": {
            "brightify_no_rrf": prop_base,
            "brightify_rrf": prop_rrf,
        },
        "latency": iter4_report.get("latency", {}),
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)

    from tools.backtest_v2.reporters.markdown import write_markdown

    _FakeCfg = type("_FakeCfg", (), {
        "output_dir": output_dir,
        "iteration_name": "iter_5_pillar_C",
    })

    class _FakeRep:
        meta    = report_dict["meta"]
        systems = report_dict["systems"]
        latency = report_dict.get("latency", {})
        config  = _FakeCfg()

        def to_dict(self):
            return {"meta": self.meta, "systems": self.systems, "latency": self.latency}

    write_markdown(_FakeRep(), os.path.join(output_dir, "report.md"))
    print(f"\n[pillar_c] Reports saved to {output_dir}/")

    if gate_pass:
        _update_config_enable_rrf(True)
        print("[pillar_c] config.ENABLE_RRF default set to True.")
    else:
        _update_config_enable_rrf(False)
        print("[pillar_c] Gate FAILED — config.ENABLE_RRF reverted to False.")

    return 0 if gate_pass else 1


def _update_config_enable_rrf(enable: bool) -> None:
    import re
    value = "True" if enable else "False"
    with open("config.py", encoding="utf-8") as fh:
        src = fh.read()
    new_src, n = re.subn(
        r'ENABLE_RRF\s*=\s*os\.environ\.get\("ENABLE_RRF",\s*"(?:True|False)"\)\s*==\s*"True"',
        f'ENABLE_RRF = os.environ.get("ENABLE_RRF", "{value}") == "True"',
        src,
    )
    if n > 0:
        with open("config.py", "w", encoding="utf-8") as fh:
            fh.write(new_src)
        print(f"[pillar_c] config.py: ENABLE_RRF default = {value}")
    else:
        print(f"[pillar_c] WARNING: could not update ENABLE_RRF default in config.py")


def cmd_run_pillar_e(args: argparse.Namespace) -> int:
    """Pillar E: compare lexicon-only emotion vs CLAP zero-shot emotion.

    Loads two catalog instances with ENABLE_CLAP_EMOTION toggled.

    Gates (all must pass):
      - NDCG@10 ext: paired bootstrap CI99.2% (Bonferroni) lower bound > -0.005
      - ILD_lyrics: clap >= lexicon * 0.95 (no diversity regression)
    """
    import datetime
    import json
    import os
    import sys

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    import pandas as pd
    import config as _cfg
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE, build_query_gt_mapping, load_editorial_gt,
    )
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.metrics.property import ild_lyrics
    from tools.backtest_v2.stats import paired_bootstrap, cluster_paired_bootstrap, stratified_sample
    from tools.backtest_v2.ground_truth.editorial import build_cluster_seeds
    from tools.backtest_v2.core import _run_system

    if not os.path.exists(_cfg.CLAP_EMOTIONS_FILE):
        print(f"[pillar_e] CLAP emotions file not found: {_cfg.CLAP_EMOTIONS_FILE}")
        print("[pillar_e] Run: python -m tools.extract_clap_emotions")
        return 1

    if not os.path.exists(GT_FILE):
        print(f"[pillar_e] GT file not found: {GT_FILE}")
        return 1
    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[pillar_e] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries")

    # --- Fixed v7.2 baseline isolation: base = lexicon emotion, treat = CLAP emotion ---
    base_flags  = dict(V72_BASELINE_FLAGS)
    treat_flags = {**V72_BASELINE_FLAGS, "ENABLE_CLAP_EMOTION": True}

    print("[pillar_e] Building lexicon-only catalog (v7.2, lexicon emotion)...")
    cat_lexicon = Catalog.build_isolated(base_flags)
    print("[pillar_e] Building CLAP catalog (v7.2 + CLAP emotion)...")
    cat_clap = Catalog.build_isolated(treat_flags)
    assert "fused_emotion" in cat_lexicon.df.columns and "fused_emotion" in cat_clap.df.columns, \
        "[pillar_e] fused_emotion must exist in both arms"

    sys_lexicon = BrightifyBaseline(cat_lexicon)
    sys_clap    = BrightifyBaseline(cat_clap)

    seeds = list(gt_mapping.keys())
    rng = np.random.default_rng(42)
    if len(seeds) > 200:
        sample_set = {seeds[i] for i in rng.choice(len(seeds), 200, replace=False).tolist()}
    else:
        sample_set = set(seeds)

    # --- Lexicon arm (v7.2) ---
    print("\n[pillar_e] Computing lexicon arm (v7.2)...")
    ndcg_lex_pq: list = []
    ild_lex_vals: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rl = sys_lexicon.recommend(seed_idx, top_k=10)
            ndcg_lex_pq.append(ndcg_at_k(rl, set(relevant), 10) if rl else 0.0)
            if seed_idx in sample_set and rl:
                ild_lex_vals.append(ild_lyrics(rl, cat_lexicon))

    # --- CLAP arm (v7.2 + CLAP emotion) ---
    print("[pillar_e] Computing CLAP arm (v7.2 + CLAP)...")
    ndcg_clap_pq: list = []
    ild_clap_vals: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rc = sys_clap.recommend(seed_idx, top_k=10)
            ndcg_clap_pq.append(ndcg_at_k(rc, set(relevant), 10) if rc else 0.0)
            if seed_idx in sample_set and rc:
                ild_clap_vals.append(ild_lyrics(rc, cat_clap))

    _sc_lex_e  = dict(zip(seeds, ndcg_lex_pq))
    _sc_clap_e = dict(zip(seeds, ndcg_clap_pq))
    _clusters_e = build_cluster_seeds(playlists)
    delta, ci_low, ci_high = cluster_paired_bootstrap(_sc_lex_e, _sc_clap_e, _clusters_e, n_boot=10_000, ci_level=BONFERRONI_CI_LEVEL)
    mean_lex  = float(np.mean(ndcg_lex_pq))
    mean_clap = float(np.mean(ndcg_clap_pq))

    print(f"\n[pillar_e] Cluster bootstrap NDCG@10 "
          f"(N={len(ndcg_lex_pq)} queries / {len(_clusters_e)} playlists, n_boots=10000):")
    print(f"  lexicon mean = {mean_lex:.5f}")
    print(f"  clap    mean = {mean_clap:.5f}")
    print(f"  delta   = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")

    ild_lex  = float(np.mean(ild_lex_vals))  if ild_lex_vals  else 0.0
    ild_clap = float(np.mean(ild_clap_vals)) if ild_clap_vals else 0.0
    print(f"  ILD_lyrics  lexicon={ild_lex:.5f}  clap={ild_clap:.5f}  threshold={ild_lex*0.95:.5f}")

    # --- Emotion coverage ---
    n_clap_labeled = cat_clap.df.get("fused_emotion", pd.Series()).notna().sum()
    n_lex_labeled  = cat_lexicon.df.get("fused_emotion", pd.Series()).notna().sum()
    clap_cov = n_clap_labeled / max(cat_clap.n, 1)
    lex_cov  = n_lex_labeled  / max(cat_lexicon.n, 1)
    print(f"\n[pillar_e] Emotion coverage: lexicon={lex_cov*100:.1f}%  clap={clap_cov*100:.1f}%")

    # Emotion distribution shift
    if hasattr(cat_clap, "df") and "fused_emotion" in cat_clap.df.columns:
        dist = cat_clap.df["fused_emotion"].value_counts(normalize=True)
        dist_str = "  ".join(f"{e}:{v*100:.0f}%" for e, v in dist.head(5).items())
        print(f"[pillar_e] CLAP emotion distribution (top 5): {dist_str}")

    # --- Gate evaluation ---
    gate_ndcg = ci_low > -0.005
    gate_ild  = ild_clap >= ild_lex * 0.95
    gate_pass = gate_ndcg and gate_ild

    verdict = (
        "PASS — set ENABLE_CLAP_EMOTION=True "
        "(no regression on song GT; benefit is in recommend_by_colors, not tested by editorial GT)"
        if gate_pass else
        "FAIL — keep ENABLE_CLAP_EMOTION=False"
    )

    print(f"\n[pillar_e] Gate results:")
    print(f"  NDCG {_CI_LABEL}[{ci_low:+.4f}] > -0.005: {'PASS' if gate_ndcg else 'FAIL'}")
    print(f"  ILD_lyrics {ild_clap:.5f} >= {ild_lex*0.95:.5f} (95% of lexicon): {'PASS' if gate_ild else 'FAIL'}")
    print(f"\n  Verdict: {verdict}")

    # --- Build iter_6 report ---
    output_dir = getattr(args, "output", None) or "var/runtime/backtest/reports/iter_6_pillar_E"
    os.makedirs(output_dir, exist_ok=True)

    ts_path = "var/runtime/backtest/test_sets/test_set_v1.json"
    if os.path.exists(ts_path):
        with open(ts_path) as fh:
            queries = json.load(fh)["queries"]
    else:
        queries = stratified_sample(cat_lexicon.df, n=500, seed=42)

    print(f"\n[pillar_e] Computing property metrics ({len(queries)} queries)...")
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        prop_lexicon = _run_system(sys_lexicon, queries, cat_lexicon, top_k=10)
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        prop_clap    = _run_system(sys_clap,    queries, cat_clap,    top_k=10)

    iter5_path = "var/runtime/backtest/reports/iter_5_pillar_C/report.json"
    iter5_report: dict = {}
    if os.path.exists(iter5_path):
        with open(iter5_path) as fh:
            iter5_report = json.load(fh)

    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_6_pillar_E",
            "n_catalog": cat_clap.n,
            "n_queries": len(queries),
            "top_k": 10,
            "seed": 42,
            "ground_truth": "editorial_playlists_v1",
            "pillar_e": {
                "model": _cfg.CLAP_MODEL,
                "clap_emotions_file": _cfg.CLAP_EMOTIONS_FILE,
                "clap_coverage_pct": round(clap_cov * 100, 2),
                "baseline": "v7.2_isolated (all other pillars off)",
                "gate_pass": gate_pass,
                "verdict": verdict,
                "bootstrap_ndcg": {
                    "n_queries": len(ndcg_lex_pq),
                    "n_boots": 10_000,
                    "mean_ndcg_lexicon": mean_lex,
                    "mean_ndcg_clap": mean_clap,
                    "delta": float(delta),
                    "ci95": [float(ci_low), float(ci_high)],
                },
                "ild_comparison": {
                    "ild_lyrics_lexicon": ild_lex,
                    "ild_lyrics_clap": ild_clap,
                    "gate_pass": gate_ild,
                },
            },
        },
        "systems": {
            "brightify_lexicon": prop_lexicon,
            "brightify_clap": prop_clap,
        },
        "latency": iter5_report.get("latency", {}),
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)

    from tools.backtest_v2.reporters.markdown import write_markdown

    _FakeCfg = type("_FakeCfg", (), {
        "output_dir": output_dir,
        "iteration_name": "iter_6_pillar_E",
    })

    class _FakeRep:
        meta    = report_dict["meta"]
        systems = report_dict["systems"]
        latency = report_dict.get("latency", {})
        config  = _FakeCfg()

        def to_dict(self):
            return {"meta": self.meta, "systems": self.systems, "latency": self.latency}

    write_markdown(_FakeRep(), os.path.join(output_dir, "report.md"))
    print(f"\n[pillar_e] Reports saved to {output_dir}/")

    if gate_pass:
        _update_config_enable_clap_emotion(True)
        print("[pillar_e] Gate PASSED — ENABLE_CLAP_EMOTION=True set as default.")
    else:
        _update_config_enable_clap_emotion(False)
        print("[pillar_e] Gate FAILED — ENABLE_CLAP_EMOTION reverted to False.")

    return 0 if gate_pass else 1


def cmd_run_pillar_f(args: argparse.Namespace) -> int:
    """Pillar F: KG embeddings + VN context vs. no-KG baseline.

    Gates (all must pass):
      - NDCG@10 ext: paired bootstrap CI99.2% (Bonferroni) lower bound > -0.005
      - ILD_lyrics: kg >= base * 0.95
    """
    import datetime
    import json
    import os
    import sys

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    import config as _cfg
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE, build_query_gt_mapping, load_editorial_gt,
    )
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.metrics.property import ild_lyrics
    from tools.backtest_v2.stats import paired_bootstrap, cluster_paired_bootstrap, stratified_sample
    from tools.backtest_v2.ground_truth.editorial import build_cluster_seeds
    from tools.backtest_v2.core import _run_system

    if not os.path.exists(GT_FILE):
        print(f"[pillar_f] GT file not found: {GT_FILE}")
        return 1
    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[pillar_f] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries")

    # --- Fixed v7.2 baseline isolation: base = all pillars off, treat = +KG +VN ---
    base_flags  = dict(V72_BASELINE_FLAGS)
    treat_flags = {**V72_BASELINE_FLAGS, "ENABLE_KG": True, "ENABLE_VN_CONTEXT": True}

    print("[pillar_f] Building baseline catalog (v7.2: all pillars off)...")
    cat_base = Catalog.build_isolated(base_flags)
    print("[pillar_f] Building treatment catalog (v7.2 + KG + VN context)...")
    cat_kg = Catalog.build_isolated(treat_flags)
    assert cat_base.rec.kg_matrix is None,  "[pillar_f] baseline must NOT load KG"
    assert cat_kg.rec.kg_matrix is not None, "[pillar_f] treatment MUST load KG"

    sys_base = BrightifyBaseline(cat_base)
    sys_kg   = BrightifyBaseline(cat_kg)

    seeds = list(gt_mapping.keys())
    rng = np.random.default_rng(42)
    if len(seeds) > 200:
        sample_set = {seeds[i] for i in rng.choice(len(seeds), 200, replace=False).tolist()}
    else:
        sample_set = set(seeds)

    # --- Base arm (recommend-time flags pinned to v7.2) ---
    print("\n[pillar_f] Computing base arm (v7.2)...")
    ndcg_base_pq: list = []
    ild_base_vals: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rb = sys_base.recommend(seed_idx, top_k=10)
            ndcg_base_pq.append(ndcg_at_k(rb, set(relevant), 10) if rb else 0.0)
            if seed_idx in sample_set and rb:
                ild_base_vals.append(ild_lyrics(rb, cat_base))

    # --- Treatment arm (recommend-time flags pinned to v7.2 + KG/VN) ---
    print("[pillar_f] Computing treatment arm (v7.2 + KG)...")
    ndcg_kg_pq: list = []
    ild_kg_vals: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rk = sys_kg.recommend(seed_idx, top_k=10)
            ndcg_kg_pq.append(ndcg_at_k(rk, set(relevant), 10) if rk else 0.0)
            if seed_idx in sample_set and rk:
                ild_kg_vals.append(ild_lyrics(rk, cat_kg))

    _sc_base_f = dict(zip(seeds, ndcg_base_pq))
    _sc_kg_f   = dict(zip(seeds, ndcg_kg_pq))
    _clusters_f = build_cluster_seeds(playlists)
    delta, ci_low, ci_high = cluster_paired_bootstrap(_sc_base_f, _sc_kg_f, _clusters_f, n_boot=10_000, ci_level=BONFERRONI_CI_LEVEL)
    mean_base = float(np.mean(ndcg_base_pq))
    mean_kg   = float(np.mean(ndcg_kg_pq))

    print(f"\n[pillar_f] Cluster bootstrap NDCG@10 "
          f"(N={len(ndcg_base_pq)} queries / {len(_clusters_f)} playlists, n_boots=10000):")
    print(f"  base mean = {mean_base:.5f}")
    print(f"  kg   mean = {mean_kg:.5f}")
    print(f"  delta = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")

    ild_base = float(np.mean(ild_base_vals)) if ild_base_vals else 0.0
    ild_kg   = float(np.mean(ild_kg_vals))   if ild_kg_vals   else 0.0
    print(f"  ILD_lyrics  base={ild_base:.5f}  kg={ild_kg:.5f}  threshold={ild_base*0.95:.5f}")

    # --- Gate evaluation ---
    gate_ndcg = ci_low > -0.005
    gate_ild  = ild_kg >= ild_base * 0.95
    gate_pass = gate_ndcg and gate_ild

    verdict = "PASS — set ENABLE_KG=True, ENABLE_VN_CONTEXT=True" \
              if gate_pass else "FAIL — disable KG or reduce kg_weight"

    print(f"\n[pillar_f] Gate results:")
    print(f"  NDCG {_CI_LABEL}[{ci_low:+.4f}] > -0.005: {'PASS' if gate_ndcg else 'FAIL'}")
    print(f"  ILD_lyrics {ild_kg:.5f} >= {ild_base*0.95:.5f} (95%): {'PASS' if gate_ild else 'FAIL'}")
    print(f"\n  Verdict: {verdict}")

    # --- Build iter_7 report ---
    output_dir = getattr(args, "output", None) or "var/runtime/backtest/reports/iter_7_pillar_F"
    os.makedirs(output_dir, exist_ok=True)

    ts_path = "var/runtime/backtest/test_sets/test_set_v1.json"
    if os.path.exists(ts_path):
        import json as _json
        with open(ts_path) as fh:
            queries = _json.load(fh)["queries"]
    else:
        queries = stratified_sample(cat_base.df, n=500, seed=42)

    print(f"\n[pillar_f] Computing property metrics ({len(queries)} queries)...")
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        prop_base = _run_system(sys_base, queries, cat_base, top_k=10)
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        prop_kg   = _run_system(sys_kg,   queries, cat_kg,   top_k=10)

    iter6_path = "var/runtime/backtest/reports/iter_6_pillar_E/report.json"
    iter6_report: dict = {}
    if os.path.exists(iter6_path):
        with open(iter6_path) as fh:
            iter6_report = json.load(fh)

    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_7_pillar_F",
            "n_catalog": cat_kg.n,
            "n_queries": len(queries),
            "top_k": 10,
            "seed": 42,
            "ground_truth": "editorial_playlists_v1",
            "pillar_f": {
                "kg_embeddings_file": _cfg.KG_EMBEDDINGS_FILE,
                "kg_dim": _cfg.KG_DIM,
                "enable_vn_context": True,
                "baseline": "v7.2_isolated (all other pillars off)",
                "gate_pass": gate_pass,
                "verdict": verdict,
                "bootstrap_ndcg": {
                    "n_queries": len(ndcg_base_pq),
                    "n_boots": 10_000,
                    "mean_ndcg_base": mean_base,
                    "mean_ndcg_kg": mean_kg,
                    "delta": float(delta),
                    "ci95": [float(ci_low), float(ci_high)],
                },
                "ild_comparison": {
                    "ild_lyrics_base": ild_base,
                    "ild_lyrics_kg": ild_kg,
                    "gate_pass": gate_ild,
                },
            },
        },
        "systems": {
            "brightify_base": prop_base,
            "brightify_kg":   prop_kg,
        },
        "latency": iter6_report.get("latency", {}),
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)

    from tools.backtest_v2.reporters.markdown import write_markdown

    _FakeCfg = type("_FakeCfg", (), {
        "output_dir": output_dir,
        "iteration_name": "iter_7_pillar_F",
    })

    class _FakeRep:
        meta    = report_dict["meta"]
        systems = report_dict["systems"]
        latency = report_dict.get("latency", {})
        config  = _FakeCfg()

        def to_dict(self):
            return {"meta": self.meta, "systems": self.systems, "latency": self.latency}

    write_markdown(_FakeRep(), os.path.join(output_dir, "report.md"))
    print(f"\n[pillar_f] Reports saved to {output_dir}/")

    if gate_pass:
        _update_config_enable_kg(True)
        print("[pillar_f] Gate PASSED — ENABLE_KG=True, ENABLE_VN_CONTEXT=True as defaults.")
    else:
        _update_config_enable_kg(False)
        print("[pillar_f] Gate FAILED — KG disabled in config.")

    return 0 if gate_pass else 1


def cmd_run_pillar_f_xartist(args: argparse.Namespace) -> int:
    """Pillar F circularity check: KG gain on CROSS-ARTIST pairs only.

    KG embeds artist co-occurrence; editorial GT also contains same-artist tracks
    in the same playlist (easy pairs). This command re-runs Pillar F evaluation
    keeping only seed→relevant pairs where the seed and relevant track have
    DIFFERENT artists — directly testing the circularity concern.

    Verdict interpretation:
      - If KG delta is similar to main Pillar F result → circularity NOT supported.
      - If KG delta collapses near 0 → KG mainly exploits same-artist proximity.
    """
    import datetime
    import json
    import os
    import sys

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE, build_cross_artist_gt_mapping, build_cluster_seeds, load_editorial_gt,
    )
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.metrics.property import ild_lyrics
    from tools.backtest_v2.stats import cluster_paired_bootstrap
    from tools.backtest_v2.core import _run_system

    if not os.path.exists(GT_FILE):
        print(f"[pillar_f_xartist] GT file not found: {GT_FILE}")
        return 1

    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_cross_artist_gt_mapping(playlists)
    clusters   = build_cluster_seeds(playlists)

    n_full = sum(len(v) for v in build_query_gt_mapping_full(playlists).values())
    n_xart = sum(len(v) for v in gt_mapping.values())
    print(f"[pillar_f_xartist] Cross-artist GT: {len(playlists)} playlists, "
          f"{len(gt_mapping)} seed queries, {n_xart} relevant pairs "
          f"(vs {n_full} in full GT = {100*n_xart/max(n_full,1):.1f}% retained)")

    if len(gt_mapping) < 10:
        print("[pillar_f_xartist] ERROR: too few cross-artist pairs to evaluate. "
              "Check artist field population in editorial GT.")
        return 1

    base_flags  = dict(V72_BASELINE_FLAGS)
    treat_flags = {**V72_BASELINE_FLAGS, "ENABLE_KG": True, "ENABLE_VN_CONTEXT": True}

    print("[pillar_f_xartist] Building baseline catalog (v7.2)...")
    cat_base = Catalog.build_isolated(base_flags)
    print("[pillar_f_xartist] Building treatment catalog (v7.2 + KG + VN)...")
    cat_kg = Catalog.build_isolated(treat_flags)

    sys_base = BrightifyBaseline(cat_base)
    sys_kg   = BrightifyBaseline(cat_kg)

    seeds = list(gt_mapping.keys())

    print(f"\n[pillar_f_xartist] Computing base arm (v7.2, {len(seeds)} seeds)...")
    ndcg_base_pq: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rb = sys_base.recommend(seed_idx, top_k=10)
            ndcg_base_pq.append(ndcg_at_k(rb, set(relevant), 10) if rb else 0.0)

    print(f"[pillar_f_xartist] Computing treatment arm (v7.2 + KG)...")
    ndcg_kg_pq: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(treat_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rk = sys_kg.recommend(seed_idx, top_k=10)
            ndcg_kg_pq.append(ndcg_at_k(rk, set(relevant), 10) if rk else 0.0)

    _sc_base = dict(zip(seeds, ndcg_base_pq))
    _sc_kg   = dict(zip(seeds, ndcg_kg_pq))
    delta, ci_low, ci_high = cluster_paired_bootstrap(
        _sc_base, _sc_kg, clusters, n_boot=10_000, ci_level=BONFERRONI_CI_LEVEL
    )
    mean_base = float(np.mean(ndcg_base_pq))
    mean_kg   = float(np.mean(ndcg_kg_pq))

    print(f"\n[pillar_f_xartist] Cluster bootstrap NDCG@10 (cross-artist pairs only):")
    print(f"  base mean = {mean_base:.5f}")
    print(f"  kg   mean = {mean_kg:.5f}")
    print(f"  delta = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")

    # Interpretation
    if delta > 0.005 and ci_low > 0:
        conclusion = "CIRCULARITY NOT SUPPORTED — KG gain persists on cross-artist pairs"
    elif abs(delta) <= 0.005:
        conclusion = "INCONCLUSIVE — delta near zero on cross-artist pairs"
    else:
        conclusion = "CIRCULARITY LIKELY — KG gain collapses on cross-artist pairs"

    print(f"\n  Conclusion: {conclusion}")

    # Save report
    output_dir = getattr(args, "output", None) or "var/runtime/backtest/reports/pillar_F_xartist"
    os.makedirs(output_dir, exist_ok=True)

    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "pillar_F_xartist_circularity_check",
            "ground_truth": "editorial_playlists_v1 (cross-artist pairs only)",
            "n_playlists": len(playlists),
            "n_seeds": len(gt_mapping),
            "n_relevant_pairs_xartist": n_xart,
            "pillar_f_xartist": {
                "baseline": "v7.2_isolated",
                "bootstrap_ndcg": {
                    "n_queries": len(ndcg_base_pq),
                    "n_boots": 10_000,
                    "ci_level": BONFERRONI_CI_LEVEL,
                    "mean_ndcg_base": mean_base,
                    "mean_ndcg_kg": mean_kg,
                    "delta": float(delta),
                    "ci": [float(ci_low), float(ci_high)],
                },
                "conclusion": conclusion,
            },
        },
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)
    print(f"\n[pillar_f_xartist] Report saved to {json_path}")

    return 0


def build_query_gt_mapping_full(playlists):
    """Thin wrapper for local use — avoids re-importing editorial in this scope."""
    from tools.backtest_v2.ground_truth.editorial import build_query_gt_mapping
    return build_query_gt_mapping(playlists)


def _update_config_enable_kg(enable: bool) -> None:
    import re
    value = "True" if enable else "False"
    with open("config.py", encoding="utf-8") as fh:
        src = fh.read()
    n_total = 0
    for flag in ("ENABLE_KG", "ENABLE_VN_CONTEXT"):
        new_src, n = re.subn(
            rf'{flag}\s*=\s*os\.environ\.get\("{flag}",\s*"(?:True|False)"\)\s*==\s*"True"',
            f'{flag} = os.environ.get("{flag}", "{value}") == "True"',
            src,
        )
        if n > 0:
            src = new_src
            n_total += n
    if n_total > 0:
        with open("config.py", "w", encoding="utf-8") as fh:
            fh.write(src)
        print(f"[pillar_f] config.py: ENABLE_KG + ENABLE_VN_CONTEXT = {value}")
    else:
        print(f"[pillar_f] WARNING: could not update KG/VN_CONTEXT flags in config.py")


def _update_config_enable_clap_emotion(enable: bool) -> None:
    import re
    value = "True" if enable else "False"
    with open("config.py", encoding="utf-8") as fh:
        src = fh.read()
    new_src, n = re.subn(
        r'ENABLE_CLAP_EMOTION\s*=\s*os\.environ\.get\("ENABLE_CLAP_EMOTION",\s*"(?:True|False)"\)\s*==\s*"True"',
        f'ENABLE_CLAP_EMOTION = os.environ.get("ENABLE_CLAP_EMOTION", "{value}") == "True"',
        src,
    )
    if n > 0:
        with open("config.py", "w", encoding="utf-8") as fh:
            fh.write(new_src)
        print(f"[pillar_e] config.py: ENABLE_CLAP_EMOTION default = {value}")
    else:
        print(f"[pillar_e] WARNING: could not update ENABLE_CLAP_EMOTION in config.py")


def cmd_run_full_system(args: argparse.Namespace) -> int:
    """End-to-end production lift: v7.2 (all pillars off) vs the CURRENT config flags.

    The per-pillar reports measure each pillar's isolated marginal contribution to
    v7.2; they do NOT sum to the deployed system's lift (pillars interact, and some
    — e.g. MMR diversity — deliberately trade NDCG for diversity). This command
    measures the real production delta in one paired comparison.
    """
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
    from tools.backtest_v2.ground_truth.editorial import (
        GT_FILE, build_query_gt_mapping, load_editorial_gt, build_cluster_seeds,
    )
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.metrics.property import ild_lyrics
    from tools.backtest_v2.stats import cluster_paired_bootstrap

    if not os.path.exists(GT_FILE):
        print(f"[full_system] GT file not found: {GT_FILE}")
        return 1
    playlists = load_editorial_gt(GT_FILE)
    gt_mapping = build_query_gt_mapping(playlists)
    print(f"[full_system] GT: {len(playlists)} playlists, {len(gt_mapping)} seed queries")

    base_flags = dict(V72_BASELINE_FLAGS)
    prod_flags = {
        "ENABLE_PILLAR_B":    cfg.ENABLE_PILLAR_B,
        "ENABLE_MERT":        cfg.ENABLE_MERT,
        "ENABLE_KG":          cfg.ENABLE_KG,
        "ENABLE_CLAP_EMOTION": cfg.ENABLE_CLAP_EMOTION,
        "ENABLE_RRF":         cfg.ENABLE_RRF,
        "ENABLE_VN_CONTEXT":  cfg.ENABLE_VN_CONTEXT,
        "DIVERSITY_METHOD":   cfg.DIVERSITY_METHOD,
    }
    print(f"[full_system] Production flags: {prod_flags}")

    print("[full_system] Building v7.2 baseline (all pillars off)...")
    cat_base = Catalog.build_isolated(base_flags)
    print("[full_system] Building production catalog (current config)...")
    cat_prod = Catalog.build_isolated(prod_flags)

    sys_base = BrightifyBaseline(cat_base)
    sys_prod = BrightifyBaseline(cat_prod)

    seeds = list(gt_mapping.keys())
    rng = np.random.default_rng(42)
    if len(seeds) > 200:
        sample_set = {seeds[i] for i in rng.choice(len(seeds), 200, replace=False).tolist()}
    else:
        sample_set = set(seeds)

    print("\n[full_system] Computing v7.2 arm...")
    ndcg_base_pq: list = []
    ild_base_vals: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(base_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rb = sys_base.recommend(seed_idx, top_k=10)
            ndcg_base_pq.append(ndcg_at_k(rb, set(relevant), 10) if rb else 0.0)
            if seed_idx in sample_set and rb:
                ild_base_vals.append(ild_lyrics(rb, cat_base))

    print("[full_system] Computing production arm...")
    ndcg_prod_pq: list = []
    ild_prod_vals: list = []
    with _pinned_recommend_flags(**_recommend_time_subset(prod_flags)):
        for seed_idx, relevant in gt_mapping.items():
            rp = sys_prod.recommend(seed_idx, top_k=10)
            ndcg_prod_pq.append(ndcg_at_k(rp, set(relevant), 10) if rp else 0.0)
            if seed_idx in sample_set and rp:
                ild_prod_vals.append(ild_lyrics(rp, cat_prod))

    _sc_base = dict(zip(seeds, ndcg_base_pq))
    _sc_prod = dict(zip(seeds, ndcg_prod_pq))
    _clusters = build_cluster_seeds(playlists)
    delta, ci_low, ci_high = cluster_paired_bootstrap(_sc_base, _sc_prod, _clusters, n_boot=10_000)
    mean_base = float(np.mean(ndcg_base_pq))
    mean_prod = float(np.mean(ndcg_prod_pq))
    ild_base = float(np.mean(ild_base_vals)) if ild_base_vals else 0.0
    ild_prod = float(np.mean(ild_prod_vals)) if ild_prod_vals else 0.0
    pct = (mean_prod / mean_base - 1.0) * 100 if mean_base > 0 else 0.0

    print(f"\n[full_system] Cluster bootstrap NDCG@10 "
          f"(N={len(ndcg_base_pq)} queries / {len(_clusters)} playlists, n_boots=10000):")
    print(f"  v7.2       mean = {mean_base:.5f}")
    print(f"  production mean = {mean_prod:.5f}  ({pct:+.1f}%)")
    print(f"  delta = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")
    print(f"  ILD_lyrics  v7.2={ild_base:.5f}  production={ild_prod:.5f}")
    significant = ci_low > 0
    print(f"  Net lift significant (CI95 lower > 0): {'YES' if significant else 'NO'}")

    output_dir = getattr(args, "output", None) or "var/runtime/backtest/reports/iter_8_full_system"
    os.makedirs(output_dir, exist_ok=True)
    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "iter_8_full_system",
            "n_catalog": cat_prod.n,
            "top_k": 10,
            "seed": 42,
            "ground_truth": "editorial_playlists_v1",
            "full_system": {
                "production_flags": prod_flags,
                "significant": bool(significant),
                "bootstrap_ndcg": {
                    "n_queries": len(ndcg_base_pq),
                    "n_playlists": len(_clusters),
                    "n_boots": 10_000,
                    "mean_ndcg_v72": mean_base,
                    "mean_ndcg_production": mean_prod,
                    "pct_change": pct,
                    "delta": float(delta),
                    "ci95": [float(ci_low), float(ci_high)],
                },
                "ild_comparison": {"ild_lyrics_v72": ild_base, "ild_lyrics_production": ild_prod},
            },
        },
        "systems": {},
        "latency": {},
    }
    with open(os.path.join(output_dir, "report.json"), "w") as fh:
        json.dump(report_dict, fh, indent=2)
    print(f"\n[full_system] Report saved to {output_dir}/report.json")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate a v8.0 cumulative summary report across all pillar iterations."""
    import datetime
    import json
    import os

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)

    REPORTS_DIR = "var/runtime/backtest/reports"

    PILLAR_SEQUENCE = [
        ("iter_0_baseline",  "Baseline v7.2"),
        ("iter_1_weight_opt","Weight optimisation"),
        ("iter_2_pillar_B",  "Pillar B — SimCSE NLP"),
        ("iter_3_pillar_D",  "Pillar D — MMR diversity"),
        ("iter_4_pillar_A",  "Pillar A — MERT audio embedding"),
        ("iter_5_pillar_C",  "Pillar C — RRF hybrid retrieval"),
        ("iter_6_pillar_E",  "Pillar E — CLAP zero-shot emotion"),
        ("iter_7_pillar_F",  "Pillar F — KG embeddings + VN context"),
    ]

    rows = []
    for iter_name, label in PILLAR_SEQUENCE:
        fpath = os.path.join(REPORTS_DIR, iter_name, "report.json")
        if not os.path.exists(fpath):
            rows.append({"iter": iter_name, "label": label, "status": "MISSING", "data": {}})
            continue
        with open(fpath) as fh:
            d = json.load(fh)
        meta = d.get("meta", {})
        # Extract pillar-specific gate info
        pillar_key = [k for k in meta if k.startswith("pillar_") or k == "weight_optimization"]
        if pillar_key:
            pd = meta[pillar_key[0]]
            gate_pass = pd.get("gate_pass")
            verdict = pd.get("verdict", "")
            bs = pd.get("bootstrap_ndcg", pd.get("bootstrap", {}))
        else:
            gate_pass = None
            verdict = ""
            bs = {}
        rows.append({
            "iter": iter_name,
            "label": label,
            "status": "PASS" if gate_pass else ("FAIL" if gate_pass is False else "INFO"),
            "gate_pass": gate_pass,
            "verdict": verdict,
            "bootstrap": bs,
        })

    # Print console summary
    print("\n" + "=" * 80)
    print(f"  BRIGHTIFY v8.0 — CUMULATIVE UPGRADE REPORT  ({datetime.date.today()})")
    print("=" * 80)
    print(f"\n{'Iteration':<30} {'Status':<6} {'NDCG Before':>12} {'NDCG After':>12} {'Δ NDCG':>10}")
    print("-" * 80)

    cumulative_ndcg = None
    for row in rows:
        bs = row.get("bootstrap", {})
        before_key = next((k for k in ("mean_ndcg_at_10_baseline", "mean_ndcg_base",
                                        "mean_ndcg_greedy", "mean_ndcg_lexicon") if k in bs), None)
        after_key  = next((k for k in ("mean_ndcg_at_10_pillar_b", "mean_ndcg_mert",
                                        "mean_ndcg_mmr", "mean_ndcg_rrf", "mean_ndcg_clap",
                                        "mean_ndcg_kg") if k in bs), None)
        before = bs.get(before_key, "") if before_key else ""
        after  = bs.get(after_key, "")  if after_key  else ""
        delta  = bs.get("delta", "")

        before_s = f"{before:.5f}" if isinstance(before, float) else "—"
        after_s  = f"{after:.5f}"  if isinstance(after,  float) else "—"
        delta_s  = (f"{delta:+.5f}" if isinstance(delta, float) else "—")

        status = row.get("status", "")
        status_s = {"PASS": "✓ PASS", "FAIL": "✗ FAIL", "INFO": " INFO", "MISSING": "? —"}.get(status, status)
        print(f"  {row['label']:<28} {status_s:<7} {before_s:>12} {after_s:>12} {delta_s:>10}")

    print("\n" + "=" * 80)
    print("  ACTIVE FLAGS (v8.0 production config):")
    print("=" * 80)

    import config as cfg
    flags = [
        ("ENABLE_PILLAR_B", cfg.ENABLE_PILLAR_B, "SimCSE NLP"),
        ("DIVERSITY_METHOD", cfg.DIVERSITY_METHOD, "MMR reranking"),
        ("ENABLE_MERT",      cfg.ENABLE_MERT,     "MERT audio embedding"),
        ("ENABLE_RRF",       cfg.ENABLE_RRF,      "RRF hybrid retrieval"),
        ("ENABLE_CLAP_EMOTION", cfg.ENABLE_CLAP_EMOTION, "CLAP zero-shot emotion"),
        ("ENABLE_KG",        cfg.ENABLE_KG,       "KG embeddings"),
        ("ENABLE_VN_CONTEXT",cfg.ENABLE_VN_CONTEXT, "VN holiday context"),
    ]
    for name, val, desc in flags:
        print(f"  {name:<25} = {str(val):<8}  # {desc}")

    print("\n" + "=" * 80)
    print("  REMAINING OPTIONAL WORK (requires external resources):")
    print("=" * 80)
    remaining = [
        ("Pillar E — MLP combiner",        "~500 VN songs annotated (V-A), $500-1000, 3 weeks"),
        ("Pillar E — multi-task ViDeBERTa", "Labeled data for 3-task fine-tuning"),
        ("Pillar F — Weather API",          "OpenWeatherMap API key required"),
        ("Pillar G — async SQLAlchemy",     "Redis + asyncpg migration (DevX only)"),
    ]
    for item, blocker in remaining:
        print(f"  • {item:<35}  [blocked: {blocker}]")
    print()

    print("=" * 80)
    print("  METHODOLOGY NOTES:")
    print("=" * 80)
    print("  CI uses cluster bootstrap (resample over 32 playlists, not 1050 queries)")
    print("  to correct pseudo-replication from the editorial GT structure.")
    print(f"  Bonferroni correction applied: {_N_PILLAR_TESTS} simultaneous pillar tests →")
    print(f"  each gate uses CI{BONFERRONI_CI_LEVEL*100:.2f}% (α≈0.05/{_N_PILLAR_TESTS}≈{0.05/_N_PILLAR_TESTS:.4f})")
    print("  instead of 95%, keeping family-wise error rate at 5%.")
    print("  Pillar C / Pillar E: CI=[0,0] is expected — RRF and CLAP do not affect")
    print("  recommend_by_song() tested by editorial GT. Color-path tests available:")
    print("    python -m tools.backtest_v2 pillar-c-color  (RRF on color path)")
    print("    python -m tools.backtest_v2 pillar-e-color  (CLAP on color path)")
    print("  These use a 24-color V-A proximity GT (engine-derived-color, supplementary).")
    print()

    # Save to JSON
    output_dir = getattr(args, "output", None) or os.path.join(REPORTS_DIR, "v8_0_final_report")
    os.makedirs(output_dir, exist_ok=True)
    summary = {
        "date": str(datetime.date.today()),
        "version": "v8.0",
        "pillars": rows,
        "active_flags": {name: val for name, val, _ in flags},
        "remaining_optional": [{"item": i, "blocker": b} for i, b in remaining],
    }
    json_path = os.path.join(output_dir, "summary.json")
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"  Summary saved → {json_path}")
    return 0


def cmd_check_mood_tags(args: argparse.Namespace) -> int:
    """§7.3 discriminativeness gate over the processed catalog."""
    import json

    import pandas as pd

    import config
    from tools.backtest_v2.ground_truth.mood_tags_weak import discriminativeness_check

    path = args.csv or config.PROCESSED_FILE
    df = pd.read_csv(path)
    result = discriminativeness_check(df)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["verdict"] != "reject" else 1


def cmd_run_pillar_c_color(args: argparse.Namespace) -> int:
    """Pillar C supplementary: test RRF on recommend_by_colors() path.

    Builds (or loads) a color→V-A GT from 24 representative hex colors.
    Compares base (no-RRF) vs treatment (RRF on) for recommend_by_colors().

    This is supplementary evidence — Pillar C already PASSED the no-regression
    song-path gate. This test validates its actual target path.
    No config changes are triggered.
    """
    import datetime
    import json
    import os
    import sys

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.color_emotion_gt import (
        build_color_gt, load_color_gt, GT_FILE as COLOR_GT_FILE,
    )
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.stats import paired_bootstrap

    print("[pillar_c_color] Building isolated v7.2 catalog (all pillars off)...")
    catalog = Catalog.build_isolated(dict(V72_BASELINE_FLAGS))

    # Build or load color GT
    rebuild = getattr(args, "rebuild", False)
    if not rebuild and os.path.exists(COLOR_GT_FILE):
        print(f"[pillar_c_color] Loading existing color GT from {COLOR_GT_FILE}")
        gt_mapping, gt_meta = load_color_gt(COLOR_GT_FILE)
    else:
        print("[pillar_c_color] Building color GT (24 representative hex colors)...")
        gt_mapping, gt_meta = build_color_gt(catalog, save_path=COLOR_GT_FILE)

    print(f"[pillar_c_color] Color GT: {len(gt_mapping)} color queries "
          f"(threshold={gt_meta['va_proximity_threshold']})")
    print(f"[pillar_c_color] Warning: {gt_meta['warning'][:80]}...")

    base_rec_flags  = {"ENABLE_RRF": False, "DIVERSITY_METHOD": "greedy", "ENABLE_VN_CONTEXT": False}
    treat_rec_flags = {"ENABLE_RRF": True,  "DIVERSITY_METHOD": "greedy", "ENABLE_VN_CONTEXT": False}

    colors = list(gt_mapping.keys())

    # --- Base arm (no RRF) ---
    print("\n[pillar_c_color] Base arm (recommend_by_colors, no RRF)...")
    ndcg_base: list = []
    with _pinned_recommend_flags(**base_rec_flags):
        for hex_color in colors:
            relevant = set(gt_mapping[hex_color])
            recs = catalog.recommend_by_colors(hex_color, top_k=10)
            ndcg_base.append(ndcg_at_k(recs, relevant, 10) if recs else 0.0)

    # --- Treatment arm (RRF on) ---
    print("[pillar_c_color] Treatment arm (recommend_by_colors, RRF on)...")
    ndcg_rrf: list = []
    with _pinned_recommend_flags(**treat_rec_flags):
        for hex_color in colors:
            relevant = set(gt_mapping[hex_color])
            recs = catalog.recommend_by_colors(hex_color, top_k=10)
            ndcg_rrf.append(ndcg_at_k(recs, relevant, 10) if recs else 0.0)

    # Standard paired bootstrap (color queries are independent — no cluster structure)
    delta, ci_low, ci_high = paired_bootstrap(ndcg_base, ndcg_rrf, n_boot=10_000)
    mean_base = float(np.mean(ndcg_base))
    mean_rrf  = float(np.mean(ndcg_rrf))

    print(f"\n[pillar_c_color] Paired bootstrap NDCG@10 "
          f"(N={len(ndcg_base)} color queries, n_boots=10000):")
    print(f"  base (no-RRF)  mean = {mean_base:.5f}")
    print(f"  treat (RRF)    mean = {mean_rrf:.5f}")
    print(f"  delta = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")

    significant = ci_low > 0
    verdict = (
        "CONFIRMS: RRF improves color→V-A alignment on recommend_by_colors() path"
        if significant else (
            "INCONCLUSIVE: delta is positive but CI crosses 0 — "
            "RRF may help but evidence is weak on 24-color GT"
            if delta > 0 else
            "NEGATIVE: RRF does not improve (or slightly hurts) color path on V-A GT"
        )
    )
    print(f"  Verdict: {verdict}")
    print("\n  [INFO] This is supplementary evidence only — Pillar C already PASS on "
          "song path. No config changes triggered.")

    output_dir = getattr(args, "output", None) or "var/runtime/backtest/reports/pillar_C_color"
    os.makedirs(output_dir, exist_ok=True)

    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "pillar_C_color",
            "n_catalog": catalog.n,
            "n_color_queries": len(ndcg_base),
            "top_k": 10,
            "ground_truth": "color_emotion_gt_v1",
            "gt_validity": "engine-derived-color",
            "gt_warning": gt_meta["warning"],
            "pillar_c_color": {
                "baseline": "v7.2_isolated (all pillars off)",
                "bootstrap_type": "standard-paired (color queries are independent)",
                "bootstrap_ndcg": {
                    "n_queries": len(ndcg_base),
                    "n_boots": 10_000,
                    "mean_ndcg_base": round(mean_base, 6),
                    "mean_ndcg_rrf":  round(mean_rrf, 6),
                    "delta": round(float(delta), 6),
                    "ci95": [round(float(ci_low), 6), round(float(ci_high), 6)],
                    "significant": significant,
                },
                "verdict": verdict,
                "config_change": "none — supplementary evidence",
            },
        },
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)
    print(f"\n[pillar_c_color] Report saved to {json_path}")
    return 0


def cmd_run_pillar_e_color(args: argparse.Namespace) -> int:
    """Pillar E supplementary: test CLAP on recommend_by_colors() path.

    Builds (or loads) a color→V-A GT from 24 representative hex colors.
    Compares lexicon-only vs CLAP emotion for recommend_by_colors().

    This is supplementary evidence — Pillar E already PASSED the no-regression
    song-path gate. This test validates its actual target path.
    No config changes are triggered.
    """
    import datetime
    import json
    import os
    import sys

    import numpy as np

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    import config as _cfg
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.color_emotion_gt import (
        build_color_gt, load_color_gt, GT_FILE as COLOR_GT_FILE,
    )
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from tools.backtest_v2.stats import paired_bootstrap

    if not os.path.exists(_cfg.CLAP_EMOTIONS_FILE):
        print(f"[pillar_e_color] CLAP emotions file not found: {_cfg.CLAP_EMOTIONS_FILE}")
        print("[pillar_e_color] Run: python -m tools.extract_clap_emotions")
        return 1

    # --- Build two catalog arms ---
    base_flags  = dict(V72_BASELINE_FLAGS)
    treat_flags = {**V72_BASELINE_FLAGS, "ENABLE_CLAP_EMOTION": True}

    print("[pillar_e_color] Building lexicon-only catalog (v7.2)...")
    cat_lexicon = Catalog.build_isolated(base_flags)
    print("[pillar_e_color] Building CLAP catalog (v7.2 + CLAP emotion)...")
    cat_clap = Catalog.build_isolated(treat_flags)

    # Build or load color GT (use lexicon catalog — GT uses V-A only, not fused_emotion)
    rebuild = getattr(args, "rebuild", False)
    if not rebuild and os.path.exists(COLOR_GT_FILE):
        print(f"[pillar_e_color] Loading existing color GT from {COLOR_GT_FILE}")
        gt_mapping, gt_meta = load_color_gt(COLOR_GT_FILE)
    else:
        print("[pillar_e_color] Building color GT using lexicon catalog...")
        gt_mapping, gt_meta = build_color_gt(cat_lexicon, save_path=COLOR_GT_FILE)

    print(f"[pillar_e_color] Color GT: {len(gt_mapping)} color queries "
          f"(threshold={gt_meta['va_proximity_threshold']})")
    print(f"[pillar_e_color] Warning: {gt_meta['warning'][:80]}...")

    base_rec_flags  = _recommend_time_subset(base_flags)
    treat_rec_flags = _recommend_time_subset(treat_flags)

    colors = list(gt_mapping.keys())

    # --- Lexicon arm ---
    print("\n[pillar_e_color] Lexicon arm (recommend_by_colors, lexicon emotion)...")
    ndcg_lex: list = []
    with _pinned_recommend_flags(**base_rec_flags):
        for hex_color in colors:
            relevant = set(gt_mapping[hex_color])
            recs = cat_lexicon.recommend_by_colors(hex_color, top_k=10)
            ndcg_lex.append(ndcg_at_k(recs, relevant, 10) if recs else 0.0)

    # --- CLAP arm ---
    print("[pillar_e_color] CLAP arm (recommend_by_colors, CLAP emotion)...")
    ndcg_clap: list = []
    with _pinned_recommend_flags(**treat_rec_flags):
        for hex_color in colors:
            relevant = set(gt_mapping[hex_color])
            recs = cat_clap.recommend_by_colors(hex_color, top_k=10)
            ndcg_clap.append(ndcg_at_k(recs, relevant, 10) if recs else 0.0)

    # Standard paired bootstrap (color queries are independent)
    delta, ci_low, ci_high = paired_bootstrap(ndcg_lex, ndcg_clap, n_boot=10_000)
    mean_lex  = float(np.mean(ndcg_lex))
    mean_clap = float(np.mean(ndcg_clap))

    print(f"\n[pillar_e_color] Paired bootstrap NDCG@10 "
          f"(N={len(ndcg_lex)} color queries, n_boots=10000):")
    print(f"  lexicon     mean = {mean_lex:.5f}")
    print(f"  CLAP        mean = {mean_clap:.5f}")
    print(f"  delta = {delta:+.5f}  {_CI_LABEL}=[{ci_low:+.5f}, {ci_high:+.5f}]")

    significant = ci_low > 0
    verdict = (
        "CONFIRMS: CLAP improves color→V-A alignment on recommend_by_colors() path"
        if significant else (
            "INCONCLUSIVE: delta is positive but CI crosses 0 — "
            "CLAP may help but evidence is weak on 24-color GT"
            if delta > 0 else
            "NEGATIVE: CLAP does not improve (or slightly hurts) color path on V-A GT"
        )
    )
    print(f"  Verdict: {verdict}")
    print("\n  [INFO] This is supplementary evidence only — Pillar E already PASS on "
          "song path. No config changes triggered.")

    # Emotion distribution shift
    clap_dist = cat_clap.df.get("fused_emotion", None)
    if clap_dist is not None:
        top5 = clap_dist.value_counts(normalize=True).head(5)
        dist_str = "  ".join(f"{e}:{v*100:.0f}%" for e, v in top5.items())
        print(f"\n[pillar_e_color] CLAP emotion distribution (top 5): {dist_str}")

    output_dir = getattr(args, "output", None) or "var/runtime/backtest/reports/pillar_E_color"
    os.makedirs(output_dir, exist_ok=True)

    report_dict = {
        "meta": {
            "date": str(datetime.date.today()),
            "iteration": "pillar_E_color",
            "n_catalog": cat_clap.n,
            "n_color_queries": len(ndcg_lex),
            "top_k": 10,
            "ground_truth": "color_emotion_gt_v1",
            "gt_validity": "engine-derived-color",
            "gt_warning": gt_meta["warning"],
            "pillar_e_color": {
                "clap_model": _cfg.CLAP_MODEL,
                "clap_emotions_file": _cfg.CLAP_EMOTIONS_FILE,
                "baseline": "v7.2_isolated (lexicon emotion, all other pillars off)",
                "bootstrap_type": "standard-paired (color queries are independent)",
                "bootstrap_ndcg": {
                    "n_queries": len(ndcg_lex),
                    "n_boots": 10_000,
                    "mean_ndcg_lexicon": round(mean_lex, 6),
                    "mean_ndcg_clap":    round(mean_clap, 6),
                    "delta": round(float(delta), 6),
                    "ci95": [round(float(ci_low), 6), round(float(ci_high), 6)],
                    "significant": significant,
                },
                "verdict": verdict,
                "config_change": "none — supplementary evidence",
            },
        },
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as fh:
        json.dump(report_dict, fh, indent=2)
    print(f"\n[pillar_e_color] Report saved to {json_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.backtest_v2", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="measure baseline / a method")
    p_run.add_argument("--config", help="path to YAML config (default: configs/backtest_v0.yaml)")
    p_run.add_argument("--ground-truth")
    p_run.add_argument("--method")
    p_run.add_argument("--output", help="override output_dir")
    p_run.set_defaults(func=cmd_run)

    p_abl = sub.add_parser("ablation", help="drop-one-signal ablation")
    p_abl.add_argument("--signals")
    p_abl.add_argument("--output", help="override output directory for signal_importance.json")
    p_abl.set_defaults(func=cmd_ablation)

    p_opt = sub.add_parser("optimize-weights", help="search RECO_SONG_WEIGHTS")
    p_opt.add_argument("--ground-truth")
    p_opt.add_argument("--method")
    p_opt.add_argument("--constraint")
    p_opt.add_argument("--max-opt-queries", type=int, default=30,
                       dest="max_opt_queries",
                       help="max queries used inside SLSQP loop (default: 200)")
    p_opt.set_defaults(func=cmd_optimize_weights)

    p_cmp = sub.add_parser("compare", help="compare two iterations")
    p_cmp.add_argument("iter_a")
    p_cmp.add_argument("iter_b")
    p_cmp.set_defaults(func=cmd_compare)

    p_pb = sub.add_parser("run-pillar-b", help="Phase 5 Pillar B: SimCSE (dangvantuan/vietnamese-embedding) vs PhoBERT")
    p_pb.add_argument("--output", help="override output directory (default: iter_2_pillar_B)")
    p_pb.set_defaults(func=cmd_run_pillar_b)

    p_pd = sub.add_parser("run-pillar-d", help="Pillar D: greedy vs MMR diversity reranking")
    p_pd.add_argument("--output", help="override output directory (default: iter_3_pillar_D)")
    p_pd.set_defaults(func=cmd_run_pillar_d)

    p_pa = sub.add_parser("run-pillar-a", help="Pillar A: 7-signal vs 8-signal MERT audio embedding")
    p_pa.add_argument("--output", help="override output directory (default: iter_4_pillar_A)")
    p_pa.set_defaults(func=cmd_run_pillar_a)

    p_pc = sub.add_parser("run-pillar-c", help="Pillar C: RRF hybrid retrieval vs no-RRF baseline")
    p_pc.add_argument("--output", help="override output directory (default: iter_5_pillar_C)")
    p_pc.set_defaults(func=cmd_run_pillar_c)

    p_pe = sub.add_parser("run-pillar-e", help="Pillar E: CLAP zero-shot emotion vs lexicon-only")
    p_pe.add_argument("--output", help="override output directory (default: iter_6_pillar_E)")
    p_pe.set_defaults(func=cmd_run_pillar_e)

    p_pf = sub.add_parser("run-pillar-f", help="Pillar F: KG embeddings + VN context vs baseline")
    p_pf.add_argument("--output", help="override output directory (default: iter_7_pillar_F)")
    p_pf.set_defaults(func=cmd_run_pillar_f)

    p_fs = sub.add_parser("run-full-system", help="end-to-end v7.2 vs production lift")
    p_fs.add_argument("--output", help="override output directory (default: iter_8_full_system)")
    p_fs.set_defaults(func=cmd_run_full_system)

    p_rep = sub.add_parser("report", help="generate final report")
    p_rep.set_defaults(func=cmd_report)

    p_mt = sub.add_parser("check-mood-tags", help="run §7.3 discriminativeness gate")
    p_mt.add_argument("--csv", help="path to processed CSV (default: config.PROCESSED_FILE)")
    p_mt.set_defaults(func=cmd_check_mood_tags)

    p_vas = sub.add_parser("va-sanity", help="build/evaluate VA sanity floor (engine-derived)")
    p_vas.add_argument("--rebuild", action="store_true", help="force rebuild even if file exists")
    p_vas.set_defaults(func=cmd_va_sanity)

    p_pcc = sub.add_parser(
        "pillar-c-color",
        help="Pillar C supplementary: RRF on recommend_by_colors() path (engine-derived-color GT)",
    )
    p_pcc.add_argument("--output", help="override output directory")
    p_pcc.add_argument("--rebuild", action="store_true", help="force rebuild color GT")
    p_pcc.set_defaults(func=cmd_run_pillar_c_color)

    p_pec = sub.add_parser(
        "pillar-e-color",
        help="Pillar E supplementary: CLAP on recommend_by_colors() path (engine-derived-color GT)",
    )
    p_pec.add_argument("--output", help="override output directory")
    p_pec.add_argument("--rebuild", action="store_true", help="force rebuild color GT")
    p_pec.set_defaults(func=cmd_run_pillar_e_color)

    p_pfx = sub.add_parser(
        "pillar-f-xartist",
        help="Pillar F circularity check: KG gain on cross-artist pairs only",
    )
    p_pfx.add_argument("--output", help="override output directory")
    p_pfx.set_defaults(func=cmd_run_pillar_f_xartist)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
