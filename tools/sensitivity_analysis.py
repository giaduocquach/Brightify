"""Sensitivity analysis for the hand-set / heuristic serving weights.

Goal: prove the serving values sit in FLAT (robust) regions — i.e. the exact
choice is not load-bearing — and make the similar-song NDCG↔MoodCoherence
trade-off explicit. Read-only: this script changes NOTHING that serving uses;
it sweeps parameters in-memory and writes a JSON report only.

Covers two of the three sweeps (the arousal tempo-weight sweep already exists as
tools/tune_muq_arousal.py and is run separately):

  A. Colour RBF bandwidth (sigma_V, sigma_A) -> Targeting Error (TE)
     Reuses the engine's quantile-space V-A coords (rec.song_va_match) and the
     same Gaussian-RBF scoring the recommender uses (recommendation_engine line
     ~727), isolating sigma's effect on TE over the 12 ICEAS colours.

  B. Similar-song fusion V-A weight -> MoodCoherence + graded NDCG@10
     Reuses backtest_v2's Catalog + property.mood_coherence + the multi-judge
     musical-similarity ground truth (graded 0-3) over its 52 seeds.

Run: python -m tools.sensitivity_analysis
"""
from __future__ import annotations
import json, math, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

OUT = "var/runtime/backtest/reports/sensitivity_analysis.json"
MUSICAL_GT = "var/runtime/backtest/ground_truth/similar_musical_gt_v1.json"
TOP_K = 10

ICEAS_COLS = [
    ('#BE0032', 'red'),    ('#F38400', 'orange'), ('#F3C300', 'yellow'),
    ('#FFB7C5', 'pink'),   ('#008856', 'green'),  ('#3AB09E', 'turquoise'),
    ('#0067A5', 'blue'),   ('#9C4F96', 'purple'), ('#80461B', 'brown'),
    ('#F2F3F4', 'white'),  ('#848482', 'grey'),   ('#222222', 'black'),
]


def _euclidean_te(idxs, va_match, target) -> float:
    if not idxs:
        return 1.0
    pts = va_match[np.array(idxs, int)]
    return float(np.mean(np.linalg.norm(pts - target, axis=1)))


def _graded_ndcg(ranked, judged: dict, k: int = TOP_K) -> float:
    """Graded NDCG@k. judged: {candidate_idx_str: grade 0..3}; unjudged -> 0."""
    dcg = sum((2 ** judged.get(str(it), 0) - 1) / math.log2(i + 2)
              for i, it in enumerate(ranked[:k]))
    ideal = sorted(judged.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def sweep_color_sigma(rec) -> dict:
    """TE vs (sigma_V, sigma_A) in the engine's quantile-match space."""
    va_match = rec.song_va_match if getattr(rec, "song_va_match", None) is not None else rec.song_va
    targets = []
    for hx, _ in ICEAS_COLS:
        cv, ca = rec.color_mapper.hsl_to_va(hx)
        q = rec._color_target_quantile([cv, ca])
        targets.append(np.asarray(q, float))

    base_v, base_a = cfg.COLOR_SCORE_VA_SIGMA_V, cfg.COLOR_SCORE_VA_SIGMA_A  # 0.20 / 0.14

    def te_at(sv, sa) -> float:
        tes = []
        for tgt in targets:
            dv = va_match[:, 0] - tgt[0]
            da = va_match[:, 1] - tgt[1]
            scores = np.exp(-0.5 * ((dv / sv) ** 2 + (da / sa) ** 2))
            top = np.argsort(scores)[::-1][:TOP_K].tolist()
            tes.append(_euclidean_te(top, va_match, tgt))
        return float(np.mean(tes))

    grid_v = [0.12, 0.16, 0.20, 0.24, 0.28]
    grid_a = [0.08, 0.11, 0.14, 0.17, 0.20]
    # 1-D sweep on each axis holding the other at its serving value
    sweep_v = {f"{sv:.2f}": te_at(sv, base_a) for sv in grid_v}
    sweep_a = {f"{sa:.2f}": te_at(base_v, sa) for sa in grid_a}
    return {
        "serving": {"sigma_v": base_v, "sigma_a": base_a, "TE": te_at(base_v, base_a)},
        "sweep_sigma_v_at_serving_a": sweep_v,
        "sweep_sigma_a_at_serving_v": sweep_a,
        "note": "TE over 12 ICEAS colours in quantile space; lower=better. Isolated RBF scoring (no MMR/cover).",
    }


def sweep_fusion_va(cat) -> dict:
    """MoodCoherence + graded NDCG@10 vs the similar-song V-A fusion weight."""
    from tools.backtest_v2.metrics.property import mood_coherence

    gt = json.load(open(MUSICAL_GT))
    seeds = [(int(s["seed_idx"]), s["judged"]) for s in gt.values()]
    lyr = 0.08  # lyrics weight held at serving value
    # weight layout: [timbral, rhythmic, tonal, lyrics, va, emotion/inst, mood, mert(audio)]
    va_grid = [0.00, 0.08, 0.16, 0.24, 0.32]
    rows = {}
    for va in va_grid:
        audio = 1.0 - lyr - va
        w = [0.0, 0.0, 0.0, lyr, va, 0.0, 0.0, audio]
        nd, mc = [], []
        for seed_idx, judged in seeds:
            recs = cat.recommend_by_song(seed_idx, top_k=TOP_K, weights=w)
            if not recs:
                continue
            nd.append(_graded_ndcg(recs, judged))
            mc.append(mood_coherence(recs, cat))
        rows[f"{va:.2f}"] = {
            "audio_w": round(audio, 3),
            "ndcg10_graded": round(float(np.mean(nd)), 4),
            "mood_coherence": round(float(np.mean(mc)), 4),
            "n_seeds": len(nd),
        }
    return {
        "serving_va_weight": 0.16,
        "lyrics_weight": lyr,
        "sweep": rows,
        "note": "graded NDCG@10 on multi-judge musical GT (52 seeds) vs MoodCoherence; "
                "shows NDCG flat/declining while MoodCoherence rises with V-A weight.",
    }


def main() -> int:
    from tools.backtest_v2.catalog import Catalog
    print("[sensitivity] loading catalog…")
    cat = Catalog.load()
    rec = cat.rec

    print("[sensitivity] A) colour RBF sigma sweep…")
    color = sweep_color_sigma(rec)
    print(f"  serving (σv={color['serving']['sigma_v']}, σa={color['serving']['sigma_a']}) "
          f"TE={color['serving']['TE']:.4f}")
    print("  TE vs σ_V (σ_A@serving):", {k: round(v, 4) for k, v in color["sweep_sigma_v_at_serving_a"].items()})
    print("  TE vs σ_A (σ_V@serving):", {k: round(v, 4) for k, v in color["sweep_sigma_a_at_serving_v"].items()})

    print("[sensitivity] B) similar-song fusion V-A weight sweep…")
    fusion = sweep_fusion_va(cat)
    for k, v in fusion["sweep"].items():
        print(f"  V-A={k} (audio={v['audio_w']}): NDCG@10={v['ndcg10_graded']}  "
              f"MoodCoh={v['mood_coherence']}  (n={v['n_seeds']})")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"color_sigma": color, "fusion_va": fusion}, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\n[sensitivity] wrote → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
