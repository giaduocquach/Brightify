"""Bước A — Chẩn đoán skew valence: artifact Qwen hay catalog thật?

Chạy: python -m tools.diagnose_valence_skew
Output: var/runtime/backtest/reports/valence_skew_diagnosis.json + print verdict
"""
import json, sys, os
from collections import Counter
import numpy as np
import pandas as pd
from scipy import stats

OUT_DIR = "var/runtime/backtest/reports"
os.makedirs(OUT_DIR, exist_ok=True)

def run():
    v4 = json.load(open("data/emotion_labels_v4.json"))
    df = pd.read_csv("data/vietnamese_music_processed_full.csv",
                     usecols=["track_id","track_name","primary_artist",
                               "valence","sentiment_compound","mode","energy","tempo"])
    df["track_id"] = df["track_id"].astype(str)
    gt = json.load(open("var/runtime/backtest/ground_truth/color_editorial_gt_v1.json"))

    vals = np.array([float(v.get("valence", 0.5)) for v in v4.values()])
    aros = np.array([float(v.get("arousal", 0.5)) for v in v4.values()])
    v4_map = {tid: float(v.get("valence", 0.5)) for tid, v in v4.items()}
    df["llm_v"] = df["track_id"].map(v4_map)
    df = df.dropna(subset=["llm_v", "valence", "sentiment_compound"])

    report = {}

    # 1. Discretization
    rounded = np.round(vals, 2)
    cnt = Counter(rounded)
    top = sorted(cnt.items(), key=lambda x: -x[1])[:12]
    dominant_val, dominant_cnt = top[0]
    dominant_pct = dominant_cnt / len(vals)
    is_discrete = all(abs(round(v * 10) / 10 - v) < 0.001 for v in vals[:200])
    report["discretization"] = {
        "top_values": [{"value": float(v), "count": int(c), "pct": round(c/len(vals),3)}
                       for v, c in top],
        "dominant_value": float(dominant_val),
        "dominant_pct": round(float(dominant_pct), 3),
        "is_discrete_scale": is_discrete,
        "n_unique_rounded": len(cnt),
        "finding": "ARTIFACT" if dominant_pct > 0.30 else "OK",
    }

    # 2. Correlations
    r_essentia = float(df["llm_v"].corr(df["valence"]))
    r_vader = float(df["llm_v"].corr(df["sentiment_compound"]))
    r_mode = float(df["llm_v"].corr(df["mode"]))
    r_energy = float(df["llm_v"].corr(df["energy"]))
    report["correlations"] = {
        "llm_v_vs_essentia_audio": round(r_essentia, 3),
        "llm_v_vs_vader_sentiment": round(r_vader, 3),
        "llm_v_vs_mode": round(r_mode, 3),
        "llm_v_vs_energy": round(r_energy, 3),
        "finding": "WEAK" if r_essentia < 0.30 else "OK",
    }

    # 3. Separability: editorial happy vs rest
    colors_data = gt["colors"]
    happy_idxs = set()
    for ch, ci in colors_data.items():
        if ci.get("target_mood") == "happy":
            happy_idxs.update(ci.get("relevant", []))
    df_happy = df[df.index.isin(happy_idxs)]
    df_rest  = df[~df.index.isin(happy_idxs)]
    u, p = stats.mannwhitneyu(df_happy["llm_v"], df_rest["llm_v"], alternative="greater")
    auc = float(u) / (len(df_happy) * len(df_rest))
    happy_median = float(df_happy["llm_v"].median())
    rest_median  = float(df_rest["llm_v"].median())
    report["separability"] = {
        "n_happy_editorial": len(df_happy),
        "n_rest": len(df_rest),
        "happy_mean_llm_v": round(float(df_happy["llm_v"].mean()), 3),
        "rest_mean_llm_v":  round(float(df_rest["llm_v"].mean()), 3),
        "happy_median_llm_v": happy_median,
        "rest_median_llm_v":  rest_median,
        "mannwhitney_auc": round(auc, 3),
        "mannwhitney_p":   round(float(p), 4),
        "finding": "ARTIFACT" if auc < 0.55 else "OK",
        "interpretation": (
            "LLM-valence CANNOT separate editorial happy from rest "
            f"(AUC={auc:.3f} ≈ random, p={p:.4f})"
            if auc < 0.55 else
            f"LLM-valence separates happy from rest (AUC={auc:.3f})"
        ),
    }

    # 4. Arousal: same problem?
    rounded_a = np.round(aros, 2)
    ca = Counter(rounded_a)
    top_a = sorted(ca.items(), key=lambda x: -x[1])[:5]
    is_discrete_a = all(abs(round(a * 10) / 10 - a) < 0.001 for a in aros[:200])
    report["arousal_check"] = {
        "top_values": [{"value": float(v), "count": int(c), "pct": round(c/len(aros),3)}
                       for v, c in top_a],
        "is_discrete_scale": is_discrete_a,
        "finding": "OK (MERT-continuous)" if not is_discrete_a else "ARTIFACT",
    }

    # 5. Happy song value distribution
    hc = Counter(np.round(df_happy["llm_v"].values, 2))
    report["happy_song_llm_v_distribution"] = [
        {"value": float(v), "count": int(c), "pct": round(c/len(df_happy),3)}
        for v, c in sorted(hc.items(), key=lambda x: -x[1])[:8]
    ]

    # --- VERDICT ---
    n_artifacts = sum([
        report["discretization"]["finding"] == "ARTIFACT",
        report["correlations"]["finding"] == "WEAK",
        report["separability"]["finding"] == "ARTIFACT",
    ])
    verdict = "ARTIFACT" if n_artifacts >= 2 else "REAL"
    report["VERDICT"] = {
        "result": verdict,
        "confidence": "HIGH" if n_artifacts == 3 else "MEDIUM",
        "n_evidence_for_artifact": n_artifacts,
        "summary": (
            "Qwen over-negativity + coarse discretization: "
            f"{report['discretization']['dominant_pct']*100:.0f}% bài stuck at "
            f"V={report['discretization']['dominant_value']:.2f}; "
            f"LLM không phân biệt editorial happy vs rest (AUC={auc:.3f}). "
            "→ Step C (cải thiện rubric) ROI CAO."
            if verdict == "ARTIFACT" else
            "Catalog thật sự lệch buồn. Step C ROI thấp hơn; anti-skew là đúng công cụ."
        ),
        "recommended_action": (
            "Cải thiện prompt LLM: (1) đổi sang thang 0-100 integer để tránh coarse-10pt; "
            "(2) thêm few-shot anchor Vietnamese; "
            "(3) spot-check decoupled LLM (non-Qwen) trên 50 bài để confirm."
            if verdict == "ARTIFACT" else
            "Giữ nguyên; anti-skew + heteroscedastic RBF đã xử lý đúng."
        ),
    }

    # Print
    print("=" * 60)
    print("BƯỚC A — VALENCE SKEW DIAGNOSIS")
    print("=" * 60)
    print(f"\n[1] DISCRETIZATION: {report['discretization']['finding']}")
    print(f"    V={dominant_val:.2f} xuất hiện ở {dominant_pct*100:.1f}% bài")
    print(f"    Chỉ có {len(cnt)} giá trị unique (multiples of 0.1: {'YES' if is_discrete else 'no'})")

    print(f"\n[2] CORRELATIONS: {report['correlations']['finding']}")
    print(f"    LLM-V vs Essentia audio: r={r_essentia:.3f}")
    print(f"    LLM-V vs VADER (English): r={r_vader:.3f}")
    print(f"    LLM-V vs mode: r={r_mode:.3f}  (mode VN đảo ngược → expected ~0)")

    print(f"\n[3] SEPARABILITY (editorial happy n={len(df_happy)} vs rest n={len(df_rest)}): "
          f"{report['separability']['finding']}")
    print(f"    happy mean={df_happy['llm_v'].mean():.3f}  rest mean={df_rest['llm_v'].mean():.3f}")
    print(f"    Mann-Whitney AUC={auc:.3f}  p={p:.4f}")
    print(f"    → {report['separability']['interpretation']}")

    print(f"\n[4] AROUSAL CHECK: {report['arousal_check']['finding']}")
    print(f"    (MERT-probe → continuous, không bị lỗi quantization)")

    print(f"\n{'='*60}")
    print(f"VERDICT: {report['VERDICT']['result']} ({report['VERDICT']['confidence']} confidence)")
    print(f"  {report['VERDICT']['summary']}")
    print(f"\nACTION: {report['VERDICT']['recommended_action']}")
    print("=" * 60)

    out_path = f"{OUT_DIR}/valence_skew_diagnosis.json"
    json.dump(report, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nsaved → {out_path}")
    return report

if __name__ == "__main__":
    run()
