"""L3 — Discriminant validity: do OPPOSITE colours recommend MOOD-separated songs?

V22 decouple: Qwen3:8b ONLY (Ollama, offline). Gemini removed from panel.
Rationale: Gemini labels song valence (v5c) AND was half the L3 judge panel
→ self-preference circularity (Panickssery NeurIPS 2024). One decoupled judge
is more defensible than a half-circular panel (Verga 2024 PoLL requires judges
to be independent). Qwen3 ≠ Gemini labeler → genuinely decoupled.

For an antonym colour pair (A, B) whose HUMAN moods differ (e.g. yellow=happy vs
black=melancholic), Qwen3 judges each recommended song on mood-A and mood-B (0-3,
from lyrics only — never the engine's colour math). lean = score(mood_A) - score(mood_B).
A-recs should have higher lean than B-recs.

Stats: Cohen's d, rank-AUC (P(lean_A > lean_B)), permutation p-value.
Cache: color_discriminant_v1.json (Qwen3, already populated).

Usage: python -m tools.color_discriminant_metrics [n_pairs] [top_k]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT        = "var/runtime/backtest/reports/color_discriminant_metrics.json"
CACHE_QWEN = "var/runtime/backtest/ground_truth/color_discriminant_v1.json"
# CACHE_GEMINI removed (V22): Gemini was labeler+judge — circularity.
DEFAULT_PAIRS = 4
TOP_K = 15


def _cohens_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return float((a.mean() - b.mean()) / sp) if sp > 0 else 0.0


def _auc(a, b):
    """P(x_a > x_b) over all pairs — rank/Mann-Whitney AUC."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if not len(a) or not len(b):
        return 0.5
    wins = sum((a[:, None] > b[None, :]).sum() + 0.5 * (a[:, None] == b[None, :]).sum() for _ in [0])
    return float(wins / (len(a) * len(b)))


def _perm_p(a, b, n=10000, seed=42):
    """Permutation p-value for mean(a) > mean(b) (one-sided)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(seed)
    obs = a.mean() - b.mean()
    pool = np.concatenate([a, b]); na = len(a)
    ge = 0
    for _ in range(n):
        rng.shuffle(pool)
        if (pool[:na].mean() - pool[na:].mean()) >= obs:
            ge += 1
    return round((ge + 1) / (n + 1), 4)


def main() -> int:
    n_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PAIRS
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else TOP_K

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.color_norms import (
        load_human_color_norm, discriminant_pairs, COLOR_TERM_HEX)
    from tools.backtest_v2.ground_truth.color_llm_gt import _judge, MOOD_VI

    cat = Catalog.load()
    norm = load_human_color_norm()
    df = cat.df
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"

    # Qwen3-only cache (V22: Gemini removed — was labeler+judge = circular).
    cache_q = json.load(open(CACHE_QWEN)) if os.path.exists(CACHE_QWEN) else {}

    def panel_lean(idx: int, mood_a: str, mood_b: str) -> float | None:
        """Qwen3 lean = score(mood_A) - score(mood_B). Cached, resumable."""
        row    = df.iloc[idx]
        lyrics = str(row.get(lyr_col, "") or "")
        if len(lyrics) < 5:
            return None
        title   = str(row.get("track_name", ""))
        cue     = f"nhịp {row.get('tempo_category','?')}, năng lượng {row.get('energy_level','?')}"
        scores  = []
        for mood in (mood_a, mood_b):
            key = f"{idx}|{mood}"
            if key not in cache_q:
                s = _judge(MOOD_VI.get(mood, mood), title, cue, lyrics)
                cache_q[key] = -1 if s is None else s
                json.dump(cache_q, open(CACHE_QWEN, "w"), ensure_ascii=False)
            scores.append(None if cache_q[key] < 0 else int(cache_q[key]))
        if scores[0] is None or scores[1] is None:
            return None
        return float(scores[0] - scores[1])

    pairs = discriminant_pairs()[:n_pairs]
    results = []
    for term_a, term_b in pairs:
        mood_a, mood_b = norm[term_a]["target_mood"], norm[term_b]["target_mood"]
        if mood_a == mood_b:
            continue
        hex_a, hex_b = COLOR_TERM_HEX[term_a], COLOR_TERM_HEX[term_b]
        recs_a = cat.recommend_by_colors([hex_a], top_k=top_k)
        recs_b = cat.recommend_by_colors([hex_b], top_k=top_k)
        leans_a = [v for v in (panel_lean(i, mood_a, mood_b) for i in recs_a) if v is not None]
        leans_b = [v for v in (panel_lean(i, mood_a, mood_b) for i in recs_b) if v is not None]
        d = _cohens_d(leans_a, leans_b)
        auc = _auc(leans_a, leans_b)
        p = _perm_p(leans_a, leans_b)
        if len(leans_b) < 3:
            separated = bool(auc >= 1.0)
        else:
            separated = bool(auc > 0.70 and p < 0.10)
        results.append({
            "pair": f"{term_a}({mood_a}) vs {term_b}({mood_b})",
            "hex": [hex_a, hex_b],
            "mean_lean_A": round(float(np.mean(leans_a)), 3) if leans_a else None,
            "mean_lean_B": round(float(np.mean(leans_b)), 3) if leans_b else None,
            "cohens_d": round(d, 3), "auc": round(auc, 3), "perm_p": p,
            "n_a": len(leans_a), "n_b": len(leans_b),
            "separated": separated,
        })
        print(f"  {results[-1]['pair']:42s} d={d:+.2f} AUC={auc:.2f} p={p} "
              f"({'SEP' if separated else 'ns'})")

    n_sep = sum(r["separated"] for r in results)

    report = {
        "top_k": top_k, "n_pairs": len(results), "n_separated": n_sep,
        "judge": "Qwen3:8b (Ollama, offline) — V22 decoupled from Gemini labeler",
        "validity": (
            "independent: Qwen3 ≠ Gemini valence labeler (v5c). "
            "Judge reads lyrics only — never engine V-A or colour math."),
        "interpretation": (
            "AUC>0.70 & p<0.10 => opposite colours retrieve mood-separated songs "
            "on an axis the ranker never sees. Single judge (no κ): Gemini removed "
            "to eliminate labeler=judge circularity (V22, Panickssery NeurIPS 2024)."),
        "pairs": results,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\n=== L3 — DISCRIMINANT VALIDITY (Qwen3, decoupled V22) ===")
    print(f"  {n_sep}/{len(results)} opposite-colour pairs significantly separated")
    print(f"  Judge: Qwen3:8b only (Gemini removed — was labeler+judge = circular)")
    print(f"  saved -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
