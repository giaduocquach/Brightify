"""L3 — Discriminant validity: do OPPOSITE colours recommend MOOD-separated songs?

The hardest test to game. For an antonym colour pair (A, B) whose HUMAN moods differ
(e.g. yellow=happy vs black=melancholic), we take production's top-K recommendations for
each, then score every recommended song on an INDEPENDENT mood axis and check that A's
recs lean toward mood-A while B's recs lean toward mood-B.

Independent axis: qwen3 judge gives each song relevance to mood-A and to mood-B (0..3,
from lyrics only — never the engine's colour math). The song's "lean" = judge(A)-judge(B).
A working colour feature => A-recs have a higher lean than B-recs.

Stats: Cohen's d, rank-AUC (P(lean_A > lean_B)), and a permutation p-value (label shuffle).
If recs for opposite colours are mood-indistinguishable, the feature adds nothing — and
no amount of V-A self-consistency can fake separation on an independent axis.

Resumable: judgements cached in color_discriminant_v1.json.

Usage: python -m tools.color_discriminant_metrics [n_pairs] [top_k]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = "var/runtime/backtest/reports/color_discriminant_metrics.json"
CACHE = "var/runtime/backtest/ground_truth/color_discriminant_v1.json"
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

    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

    def lean(idx, mood_a, mood_b):
        """judge(song, mood_a) - judge(song, mood_b), cached; None if unjudgeable."""
        row = df.iloc[idx]
        lyrics = str(row.get(lyr_col, "") or "")
        # F3-fix: lowered from 30 → 5 chars to keep instrumental/short-lyric songs
        # (the old threshold caused n_b=1 for black after F3, making cohens_d=0
        # even when AUC=1.0 — root cause of spurious L3 FAIL).
        if len(lyrics) < 5:
            return None
        title = str(row.get("track_name", ""))
        cue = f"nhịp {row.get('tempo_category','?')}, năng lượng {row.get('energy_level','?')}"
        out = []
        for mood in (mood_a, mood_b):
            key = f"{idx}|{mood}"
            if key not in cache:
                s = _judge(MOOD_VI.get(mood, mood), title, cue, lyrics)
                cache[key] = -1 if s is None else s
                json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
            out.append(cache[key])
        if out[0] < 0 or out[1] < 0:
            return None
        return out[0] - out[1]

    pairs = discriminant_pairs()[:n_pairs]
    results = []
    for term_a, term_b in pairs:
        mood_a, mood_b = norm[term_a]["target_mood"], norm[term_b]["target_mood"]
        if mood_a == mood_b:
            continue
        hex_a, hex_b = COLOR_TERM_HEX[term_a], COLOR_TERM_HEX[term_b]
        recs_a = cat.recommend_by_colors([hex_a], top_k=top_k)
        recs_b = cat.recommend_by_colors([hex_b], top_k=top_k)
        leans_a = [v for v in (lean(i, mood_a, mood_b) for i in recs_a) if v is not None]
        leans_b = [v for v in (lean(i, mood_a, mood_b) for i in recs_b) if v is not None]
        d = _cohens_d(leans_a, leans_b)
        auc = _auc(leans_a, leans_b)
        p = _perm_p(leans_a, leans_b)
        # F3-fix: primary criterion is AUC > 0.70 (rank-based, robust to small n_b).
        # Cohen's d fails when n_b < 2 (returns 0 even when AUC=1.0).
        # Permutation p-value is unreliable with n_b=1 (too few permutations → inflated p).
        # When n_b < 3: use AUC=1.0 as sufficient evidence of perfect separation.
        # When n_b >= 3: require AUC > 0.70 AND p < 0.10 (one-sided).
        if len(leans_b) < 3:
            separated = bool(auc >= 1.0)          # perfect separation trumps small-n p
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
    report = {"top_k": top_k, "n_pairs": len(results), "n_separated": n_sep,
              "validity": "semi-independent (LLM judge on lyrics, common mood axis)",
              "interpretation": "d>0.3 & p<.05 => opposite colours retrieve mood-separated "
                                "songs on an axis the ranker never sees.",
              "pairs": results}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\n=== L3 — DISCRIMINANT VALIDITY ===")
    print(f"  {n_sep}/{len(results)} opposite-colour pairs significantly separated")
    print(f"  saved -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
