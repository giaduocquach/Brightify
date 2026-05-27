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
from typing import List, Optional


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

    # Replace the "with_lyrics" line inside RECO_SONG_WEIGHTS dict
    pattern = r'("with_lyrics"\s*:\s*)\[.*?\]'
    replacement = r'\g<1>' + formatted
    new_src, n = re.subn(pattern, replacement, src)
    if n == 0:
        print("[optimize] WARNING: could not find 'with_lyrics' pattern in config.py — not updated")
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


def cmd_report(args: argparse.Namespace) -> int:
    return _not_implemented("Phase 6 (final report)")


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

    p_rep = sub.add_parser("report", help="generate final report")
    p_rep.set_defaults(func=cmd_report)

    p_mt = sub.add_parser("check-mood-tags", help="run §7.3 discriminativeness gate")
    p_mt.add_argument("--csv", help="path to processed CSV (default: config.PROCESSED_FILE)")
    p_mt.set_defaults(func=cmd_check_mood_tags)

    p_vas = sub.add_parser("va-sanity", help="build/evaluate VA sanity floor (engine-derived)")
    p_vas.add_argument("--rebuild", action="store_true", help="force rebuild even if file exists")
    p_vas.set_defaults(func=cmd_va_sanity)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
