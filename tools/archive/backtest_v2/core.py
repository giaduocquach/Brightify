"""Core config / runner / report for backtest v2. §6 — Phase 1.

BacktestRunner orchestrates:
  1. Stratified sample of 500 queries (seed=42).
  2. Run each system on every query → collect per-query property metrics.
  3. Aggregate with bootstrap CI.
  4. Measure latency for brightify methods.
  5. Write JSON + Markdown reports.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from tools.backtest_v2.stats import (
    ci_from_samples,
    paired_bootstrap,
    quadrant_breakdown,
    stratified_sample,
)
from tools.backtest_v2.metrics.property import (
    artist_gini,
    catalog_coverage,
    compute_all,
    similar_song_symmetry,
)
from tools.backtest_v2.metrics.operational import measure_all_methods


@dataclass
class BacktestConfig:
    """Run configuration. Loaded from configs/backtest_*.yaml."""

    methods: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    baselines: List[str] = field(default_factory=lambda: ['random', 'audio_only', 'lyrics_only', 'va_only', 'brightify_v7.2'])
    ground_truth: Optional[str] = None
    test_set: Optional[str] = None
    top_k: int = 10
    seed: int = 42
    n_queries: int = 500
    output_dir: Optional[str] = None
    iteration_name: str = 'iter_0_baseline'
    latency_n: int = 200

    @classmethod
    def from_yaml(cls, path: str) -> "BacktestConfig":
        import yaml
        with open(path, encoding='utf-8') as fh:
            d = yaml.safe_load(fh)
        return cls(
            methods=d.get('methods', []),
            metrics=d.get('metrics', []),
            baselines=d.get('baselines', ['random', 'audio_only', 'lyrics_only', 'va_only', 'brightify_v7.2']),
            ground_truth=d.get('ground_truth'),
            test_set=d.get('test_set'),
            top_k=int(d.get('top_k', 10)),
            seed=int(d.get('seed', 42)),
            n_queries=int(d.get('n_queries', 500)),
            output_dir=d.get('output_dir'),
            iteration_name=d.get('iteration_name', 'iter_0_baseline'),
            latency_n=int(d.get('latency_n', 200)),
        )


@dataclass
class BacktestReport:
    """Results of one backtest run."""

    config: BacktestConfig
    # {system_name: {metric_name: {value, ci95, validity, ...}}}
    systems: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    latency: Dict[str, Dict[str, float]] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'meta': self.meta,
            'systems': self.systems,
            'latency': self.latency,
        }


def _metric_entry(
    per_query_values: List[float],
    validity: str = 'property',
    ground_truth: Optional[str] = None,
    n_boot: int = 10_000,
    seed: int = 42,
) -> Dict[str, Any]:
    """Wrap per-query values into a report entry with CI."""
    if not per_query_values:
        return {'value': None, 'ci95': [None, None], 'n': 0, 'validity': validity}
    mean, ci_low, ci_high = ci_from_samples(per_query_values, n_boot=n_boot, seed=seed)
    entry: Dict[str, Any] = {
        'value': round(mean, 6),
        'ci95': [round(ci_low, 6), round(ci_high, 6)],
        'n': len(per_query_values),
        'validity': validity,
    }
    if ground_truth is not None:
        entry['ground_truth'] = ground_truth
    return entry


def _build_systems(config: BacktestConfig, catalog: Any) -> Dict[str, Any]:
    """Instantiate all requested baseline systems."""
    from tools.backtest_v2.baselines.random_b import RandomBaseline
    from tools.backtest_v2.baselines.audio_only import AudioOnlyBaseline
    from tools.backtest_v2.baselines.lyrics_only import LyricsOnlyBaseline
    from tools.backtest_v2.baselines.va_only import VAOnlyBaseline
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline

    mapping = {
        'random': lambda: RandomBaseline(catalog, seed=config.seed),
        'audio_only': lambda: AudioOnlyBaseline(catalog),
        'lyrics_only': lambda: LyricsOnlyBaseline(catalog),
        'va_only': lambda: VAOnlyBaseline(catalog),
        'brightify_v7.2': lambda: BrightifyBaseline(catalog),
    }

    systems = {}
    for name in config.baselines:
        if name in mapping:
            systems[name] = mapping[name]()
        else:
            print(f"[backtest_v2] unknown baseline '{name}' — skipped")
    return systems


def _run_system(
    system: Any,
    queries: Sequence[int],
    catalog: Any,
    top_k: int,
    symmetry_sample: int = 100,
) -> Dict[str, Any]:
    """Evaluate one system on all queries. Returns aggregated metric dict."""
    per_query: Dict[str, List[float]] = {}
    all_recs: List[List[int]] = []

    for seed_idx in queries:
        recs = system.recommend(seed_idx, top_k=top_k)
        if not recs:
            continue
        row = compute_all(recs, seed_idx, catalog)
        for k, v in row.items():
            per_query.setdefault(k, []).append(v)
        all_recs.append(recs)

    # Per-query metrics → CI
    result: Dict[str, Any] = {}
    for metric_name, values in per_query.items():
        result[metric_name] = _metric_entry(values)

    # Global metrics (not per-query)
    result['coverage'] = {
        'value': round(catalog_coverage(all_recs, catalog.n), 6),
        'ci95': [None, None],
        'n': len(all_recs),
        'validity': 'property',
    }
    result['artist_gini'] = {
        'value': round(artist_gini(all_recs, catalog), 6),
        'ci95': [None, None],
        'n': len(all_recs),
        'validity': 'property',
    }

    # Symmetry — run on a random subsample of queries (expensive: O(n²) recommend calls)
    sym_seeds = list(queries[:symmetry_sample])
    sym_value = similar_song_symmetry(
        lambda idx, k: system.recommend(idx, top_k=k),
        sym_seeds,
        top_k,
    )
    result['symmetry'] = {
        'value': round(sym_value, 6),
        'ci95': [None, None],
        'n': len(sym_seeds),
        'validity': 'property',
    }

    return result


class BacktestRunner:
    """Orchestrates a full Phase 1 backtest run."""

    def __init__(self, config: BacktestConfig, catalog: Any = None) -> None:
        self.config = config
        self.catalog = catalog

    def run(self, override_weights: Optional[Dict[str, Any]] = None) -> BacktestReport:
        from loguru import logger

        cfg = self.config
        catalog = self.catalog

        if catalog is None:
            from tools.backtest_v2.catalog import Catalog
            logger.info("[backtest_v2] Loading catalog (MusicRecommender)...")
            catalog = Catalog.load()
            self.catalog = catalog

        logger.info(f"[backtest_v2] Catalog: {catalog.n} songs")

        # 1. Sample queries
        logger.info(f"[backtest_v2] Sampling {cfg.n_queries} queries (stratified seed={cfg.seed})...")
        queries = stratified_sample(catalog.df, n=cfg.n_queries, seed=cfg.seed)
        quad_info = quadrant_breakdown(catalog.df, queries)
        logger.info(f"[backtest_v2] Quadrant breakdown: {quad_info}")

        # Save test set JSON
        if cfg.output_dir:
            import json
            os.makedirs(cfg.output_dir, exist_ok=True)
            ts_path = os.path.join('var/runtime/backtest/test_sets', 'test_set_v1.json')
            os.makedirs(os.path.dirname(ts_path), exist_ok=True)
            with open(ts_path, 'w') as fh:
                json.dump({
                    'n': len(queries),
                    'seed': cfg.seed,
                    'queries': queries,
                    'quadrant_breakdown': quad_info,
                }, fh, indent=2)

        # 2. Build systems
        systems = _build_systems(cfg, catalog)
        if override_weights and 'brightify_v7.2' in systems:
            from tools.backtest_v2.baselines.brightify import BrightifyBaseline
            systems['brightify_v7.2'] = BrightifyBaseline(catalog, weights=override_weights.get('recommend_by_song'))

        # 3. Evaluate each system
        system_results: Dict[str, Any] = {}
        for name, system in systems.items():
            logger.info(f"[backtest_v2] Evaluating system: {name} ({len(queries)} queries)...")
            system_results[name] = _run_system(system, queries, catalog, cfg.top_k)
            logger.info(f"[backtest_v2]   Done: {name}")

        # 4. Latency
        logger.info(f"[backtest_v2] Measuring latency (N={cfg.latency_n})...")
        latency = measure_all_methods(catalog, queries[:50], n=cfg.latency_n)

        # 5. Assemble report
        meta = {
            'date': datetime.date.today().isoformat(),
            'iteration': cfg.iteration_name,
            'n_catalog': catalog.n,
            'n_queries': len(queries),
            'top_k': cfg.top_k,
            'seed': cfg.seed,
            'quadrant_breakdown': quad_info,
        }

        report = BacktestReport(
            config=cfg,
            systems=system_results,
            latency=latency,
            meta=meta,
        )

        # 6. Write reports
        if cfg.output_dir:
            from tools.backtest_v2.reporters.json_export import write_json
            from tools.backtest_v2.reporters.markdown import write_markdown
            os.makedirs(cfg.output_dir, exist_ok=True)
            json_path = os.path.join(cfg.output_dir, 'report.json')
            md_path = os.path.join(cfg.output_dir, 'report.md')
            write_json(report, json_path)
            write_markdown(report, md_path)
            logger.info(f"[backtest_v2] Reports written to {cfg.output_dir}/")

        return report
