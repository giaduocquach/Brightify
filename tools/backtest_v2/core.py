"""Core config / runner / report contracts for backtest v2.

Phase 0 skeleton — types and signatures only. Logic lands in Phase 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BacktestConfig:
    """Run configuration. Loaded from configs/backtest_*.yaml (Phase 1)."""

    methods: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    ground_truth: Optional[str] = None
    test_set: Optional[str] = None
    top_k: int = 10
    seed: int = 42
    output_dir: Optional[str] = None


@dataclass
class BacktestReport:
    """Result of a run. `metrics` maps metric name -> value + validity label."""

    config: BacktestConfig
    metrics: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError("BacktestReport.to_dict — Phase 1")


class BacktestRunner:
    """Drives a backtest: sample queries, run a method, compute metrics.

    Phase 0 stub. Wraps the live MusicRecommender via catalog.py in Phase 1.
    """

    def __init__(self, config: BacktestConfig, catalog: Any = None):
        self.config = config
        self.catalog = catalog

    def run(self, override_weights: Optional[Dict[str, Any]] = None) -> BacktestReport:
        raise NotImplementedError("BacktestRunner.run — Phase 1")
