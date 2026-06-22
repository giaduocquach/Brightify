"""Brightify backtest framework v2 (offline content-based evaluation).

See docs/PLAN_BACKTEST_METRICS.md. This package is the Phase 0 skeleton:
module structure + runnable CLI. Metrics, ground truth, baselines, and the
improvement loop are filled in across Phases 1–5.
"""

from tools.backtest_v2.core import BacktestConfig, BacktestRunner, BacktestReport

__all__ = ["BacktestConfig", "BacktestRunner", "BacktestReport"]
