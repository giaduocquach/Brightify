"""CLI entry point for backtest v2. §6.4.

    python -m tools.backtest_v2 run --config configs/backtest_v0.yaml
    python -m tools.backtest_v2 ablation --signals timbral,rhythmic,...
    python -m tools.backtest_v2 optimize-weights --ground-truth editorial_playlists_v1
    python -m tools.backtest_v2 compare iter_0_baseline iter_1_weight_opt
    python -m tools.backtest_v2 report
    python -m tools.backtest_v2 check-mood-tags        # §7.3 gate (implemented)

Phase 0: argument surface + dispatch wired; commands are stubs except
check-mood-tags. Run/ablation/optimize land in Phases 1–4.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional


def _not_implemented(phase: str) -> int:
    print(f"[backtest_v2] not implemented yet — {phase}. See docs/PLAN_BACKTEST_METRICS.md")
    return 2


def cmd_run(args: argparse.Namespace) -> int:
    return _not_implemented("Phase 1 (baseline measure)")


def cmd_ablation(args: argparse.Namespace) -> int:
    return _not_implemented("Phase 3 (drop-one-signal ablation)")


def cmd_optimize_weights(args: argparse.Namespace) -> int:
    return _not_implemented("Phase 4 (weight optimization)")


def cmd_compare(args: argparse.Namespace) -> int:
    return _not_implemented("Phase 1+ (iteration compare)")


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
    p_run.add_argument("--config")
    p_run.add_argument("--ground-truth")
    p_run.add_argument("--method")
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
