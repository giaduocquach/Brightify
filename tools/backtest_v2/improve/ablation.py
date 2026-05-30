"""Drop-one-signal ablation → rank signals by importance. §11.2 — Phase 3.

For each signal in {timbral, rhythmic, tonal, lyrics, va, emotion, mood}:
zero its weight, normalize the rest, re-run, record ΔNDCG@10 / ΔILD_lyrics / ΔMoodCoherence.
Largest |ΔNDCG@10| = most important signal → upgrade that pillar first.

Output: reports/iter_0_baseline/ablation/signal_importance.json
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

SIGNALS = ["timbral", "rhythmic", "tonal", "lyrics", "va", "emotion", "mood"]

# §11.2 mapping: signal → pillar upgrade
SIGNAL_TO_PILLAR = {
    "lyrics":   {"pillar": "B", "name": "SimCSE (dangvantuan/vietnamese-embedding)", "action": "Replace PhoBERT embedding model"},
    "timbral":  {"pillar": "A", "name": "MERT/CLAP audio encoder", "action": "Replace Essentia timbral features"},
    "rhythmic": {"pillar": "A", "name": "MERT/CLAP audio encoder", "action": "Replace Essentia rhythmic features"},
    "tonal":    {"pillar": "A", "name": "MERT/CLAP audio encoder", "action": "Replace Essentia tonal features"},
    "va":       {"pillar": "E", "name": "MLP emotion combiner", "action": "Improve V-A estimation"},
    "emotion":  {"pillar": "E", "name": "MLP emotion combiner", "action": "Improve emotion vector quality"},
    "mood":     {"pillar": "D", "name": "MMR/DPP diversity", "action": "Improve mood post-processing or diversity"},
}


def _ablated_weights(base_weights: List[float], drop_idx: int) -> List[float]:
    """Zero weight[drop_idx], normalize remaining to sum=1.0."""
    w = list(base_weights)
    w[drop_idx] = 0.0
    total = sum(w)
    if total <= 0:
        # Fallback: uniform over remaining signals
        n = len(w)
        return [1.0 / (n - 1) if i != drop_idx else 0.0 for i in range(n)]
    return [x / total for x in w]


def run_ablation(
    catalog: Any,
    ground_truth: Dict[int, List[int]],
    base_weights: Optional[List[float]] = None,
    output_dir: str = "var/runtime/backtest/reports/iter_0_baseline/ablation",
    gt_name: str = "editorial_playlists_v1",
    n_queries: int = 500,
    seed: int = 42,
    top_k: int = 10,
) -> Dict[str, Any]:
    """Run drop-one-signal ablation over all 7 signals.

    Args:
        catalog       — Catalog instance (already loaded).
        ground_truth  — {seed_idx: [relevant_idx, ...]} from editorial GT.
        base_weights  — baseline weights (default: config.RECO_SONG_WEIGHTS["with_lyrics"]).
        output_dir    — where to save signal_importance.json.
        gt_name       — GT source label for report metadata.
        n_queries     — number of property-metric queries (stratified, seed=42).
        seed          — random seed.
        top_k         — recommendation depth.

    Returns:
        signal_importance dict (also saved to output_dir/signal_importance.json).
    """
    import config as cfg
    from tools.backtest_v2.baselines.brightify import BrightifyBaseline
    from tools.backtest_v2.metrics.accuracy import evaluate_system_accuracy, ndcg_at_k
    from tools.backtest_v2.metrics.property import compute_all
    from tools.backtest_v2.stats import stratified_sample

    if base_weights is None:
        base_weights = list(cfg.RECO_SONG_WEIGHTS["with_lyrics"])

    assert len(base_weights) == len(SIGNALS), (
        f"base_weights length {len(base_weights)} != {len(SIGNALS)} signals"
    )

    # --- Baseline metrics (brightify_v7.2 full weights) ---
    print("[ablation] Running baseline system for delta reference...")
    baseline_sys = BrightifyBaseline(catalog, weights=None)  # uses config defaults

    baseline_ndcg = _eval_ndcg(baseline_sys, ground_truth, top_k=top_k, gt_name=gt_name)

    queries = stratified_sample(catalog.df, n=n_queries, seed=seed)
    baseline_ild, baseline_mood, baseline_sameart = _eval_property(baseline_sys, queries, catalog, top_k)

    print(f"[ablation] Baseline: NDCG@10={baseline_ndcg:.6f}  "
          f"ILD_lyrics={baseline_ild:.6f}  MoodCoher={baseline_mood:.6f}  "
          f"SameArtist@10={baseline_sameart:.6f}")

    # --- Per-signal ablation ---
    results: List[Dict[str, Any]] = []

    for i, signal in enumerate(SIGNALS):
        w = _ablated_weights(base_weights, i)
        print(f"[ablation]  drop '{signal}' → weights={[round(x, 4) for x in w]}")

        ablated_sys = BrightifyBaseline(catalog, weights=w)

        ndcg = _eval_ndcg(ablated_sys, ground_truth, top_k=top_k, gt_name=gt_name)
        ild, mood, sameart = _eval_property(ablated_sys, queries, catalog, top_k)

        delta_ndcg = ndcg - baseline_ndcg
        delta_ild = ild - baseline_ild
        delta_mood = mood - baseline_mood
        delta_sameart = sameart - baseline_sameart

        pillar_info = SIGNAL_TO_PILLAR[signal]
        results.append({
            "signal": signal,
            "drop_idx": i,
            "ablated_weights": [round(x, 6) for x in w],
            "ndcg_at_10": round(ndcg, 6),
            "delta_ndcg_at_10": round(delta_ndcg, 6),
            "ild_lyrics": round(ild, 6),
            "delta_ild_lyrics": round(delta_ild, 6),
            "mood_coherence": round(mood, 6),
            "delta_mood_coherence": round(delta_mood, 6),
            "same_artist_at_10": round(sameart, 6),
            "delta_same_artist_at_10": round(delta_sameart, 6),
            "importance_abs_ndcg": round(abs(delta_ndcg), 6),
            "pillar": pillar_info["pillar"],
            "pillar_name": pillar_info["name"],
            "pillar_action": pillar_info["action"],
            "ground_truth": gt_name,
            "validity": "external",
        })
        print(f"[ablation]    ΔNDCG@10={delta_ndcg:+.6f}  "
              f"ΔILD={delta_ild:+.6f}  ΔMood={delta_mood:+.6f}  ΔSameArtist={delta_sameart:+.6f}")

    # Sort by |ΔNDCG@10| descending — most important first
    results_sorted = sorted(results, key=lambda r: r["importance_abs_ndcg"], reverse=True)

    # Build pillar priority recommendation
    pillar_priority = _build_pillar_priority(results_sorted)

    output = {
        "meta": {
            "date": _today(),
            "base_weights": [round(x, 6) for x in base_weights],
            "signals": SIGNALS,
            "baseline_ndcg_at_10": round(baseline_ndcg, 6),
            "baseline_ild_lyrics": round(baseline_ild, 6),
            "baseline_mood_coherence": round(baseline_mood, 6),
            "baseline_same_artist_at_10": round(baseline_sameart, 6),
            "n_gt_queries": len(ground_truth),
            "n_property_queries": n_queries,
            "top_k": top_k,
            "seed": seed,
            "gt_name": gt_name,
            "validity": "external",
        },
        "signal_importance": results_sorted,
        "weakest_signal": results_sorted[-1]["signal"],
        "most_important_signal": results_sorted[0]["signal"],
        "pillar_priority": pillar_priority,
    }

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "signal_importance.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"[ablation] Saved: {out_path}")

    _print_table(output)
    return output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eval_ndcg(
    system: Any,
    ground_truth: Dict[int, List[int]],
    top_k: int,
    gt_name: str,
) -> float:
    """Return mean NDCG@top_k over all GT queries."""
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k as _ndcg

    scores: List[float] = []
    for seed_idx, relevant_list in ground_truth.items():
        relevant = set(relevant_list)
        if not relevant:
            continue
        ranked = system.recommend(seed_idx, top_k=top_k)
        scores.append(_ndcg(ranked, relevant, top_k))
    return float(np.mean(scores)) if scores else 0.0


def _eval_property(
    system: Any,
    queries: List[int],
    catalog: Any,
    top_k: int,
) -> tuple:
    """Return (mean_ild_lyrics, mean_mood_coherence, mean_same_artist_at_k)."""
    from tools.backtest_v2.metrics.property import compute_all

    ild_values: List[float] = []
    mood_values: List[float] = []
    same_artist_values: List[float] = []  # GT-3 — similar-song bias

    for seed_idx in queries:
        recs = system.recommend(seed_idx, top_k=top_k)
        if not recs:
            continue
        row = compute_all(recs, seed_idx, catalog)
        if "ild_lyrics" in row:
            ild_values.append(row["ild_lyrics"])
        if "mood_coherence" in row:
            mood_values.append(row["mood_coherence"])
        if "same_artist_at_k" in row:
            same_artist_values.append(row["same_artist_at_k"])

    ild = float(np.mean(ild_values)) if ild_values else 0.0
    mood = float(np.mean(mood_values)) if mood_values else 0.0
    same_artist = float(np.mean(same_artist_values)) if same_artist_values else 0.0
    return ild, mood, same_artist


def _build_pillar_priority(results_sorted: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build unique pillar upgrade order from ablation results (weakest → most important)."""
    seen_pillars: set = set()
    priority: List[Dict[str, Any]] = []

    # Weakest signals (small |ΔNDCG|) = most room for improvement → upgrade first
    for r in reversed(results_sorted):
        p = r["pillar"]
        if p not in seen_pillars:
            seen_pillars.add(p)
            priority.append({
                "rank": len(priority) + 1,
                "pillar": p,
                "pillar_name": r["pillar_name"],
                "action": r["pillar_action"],
                "driven_by_signal": r["signal"],
                "delta_ndcg_at_10": r["delta_ndcg_at_10"],
                "reasoning": (
                    f"Signal '{r['signal']}' has smallest |ΔNDCG@10|={r['importance_abs_ndcg']:.4f} "
                    f"→ currently weakest contributor → most room to improve"
                ),
            })

    return priority


def _print_table(output: Dict[str, Any]) -> None:
    meta = output["meta"]
    rows = output["signal_importance"]
    print()
    print("=" * 84)
    print("  ABLATION RESULTS — drop-one-signal (recommend_by_song)")
    print(f"  Baseline: NDCG@10={meta['baseline_ndcg_at_10']:.4f}  "
          f"ILD={meta['baseline_ild_lyrics']:.4f}  "
          f"MoodCoher={meta['baseline_mood_coherence']:.4f}")
    print("=" * 84)
    print(f"  {'Signal':<10} {'ΔNDCG@10':>10} {'ΔILD_lyrics':>12} {'ΔMoodCoher':>12}  {'|ΔNDCG|':>8}  Pillar")
    print("-" * 84)
    for r in rows:
        print(
            f"  {r['signal']:<10} "
            f"{r['delta_ndcg_at_10']:>+10.4f} "
            f"{r['delta_ild_lyrics']:>+12.4f} "
            f"{r['delta_mood_coherence']:>+12.4f}  "
            f"{r['importance_abs_ndcg']:>8.4f}  "
            f"Pillar {r['pillar']} ({r['pillar_name']})"
        )
    print()
    print(f"  Most important: {output['most_important_signal']}  |  "
          f"Weakest: {output['weakest_signal']}")
    print()
    print("  PILLAR UPGRADE ORDER (weakest → most important):")
    for p in output["pillar_priority"]:
        print(f"    {p['rank']}. Pillar {p['pillar']} — {p['pillar_name']} "
              f"(driven by '{p['driven_by_signal']}', ΔNDCG={p['delta_ndcg_at_10']:+.4f})")
    print("=" * 84)


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()
