"""Markdown report writer. §14 template — Phase 1."""

from __future__ import annotations

import os
from typing import Any, Dict, List


def write_markdown(report: Any, path: str) -> None:
    """Write BacktestReport as Markdown per §14 template."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)

    d = report.to_dict()
    meta = d.get('meta', {})
    metrics = d.get('metrics', {})
    systems = d.get('systems', {})
    latency = d.get('latency', {})

    lines: List[str] = []
    _h1(lines, "Brightify Recommendation Engine — Baseline Report (iter_0)")
    lines.append(f"**Date:** {meta.get('date', 'N/A')}")
    lines.append(f"**Catalog:** {meta.get('n_catalog', '?')} songs")
    lines.append(f"**Queries:** {meta.get('n_queries', '?')} (stratified seed=42)")
    lines.append(f"**Top-K:** {meta.get('top_k', 10)}")
    lines.append(f"**Engine:** {meta.get('iteration', 'iter_0_baseline')}")
    lines.append("")

    # ------------------------------------------------------------------
    # Property metrics table
    # ------------------------------------------------------------------
    _h2(lines, "1. Property Metrics (Group A — validity: property)")
    lines.append(
        "> All metrics below are property metrics (no ground truth). "
        "Higher ILD = more diverse. Higher Coherence = more consistent mood/tempo/color. "
        "Lower Calibration error = better emotion distribution match."
    )
    lines.append("")

    METRIC_INFO: Dict[str, str] = {
        'ild_lyrics':        'ILD Lyrics (cosine, ↑ diverse)',
        'ild_audio':         'ILD Audio (cosine, ↑ diverse)',
        'ild_va':            'ILD V-A (Euclid, ↑ diverse)',
        'ild_color':         'ILD Color (CIEDE2000, ↑ diverse)',
        'coverage':          'Coverage (↑ more catalog)',
        'artist_gini':       'Artist Gini (↓ more equitable)',
        'mood_coherence':    'MoodCoherence (↑ consistent)',
        'tempo_coherence':   'TempoCoherence (↑ consistent)',
        'color_coherence':   'ColorCoherence (↑ consistent)',
        'calibration_error': 'Calibration Error KL (↓ better)',
        'symmetry':          'Symmetry Jaccard (↑ consistent)',
        'serendipity_proxy': 'Serendipity Proxy (↑ surprising)',
    }

    # Header
    sys_names = list(systems.keys())
    header = '| Metric | ' + ' | '.join(sys_names) + ' |'
    sep = '|---|' + '---|' * len(sys_names)
    lines.append(header)
    lines.append(sep)

    for metric_key, label in METRIC_INFO.items():
        row_cells = [label]
        for sname in sys_names:
            sys_data = systems.get(sname, {})
            m = sys_data.get(metric_key)
            if m is None:
                row_cells.append('—')
            elif isinstance(m, dict):
                val = m.get('value', '?')
                ci = m.get('ci95', [None, None])
                if isinstance(val, float):
                    cell = f"{val:.4f}"
                    if ci[0] is not None:
                        cell += f" [{ci[0]:.4f}, {ci[1]:.4f}]"
                else:
                    cell = str(val)
                row_cells.append(cell)
            else:
                row_cells.append(f"{float(m):.4f}")
        lines.append('| ' + ' | '.join(row_cells) + ' |')

    lines.append("")

    # ------------------------------------------------------------------
    # Quadrant breakdown
    # ------------------------------------------------------------------
    quad = meta.get('quadrant_breakdown', {})
    if quad:
        _h2(lines, "2. Query Distribution by Quadrant")
        lines.append("| Quadrant | N | Note |")
        lines.append("|---|---|---|")
        notes = {
            'Q1': 'Happy/Excited',
            'Q2': 'Angry/Tense — **EXEMPT** from per-quadrant pass/fail (n<30)',
            'Q3': 'Sad/Depressed',
            'Q4': 'Calm/Peaceful',
        }
        for q in sorted(quad.keys()):
            lines.append(f"| {q} | {quad[q]} | {notes.get(q, '')} |")
        lines.append("")

    # ------------------------------------------------------------------
    # Latency
    # ------------------------------------------------------------------
    if latency:
        _h2(lines, "3. Latency (Brightify v7.2, N=200)")
        lines.append("| Method | p50 (ms) | p95 (ms) | p99 (ms) |")
        lines.append("|---|---|---|---|")
        for method, lat in latency.items():
            p50 = lat.get('p50', 0)
            p95 = lat.get('p95', 0)
            p99 = lat.get('p99', 0)
            lines.append(f"| {method} | {p50:.1f} | {p95:.1f} | {p99:.1f} |")
        lines.append("")

    # ------------------------------------------------------------------
    # Data quality notes
    # ------------------------------------------------------------------
    _h2(lines, "4. Data / Validity Notes")
    lines.append("- **Ground truth**: none (Phase 1 property-only). Accuracy metrics (NDCG) require Phase 2 editorial playlists.")
    lines.append("- **mood_tags**: REJECTED (§7.3 gate — 98.2% tagged 'corporate', non-discriminative).")
    lines.append("- **Q2**: n=14 total in catalog — exempt from per-quadrant pass/fail.")
    lines.append("- All metrics carry `validity: 'property'` label in report.json.")
    lines.append("- Tautology guard: V-A/quadrant NOT used as ground truth (engine input).")
    lines.append("")

    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


def _h1(lines: List[str], text: str) -> None:
    lines.extend([f"# {text}", ""])


def _h2(lines: List[str], text: str) -> None:
    lines.extend([f"## {text}", ""])
