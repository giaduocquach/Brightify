"""L3 discriminant validity for recommend_by_song (similar-song).

Port of color_discriminant_metrics.py logic, applied to music similarity:

  Define emotion-opposite cluster pairs from fused_emotion.
  For each pair (emo_A, emo_B): sample N seed songs from each cluster.
  Get top-K recommendations from each seed group.
  Qwen3:8b judges every recommended song on mood_A vs mood_B:
      lean = score(mood_A) − score(mood_B)
  Claim: recs from A-seeds should have higher lean than recs from B-seeds.
  Stats: Cohen's d, rank-AUC (Mann-Whitney), permutation p-value.
  PASS: AUC > 0.70 & p < 0.10 (or AUC == 1.0 for tiny samples).

Non-circular: judge reads title + fused_emotion + tempo/energy + lyrics snippet.
              Never sees engine's cosine scores, V-A values, or MERT embeddings.

Cache: similar_discriminant_v1.json (key="{idx}|{mood}", same format as
       color_discriminant_v1.json — compatible if moods overlap).

Usage: python -m tools.similar_discriminant_metrics [n_pairs] [n_seeds] [top_k]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT        = "var/runtime/backtest/reports/similar_discriminant_metrics.json"
CACHE_FILE = "var/runtime/backtest/ground_truth/similar_discriminant_v1.json"
DEFAULT_N_SEEDS = 8    # seed songs per emotion cluster
DEFAULT_TOP_K   = 15   # recommendations per seed

# Russell-circumplex opposite pairs — chosen for maximum mood distance.
# happy↔sad (Q1 vs Q3), excited↔melancholic (Q1 vs Q3-Q4 border),
# tense↔peaceful (Q2 vs Q4), calm↔angry (Q4 vs Q2).
EMOTION_PAIRS = [
    ("happy",    "sad"),
    ("excited",  "melancholic"),
    ("tense",    "peaceful"),
    ("calm",     "angry"),
]

# Vietnamese mood descriptions — same vocabulary as color_llm_gt.MOOD_VI.
MOOD_VI = {
    "happy":       "vui tươi, hạnh phúc, tích cực, rộn ràng",
    "sad":         "buồn bã, đau khổ, mất mát, nước mắt",
    "excited":     "phấn khích, sôi động, tràn đầy năng lượng, hứng khởi",
    "melancholic": "u sầu, hoài niệm, man mác buồn, tiếc nuối nhẹ",
    "tense":       "căng thẳng, bồn chồn, lo âu, bất an",
    "peaceful":    "yên bình, thanh thản, dịu dàng, an nhiên",
    "calm":        "bình tĩnh, nhẹ nhàng, thư thái, êm dịu",
    "angry":       "giận dữ, phẫn nộ, mạnh mẽ dữ dội, bùng nổ",
}


# ---------------------------------------------------------------------------
# Stats helpers (same as color_discriminant_metrics)
# ---------------------------------------------------------------------------

def _cohens_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return float((a.mean() - b.mean()) / sp) if sp > 0 else 0.0


def _auc(a, b):
    """P(x_a > x_b) — Mann-Whitney rank AUC."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if not len(a) or not len(b):
        return 0.5
    wins = float((a[:, None] > b[None, :]).sum()) + 0.5 * float((a[:, None] == b[None, :]).sum())
    return wins / (len(a) * len(b))


def _perm_p(a, b, n: int = 10_000, seed: int = 42) -> float:
    """One-sided permutation p-value for mean(a) > mean(b)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(seed)
    obs = a.mean() - b.mean()
    pool = np.concatenate([a, b])
    na = len(a)
    ge = 0
    for _ in range(n):
        perm = rng.permutation(pool)
        if perm[:na].mean() - perm[na:].mean() >= obs:
            ge += 1
    return round((ge + 1) / (n + 1), 4)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    n_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else len(EMOTION_PAIRS)
    n_seeds = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_N_SEEDS
    top_k   = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_TOP_K

    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.color_llm_gt import _judge as _mood_judge

    cat = Catalog.load()
    df  = cat.df
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"
    rng = np.random.default_rng(42)

    cache: dict = json.load(open(CACHE_FILE)) if os.path.exists(CACHE_FILE) else {}

    def _save():
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        json.dump(cache, open(CACHE_FILE, "w"), ensure_ascii=False)

    def panel_lean(idx: int, mood_a: str, mood_b: str) -> float | None:
        """Qwen3 lean = score(mood_A) − score(mood_B). Resumable."""
        row    = df.iloc[idx]
        lyrics = str(row.get(lyr_col, "") or "")
        if len(lyrics) < 5:
            return None
        title = str(row.get("track_name", ""))
        cue   = f"nhịp {row.get('tempo_category','?')}, năng lượng {row.get('energy_level','?')}"
        scores = []
        for mood in (mood_a, mood_b):
            key = f"{idx}|{mood}"
            if key not in cache:
                s = _mood_judge(MOOD_VI.get(mood, mood), title, cue, lyrics)
                cache[key] = -1 if s is None else s
                _save()
            scores.append(None if cache[key] < 0 else int(cache[key]))
        if any(s is None for s in scores):
            return None
        return float(scores[0] - scores[1])

    if "fused_emotion" not in df.columns:
        print("[discriminant] ERROR: fused_emotion column missing in catalog")
        return 1

    results = []
    for emo_a, emo_b in EMOTION_PAIRS[:n_pairs]:
        idxs_a = np.where(df["fused_emotion"].values == emo_a)[0]
        idxs_b = np.where(df["fused_emotion"].values == emo_b)[0]
        min_needed = n_seeds
        if len(idxs_a) < min_needed or len(idxs_b) < min_needed:
            print(f"  [skip] {emo_a}({len(idxs_a)}) vs {emo_b}({len(idxs_b)}) "
                  f"— need {min_needed} each")
            continue

        seeds_a = [int(i) for i in rng.choice(idxs_a, size=n_seeds, replace=False)]
        seeds_b = [int(i) for i in rng.choice(idxs_b, size=n_seeds, replace=False)]

        # Collect recs from both seed groups (deduplicated within each group)
        recs_a: list[int] = list(dict.fromkeys(
            i for s in seeds_a for i in cat.recommend_by_song(s, top_k=top_k)
        ))
        recs_b: list[int] = list(dict.fromkeys(
            i for s in seeds_b for i in cat.recommend_by_song(s, top_k=top_k)
        ))

        print(f"  Judging {emo_a}({len(recs_a)} recs) vs {emo_b}({len(recs_b)} recs)…")
        leans_a = [v for v in (panel_lean(i, emo_a, emo_b) for i in recs_a) if v is not None]
        leans_b = [v for v in (panel_lean(i, emo_a, emo_b) for i in recs_b) if v is not None]

        d   = _cohens_d(leans_a, leans_b)
        auc = _auc(leans_a, leans_b)
        p   = _perm_p(leans_a, leans_b)
        if len(leans_b) < 3:
            separated = bool(auc >= 1.0)
        else:
            separated = bool(auc > 0.70 and p < 0.10)

        results.append({
            "pair":       f"{emo_a} vs {emo_b}",
            "n_seeds":    n_seeds,
            "top_k":      top_k,
            "mean_lean_A": round(float(np.mean(leans_a)), 3) if leans_a else None,
            "mean_lean_B": round(float(np.mean(leans_b)), 3) if leans_b else None,
            "cohens_d":   round(d, 3),
            "auc":        round(auc, 3),
            "perm_p":     p,
            "n_A":        len(leans_a),
            "n_B":        len(leans_b),
            "separated":  separated,
        })
        print(f"  {emo_a:12s} vs {emo_b:12s}: d={d:+.2f}  AUC={auc:.2f}  "
              f"p={p}  ({'SEP ✓' if separated else 'ns  ✗'})")

    n_sep = sum(r["separated"] for r in results)
    report = {
        "n_pairs":             len(results),
        "n_separated":         n_sep,
        "n_seeds_per_cluster": n_seeds,
        "top_k":               top_k,
        "judge":               "Qwen3:8b (Ollama, offline)",
        "validity":            ("Non-circular: judge reads title+fused_emotion+tempo+energy+lyrics. "
                                "Never sees engine cosine scores, V-A values, or MERT embeddings."),
        "pass_criterion":      "AUC > 0.70 & perm_p < 0.10",
        "pairs":               results,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)

    print(f"\n=== SIMILAR-SONG — DISCRIMINANT VALIDITY (Qwen3, offline) ===")
    print(f"  {n_sep}/{len(results)} emotion-opposite pairs significantly separated")
    print(f"  saved → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
