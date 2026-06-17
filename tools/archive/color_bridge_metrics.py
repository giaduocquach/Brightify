"""L1 — Bridge fidelity: does the engine's colour->emotion map match HUMAN data?

Validates AdvancedColorMapper.hsl_to_va() and .color_to_emotion_probs() against the
International Colour-Emotion Association Survey (ICEAS / Jonauskaite et al. 2020,
Psychological Science, OSF 2w6gh — 8615 participants per colour, 37 nations).

This is the NON-CIRCULAR core of the colour-feature defense: the answer key is human
ratings collected with no knowledge of Brightify, so agreement is genuine evidence
that "colour -> emotion" is implemented correctly.

Metrics (across the 12 normed colours):
  * V-A fidelity   — Pearson r + Spearman rho + RMSE between engine V-A and human V-A,
                     for valence and arousal separately. (bootstrap-CI over colours)
  * emotion shape  — mean cosine + Spearman between engine 8-emotion vector and the
                     human DISTINCTIVE 8-emotion profile, per colour.
  * mood top-1     — fraction of colours whose engine top-emotion == human target_mood,
                     and top-1-in-human-top-2 (lenient).

Usage: python -m tools.color_bridge_metrics
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = "var/runtime/backtest/reports/color_bridge_metrics.json"


def _boot_ci(fn, x, y, n_boot=10000, seed=42):
    """Bootstrap 95% CI of a paired statistic fn(x, y) by resampling the items."""
    rng = np.random.default_rng(seed)
    x = np.asarray(x); y = np.asarray(y)
    n = len(x)
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        try:
            stats.append(fn(x[idx], y[idx]))
        except Exception:
            continue
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return round(float(fn(x, y)), 4), round(float(lo), 4), round(float(hi), 4)


def main() -> int:
    from scipy.stats import pearsonr, spearmanr
    from core.advanced_color_mapping import get_advanced_color_mapper
    from tools.backtest_v2.ground_truth.color_norms import (
        load_human_color_norm, EMO8)

    norm = load_human_color_norm()
    m = get_advanced_color_mapper()
    terms = list(norm)

    hv, ha, ev, ea = [], [], [], []          # human/engine valence & arousal
    emo_cos, emo_rho = [], []                 # per-colour 8-emotion agreement
    top1_strict, top1_lenient = [], []
    per_color = {}

    for t in terms:
        d = norm[t]
        h_v, h_a = d["human_va"]
        e_v, e_a = m.hsl_to_va(d["hex"])
        hv.append(h_v); ha.append(h_a); ev.append(e_v); ea.append(e_a)

        eng_probs = m.color_to_emotion_probs(d["hex"])
        eng_vec = np.array([eng_probs.get(l, 0.0) for l in EMO8])
        hum_vec = np.array([d["distinctive8"].get(l, 0.0) for l in EMO8])
        cos = float(eng_vec @ hum_vec / (np.linalg.norm(eng_vec) * np.linalg.norm(hum_vec) + 1e-9))
        rho = float(spearmanr(eng_vec, hum_vec).correlation)
        emo_cos.append(cos); emo_rho.append(0.0 if np.isnan(rho) else rho)

        eng_top = EMO8[int(np.argmax(eng_vec))]
        hum_top2 = sorted(d["distinctive8"], key=d["distinctive8"].get, reverse=True)[:2]
        top1_strict.append(1.0 if eng_top == d["target_mood"] else 0.0)
        top1_lenient.append(1.0 if eng_top in hum_top2 else 0.0)

        per_color[t] = {
            "hex": d["hex"], "human_va": [round(h_v, 3), round(h_a, 3)],
            "engine_va": [round(e_v, 3), round(e_a, 3)],
            "human_mood": d["target_mood"], "engine_mood": eng_top,
            "emotion_cosine": round(cos, 3),
        }

    pear = lambda a, b: pearsonr(a, b)[0]
    spear = lambda a, b: spearmanr(a, b).correlation
    rmse = lambda a, b: float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))

    report = {
        "n_colors": len(terms),
        "ground_truth": "ICEAS / Jonauskaite 2020 (8615 ppl/colour, 37 nations) — EXTERNAL, human",
        "validity": "external",
        "caveat": "After the P1/P2 recalibration (2026-06), hsl_to_va valence and "
                  "color_to_emotion_probs are FIT TO this ICEAS data, so these are now "
                  "IN-SAMPLE. Honest generalisation = leave-one-out CV: valence Pearson "
                  "0.77 (was 0.26). Emotion cosine/mood top-1 are 1.0 by construction "
                  "(empirical lookup) — not evidence. The real out-of-sample evidence that "
                  "P1/P2 helped is L2 (retrieval on editorial/LLM GT) + L3 (discriminant), "
                  "whose GTs are independent of ICEAS.",
        "va_fidelity": {
            "valence_pearson": _boot_ci(pear, hv, ev),
            "valence_spearman": _boot_ci(spear, hv, ev),
            "valence_rmse": round(rmse(hv, ev), 4),
            "arousal_pearson": _boot_ci(pear, ha, ea),
            "arousal_spearman": _boot_ci(spear, ha, ea),
            "arousal_rmse": round(rmse(ha, ea), 4),
        },
        "emotion_shape": {
            "mean_cosine": round(float(np.mean(emo_cos)), 4),
            "mean_spearman": round(float(np.mean(emo_rho)), 4),
        },
        "mood_top1": {
            "strict_acc": round(float(np.mean(top1_strict)), 4),
            "lenient_acc_top2": round(float(np.mean(top1_lenient)), 4),
        },
        "per_color": per_color,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)

    f = report["va_fidelity"]
    print("\n=== L1 — COLOUR→EMOTION BRIDGE FIDELITY (vs human ICEAS) ===")
    print(f"  {report['n_colors']} colours | GT = human survey (external, non-circular)\n")
    print(f"  VALENCE  Pearson {f['valence_pearson'][0]:+.3f} CI{f['valence_pearson'][1:]}"
          f"  Spearman {f['valence_spearman'][0]:+.3f}  RMSE {f['valence_rmse']}")
    print(f"  AROUSAL  Pearson {f['arousal_pearson'][0]:+.3f} CI{f['arousal_pearson'][1:]}"
          f"  Spearman {f['arousal_spearman'][0]:+.3f}  RMSE {f['arousal_rmse']}")
    e, mo = report["emotion_shape"], report["mood_top1"]
    print(f"  EMOTION  mean cosine {e['mean_cosine']}  mean Spearman {e['mean_spearman']}")
    print(f"  MOOD     top-1 strict {mo['strict_acc']}  top-1-in-human-top2 {mo['lenient_acc_top2']}")
    print("\n  per-colour (human_mood vs engine_mood):")
    for t, c in per_color.items():
        flag = "" if c["human_mood"] == c["engine_mood"] else "  <-- mismatch"
        print(f"    {t:9s} {c['hex']:8s} humanVA{c['human_va']} engVA{c['engine_va']}"
              f"  {c['human_mood']:11s} -> {c['engine_mood']:11s}{flag}")
    print(f"\n  saved -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
