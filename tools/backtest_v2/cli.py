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
    """Phase 1: measure baseline property metrics for all systems."""
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

    runner = BacktestRunner(config)
    report = runner.run()

    # Print summary to stdout
    _print_summary(report)
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
    return _not_implemented("Phase 3 (drop-one-signal ablation)")


def cmd_optimize_weights(args: argparse.Namespace) -> int:
    return _not_implemented("Phase 4 (weight optimization)")


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
    p_abl.set_defaults(func=cmd_ablation)

    p_opt = sub.add_parser("optimize-weights", help="search RECO_SONG_WEIGHTS")
    p_opt.add_argument("--ground-truth")
    p_opt.add_argument("--method")
    p_opt.add_argument("--constraint")
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

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
