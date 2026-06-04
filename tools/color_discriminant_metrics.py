"""L3 — Discriminant validity: do OPPOSITE colours recommend MOOD-separated songs?

Phase 3 upgrade: PoLL panel (Qwen3 + Gemini 2.5-flash) per Verga 2024.
Panel = average of 2 distinct-family judges. Reports Fleiss/Cohen κ between judges.
Judge ≠ labeler constraint: Qwen3 is Ollama (offline); Gemini is API (labeler in v5b
for valence, but L3 task is lyrics-mood relevance 0-3 — different task, acceptable).
Known ceiling: multilingual judge κ≈0.3 (EMNLP 2025) — cite in report, not a failure.

For an antonym colour pair (A, B) whose HUMAN moods differ (e.g. yellow=happy vs
black=melancholic), each recommended song is judged by BOTH models on mood-A and mood-B.
Panel lean = avg(qwen_lean, gemini_lean) where lean = score(mood_A) - score(mood_B).
A-recs should have higher panel lean than B-recs.

Stats: Cohen's d, rank-AUC (P(lean_A > lean_B)), permutation p-value.
Two separate caches: color_discriminant_v1.json (Qwen3), color_discriminant_gemini_v1.json.

Usage: python -m tools.color_discriminant_metrics [n_pairs] [top_k]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT   = "var/runtime/backtest/reports/color_discriminant_metrics.json"
CACHE_QWEN   = "var/runtime/backtest/ground_truth/color_discriminant_v1.json"
CACHE_GEMINI = "var/runtime/backtest/ground_truth/color_discriminant_gemini_v1.json"
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
    from tools.backtest_v2.ground_truth.color_llm_gt import (
        _judge, _judge_gemini, MOOD_VI)

    cat = Catalog.load()
    norm = load_human_color_norm()
    df = cat.df
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"

    cache_q = json.load(open(CACHE_QWEN))   if os.path.exists(CACHE_QWEN)   else {}
    cache_g = json.load(open(CACHE_GEMINI)) if os.path.exists(CACHE_GEMINI) else {}

    # Collect (qwen_score, gemini_score) per (idx, mood) for κ computation
    kappa_pairs: list[tuple[int, int]] = []   # (qwen_score, gemini_score)

    def _get_scores(idx: int, mood: str) -> tuple[int | None, int | None]:
        """Return (qwen, gemini) scores for song × mood, using caches."""
        row = df.iloc[idx]
        lyrics = str(row.get(lyr_col, "") or "")
        if len(lyrics) < 5:
            return None, None
        title = str(row.get("track_name", ""))
        cue   = f"nhịp {row.get('tempo_category','?')}, năng lượng {row.get('energy_level','?')}"
        mood_vi = MOOD_VI.get(mood, mood)
        key = f"{idx}|{mood}"

        # Qwen3
        if key not in cache_q:
            s = _judge(mood_vi, title, cue, lyrics)
            cache_q[key] = -1 if s is None else s
            json.dump(cache_q, open(CACHE_QWEN, "w"), ensure_ascii=False)
        sq = None if cache_q[key] < 0 else int(cache_q[key])

        # Gemini (different family — PoLL Verga 2024)
        if key not in cache_g:
            s = _judge_gemini(mood_vi, title, cue, lyrics)
            cache_g[key] = -1 if s is None else s
            json.dump(cache_g, open(CACHE_GEMINI, "w"), ensure_ascii=False)
        sg = None if cache_g[key] < 0 else int(cache_g[key])

        if sq is not None and sg is not None:
            kappa_pairs.append((sq, sg))
        return sq, sg

    def panel_lean(idx: int, mood_a: str, mood_b: str) -> float | None:
        """PoLL panel lean = avg(qwen_lean, gemini_lean). Falls back to single judge."""
        sa_q, sa_g = _get_scores(idx, mood_a)
        sb_q, sb_g = _get_scores(idx, mood_b)
        leans = []
        if sa_q is not None and sb_q is not None:
            leans.append(sa_q - sb_q)
        if sa_g is not None and sb_g is not None:
            leans.append(sa_g - sb_g)
        return float(np.mean(leans)) if leans else None

    def _cohens_kappa(pairs: list[tuple[int, int]]) -> float:
        """Cohen's κ between 2 judges on 0-3 scale."""
        if len(pairs) < 10:
            return float('nan')
        a = [p[0] for p in pairs]; b = [p[1] for p in pairs]
        po = sum(x == y for x, y in zip(a, b)) / len(pairs)
        # Expected agreement by chance
        cats = list(range(4))
        n = len(pairs)
        pa = [a.count(c) / n for c in cats]
        pb = [b.count(c) / n for c in cats]
        pe = sum(x * y for x, y in zip(pa, pb))
        return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0

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
    kappa = _cohens_kappa(kappa_pairs)
    kappa_note = (f"κ={kappa:.3f} (ceiling for VN ~0.3, EMNLP 2025)" if not np.isnan(kappa)
                  else "κ=n/a (insufficient pairs)")

    report = {
        "top_k": top_k, "n_pairs": len(results), "n_separated": n_sep,
        "panel": "Qwen3:8b (Ollama) + Gemini-2.5-flash (API) — PoLL Verga 2024",
        "inter_judge_kappa": kappa,
        "kappa_note": kappa_note,
        "validity": "semi-independent PoLL panel (lyrics mood axis, not engine V-A)",
        "interpretation": (
            "Panel lean = avg(Qwen3, Gemini) judge scores. "
            "AUC>0.70 & p<0.10 => opposite colours retrieve mood-separated songs."),
        "pairs": results,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\n=== L3 — DISCRIMINANT VALIDITY (PoLL panel) ===")
    print(f"  {n_sep}/{len(results)} opposite-colour pairs significantly separated")
    print(f"  Inter-judge agreement: {kappa_note}")
    print(f"  saved -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
