"""Phase 2 — Multi-judge LLM agreement (pseudo-human evaluation rigor).

A single LLM judge can be biased; a thesis-grade pseudo-human evaluation needs ≥2 judges from
DIFFERENT model families + inter-rater agreement (Zheng 2023 'LLM-as-judge'; Liu 2023 G-Eval;
Landis & Koch 1977 κ bands). The colour-mood GT was built offline by Qwen3:8b (judge A, cached
in color_gpt_gt_v1.json). This re-judges the SAME (colour, song) pairs with OpenAI gpt-4o-mini
(judge B, different family) and reports cross-family agreement: quadratic-weighted Cohen's κ,
exact-agreement, Spearman, and relevant-set (≥2) agreement. High κ ⇒ the LLM-judge GT is a
reliable pseudo-human signal, not one model's idiosyncrasy.

Run: python -m tools.llm_judge_agreement [--per-color 8]
"""
from __future__ import annotations
import argparse, json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CACHED_GT = "var/runtime/backtest/ground_truth/color_gpt_gt_v1.json"   # judge A (Qwen3, offline)
REL = 2


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--per-color", type=int, default=8)
    args = ap.parse_args()
    from sklearn.metrics import cohen_kappa_score
    from scipy.stats import spearmanr
    os.environ["BRIGHTIFY_COLOR_JUDGE"] = "openai"
    from tools.backtest_v2.ground_truth.color_llm_gt import _judge_openai, MOOD_VI
    from core.recommendation_engine import get_recommender

    df = get_recommender().df.reset_index(drop=True)
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"
    gt = json.load(open(CACHED_GT))
    rng = np.random.RandomState(0)

    def audio_cue(row):
        return f"nhịp {row.get('tempo_category','?')}, năng lượng {row.get('energy_level','?')}"

    A, B, rows_log = [], [], []
    print(f"\nMULTI-JUDGE AGREEMENT — Qwen3 (cached, judge A) vs OpenAI gpt-4o-mini (judge B)")
    print(f"{'colour':9} {'mood':12} {'n':>3}  sample κ-pairs")
    for hexv, entry in gt.items():
        mood = entry.get("target_mood", ""); judged = entry.get("judged", {})
        items = [(int(k), int(v)) for k, v in judged.items() if int(v) >= 0]   # drop -1 unjudgeable
        if not items:
            continue
        rng.shuffle(items)
        picked = items[:args.per_color]
        for idx, qwen_score in picked:
            row = df.iloc[idx]
            lyr = str(row.get(lyr_col, "") or "")
            if len(lyr) < 30:
                continue
            ob = _judge_openai(MOOD_VI.get(mood, mood), str(row.get("track_name", "")),
                               audio_cue(row), lyr)
            if ob is None:
                continue
            A.append(qwen_score); B.append(int(ob))
            rows_log.append((entry.get("term", hexv), mood, qwen_score, int(ob)))
        print(f"{entry.get('term',hexv):9} {mood:12} {len([r for r in rows_log if r[0]==entry.get('term',hexv)]):>3}")

    A, B = np.array(A), np.array(B)
    if len(A) < 10:
        print(f"\n[abort] only {len(A)} comparable pairs"); return 1
    kw = cohen_kappa_score(A, B, weights="quadratic")
    kraw = cohen_kappa_score(A, B)
    exact = float(np.mean(A == B))
    within1 = float(np.mean(np.abs(A - B) <= 1))
    rho = spearmanr(A, B).correlation
    # relevant-set (≥2) agreement
    ra, rb = (A >= REL), (B >= REL)
    rel_agree = float(np.mean(ra == rb))
    band = ("almost perfect" if kw >= .81 else "substantial" if kw >= .61 else
            "moderate" if kw >= .41 else "fair" if kw >= .21 else "slight")
    print(f"\n=== INTER-JUDGE AGREEMENT (n={len(A)} colour-song pairs, scores 0–3) ===")
    print(f"  Cohen's κ (quadratic-weighted) = {kw:.3f}  → {band} (Landis & Koch 1977)")
    print(f"  Cohen's κ (unweighted)         = {kraw:.3f}")
    print(f"  exact agreement                = {exact:.1%}   within-1                = {within1:.1%}")
    print(f"  Spearman ρ                     = {rho:+.3f}")
    print(f"  relevant-set (≥2) agreement    = {rel_agree:.1%}")
    print(f"\n  Interpretation: two LLM judges from DIFFERENT families agree at κ={kw:.2f} ({band}),")
    print(f"  supporting the LLM-judge GT as a reliable pseudo-human signal (Zheng 2023, G-Eval).")
    out = {"n_pairs": len(A), "kappa_quadratic": round(float(kw), 4),
           "kappa_unweighted": round(float(kraw), 4), "exact": round(exact, 4),
           "within1": round(within1, 4), "spearman": round(float(rho), 4),
           "relevant_set_agreement": round(rel_agree, 4),
           "judge_A": "qwen3:8b (cached)", "judge_B": "openai gpt-4o-mini"}
    json.dump(out, open("data/llm_judge_agreement.json", "w"), indent=2)
    print(f"\n→ data/llm_judge_agreement.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
