"""B3 (V21) — Recalibrate MERT-arousal: proxy-anchor + tuned blend + quantile-map to DEAM.

V21 upgrade over Phase 1 (2026-06-04 audit):
  Phase 1 weakness: blend weights (0.65/0.35) were hand-picked; variance-expansion
  to std=0.18 was an arbitrary "magic number" with no principled reference.

B3 fix (Maraun 2013 / Fisher transformation / Spearman CV):
  1. Proxy-arousal: energy + loudness_lufs + neg-danceability (Spearman > 0.4, culture-neutral).
  2. Tune blend weight w* via grid-search maximising Σ Spearman(blend_w, proxy_j) — label-free,
     reproducible, no magic number. Reports sensitivity curve.
  3. Quantile-map blend → DEAM arousal distribution (n=1802, mean=0.477, std=0.160) —
     REPLACES arbitrary variance_expand. CDF-to-CDF matching preserves ranking while
     aligning the full distribution shape (skew, tails) not just mean/std (Maraun 2013).

Outputs: data/arousal_v3.json   (tid→arousal float 0-1, B3)
         data/emotion_labels_v5c.json  (v5 valence + B3 arousal)
Config:  RELABELED_EMOTIONS_FILE → v5c after gate.

Run:  python -m tools.recalibrate_arousal
Gate: python -m tools.validate_arousal v3
"""
import json, os, sys, glob
import numpy as np
import pandas as pd
from scipy import stats, interpolate
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

OUT_ARO    = "data/arousal_v3.json"
OUT_LABELS = "data/emotion_labels_v5c.json"
DEAM_DIR   = "data/external/deam"

# Blend weight search space — will be tuned, not hard-coded
W_GRID = np.arange(0.40, 0.91, 0.05)


def load_deam_arousal() -> np.ndarray:
    """Load DEAM static arousal annotations, normalise 1..9 → 0..1."""
    fs = glob.glob(
        f"{DEAM_DIR}/**/song_level/static_annotations_averaged_songs_*.csv",
        recursive=True)
    if not fs:
        raise FileNotFoundError(f"No DEAM annotation CSVs found in {DEAM_DIR}")
    dfs = [pd.read_csv(f) for f in fs]
    df  = pd.concat(dfs, ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    aro_raw = df["arousal_mean"].dropna().values.astype(float)
    return np.clip((aro_raw - 1.0) / 8.0, 0.0, 1.0)


def build_proxy(df: pd.DataFrame) -> np.ndarray:
    """Label-free audio-arousal proxy from Essentia features (z-scored, sigmoid-mapped).
    Feature selection by Spearman(feature, MERT-arousal): energy+0.448, lufs+0.364, neg-dance+0.653.
    """
    def zscore(x: np.ndarray) -> np.ndarray:
        s = x.std()
        return (x - x.mean()) / s if s > 1e-9 else np.zeros_like(x)

    energy    = zscore(df["energy"].fillna(df["energy"].median()).values)
    lufs      = zscore(df["loudness_lufs"].fillna(df["loudness_lufs"].median()).values)
    neg_dance = zscore(-df["danceability"].fillna(df["danceability"].median()).values)

    w = np.array([0.448, 0.364, 0.653])
    w /= w.sum()
    combined = w[0] * energy + w[1] * lufs + w[2] * neg_dance
    return 1.0 / (1.0 + np.exp(-combined * 1.5))   # → [0, 1]


def tune_blend_weight(mert: np.ndarray, proxy: np.ndarray,
                      df: pd.DataFrame) -> tuple[float, dict]:
    """Grid-search w* maximising Σ Spearman(blend_w, audio_proxy_j).

    All proxy signals are culture-neutral (energy, loudness_lufs, neg-danceability).
    Label-free and reproducible. Returns (w*, sensitivity_curve).
    """
    energy    = df["energy"].fillna(df["energy"].median()).values
    lufs      = df["loudness_lufs"].fillna(df["loudness_lufs"].median()).values
    neg_dance = -df["danceability"].fillna(df["danceability"].median()).values

    sensitivity = {}
    best_score, best_w = -np.inf, W_GRID[0]

    for w in W_GRID:
        blend = w * mert + (1.0 - w) * proxy
        r_e, _ = stats.spearmanr(blend, energy)
        r_l, _ = stats.spearmanr(blend, lufs)
        r_d, _ = stats.spearmanr(blend, neg_dance)
        score  = r_e + r_l + r_d
        sensitivity[round(float(w), 2)] = {
            "spearman_energy": round(float(r_e), 4),
            "spearman_lufs":   round(float(r_l), 4),
            "spearman_neg_dance": round(float(r_d), 4),
            "total_score":     round(float(score), 4),
        }
        if score > best_score:
            best_score, best_w = score, w

    return float(round(best_w, 2)), sensitivity


def quantile_map(source: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """CDF-to-CDF quantile mapping (Maraun 2013 J.Climate).

    Maps each value in source to the value in reference at the same empirical quantile.
    Preserves rank order of source; aligns full distribution (mean, std, skew, tails)
    to reference — NOT just mean and std as linear variance-expansion does.
    Extrapolation: clamp to reference [min, max].
    """
    ref_sorted = np.sort(reference)
    # Empirical quantile of each source value in the source distribution
    source_ranks = stats.rankdata(source) / (len(source) + 1)   # Hazen plotting position
    # Interpolate: quantile → reference value
    ref_quantiles = (np.arange(1, len(ref_sorted) + 1)) / (len(ref_sorted) + 1)
    mapped = np.interp(source_ranks, ref_quantiles, ref_sorted)
    return np.clip(mapped, ref_sorted.min(), ref_sorted.max())


def run():
    print("[recalibrate_arousal B3] Loading data...")
    df = pd.read_csv(cfg.PROCESSED_FILE,
                     usecols=["track_id", "energy", "loudness_lufs",
                               "danceability", "loudness"])
    df["track_id"] = df["track_id"].astype(str)
    n = len(df)

    mert_raw  = json.load(open("data/mert_arousal.json"))
    mert_arr  = np.array([float(mert_raw.get(tid, 0.475)) for tid in df["track_id"]])
    deam_ref  = load_deam_arousal()
    proxy_01  = build_proxy(df)

    print(f"  MERT arousal (raw): mean={mert_arr.mean():.3f}  std={mert_arr.std():.3f}")
    print(f"  DEAM reference:     mean={deam_ref.mean():.3f}  std={deam_ref.std():.3f}  n={len(deam_ref)}")

    # 1. Tune blend weight w* (label-free, Spearman vs audio proxies)
    print("\n[B3 step 1] Tuning blend weight w (MERT vs proxy)...")
    w_star, sensitivity = tune_blend_weight(mert_arr, proxy_01, df)
    print(f"  w* = {w_star}  (grid search over {[round(w,2) for w in W_GRID]})")
    print(f"  Sensitivity at w*: {sensitivity[w_star]}")
    print("  Top 5 w by total_score:")
    for w, v in sorted(sensitivity.items(), key=lambda x: -x[1]["total_score"])[:5]:
        print(f"    w={w}  score={v['total_score']:.4f}  "
              f"(energy={v['spearman_energy']:.3f}  lufs={v['spearman_lufs']:.3f}  "
              f"neg_dance={v['spearman_neg_dance']:.3f})")

    # 2. Compute optimally-blended arousal
    blend = w_star * mert_arr + (1.0 - w_star) * proxy_01
    print(f"\n[B3 step 2] Blend (w*={w_star}): mean={blend.mean():.3f}  std={blend.std():.3f}")

    # 3. Quantile-map blend → DEAM distribution (principled, CDF-to-CDF)
    arousal_v3 = quantile_map(blend, deam_ref)
    print(f"[B3 step 3] Quantile-mapped to DEAM:")
    print(f"  mean={arousal_v3.mean():.3f}  std={arousal_v3.std():.3f}  "
          f">0.7: {(arousal_v3>0.7).mean():.1%}  >0.6: {(arousal_v3>0.6).mean():.1%}")

    # Compare old Phase 1 (v2) vs new B3 (v3)
    v2_raw = json.load(open("data/arousal_v2.json"))
    v2_arr = np.array([float(v2_raw.get(tid, 0.5)) for tid in df["track_id"]])
    rho_v2v3, _ = stats.spearmanr(v2_arr, arousal_v3)
    print(f"\n  Spearman(v2, v3) = {rho_v2v3:.3f}  (ranking similarity vs Phase 1)")

    # 4. Save arousal_v3.json
    aro_dict = {str(df.iloc[i]["track_id"]): round(float(arousal_v3[i]), 4)
                for i in range(n)}
    json.dump(aro_dict, open(OUT_ARO, "w"), ensure_ascii=False)
    print(f"\n  Saved → {OUT_ARO}")

    # 5. Merge into v5c (v5 Gemini valence + B3 arousal)
    print("[B3] Merging with v5 Gemini labels → v5c...")
    v5 = json.load(open("data/emotion_labels_v5.json"))   # Gemini valence base

    from core.emotion_analysis import get_emotion_analyzer
    _, _, fusion = get_emotion_analyzer()

    out = {}
    for tid, new_aro in aro_dict.items():
        e = dict(v5.get(tid, {}))
        gem_v = float(e.get("valence", 0.5))
        label = fusion.get_emotion_label(gem_v, new_aro)
        e["arousal"] = new_aro
        e["label"]   = label
        e["src"]     = "gemini_v5c"
        out[tid] = e

    json.dump(out, open(OUT_LABELS, "w"), ensure_ascii=False)

    from collections import Counter
    dist = Counter(v.get("label") for v in out.values())
    vals = np.array([float(v5.get(tid, {}).get("valence", 0.5)) for tid in df["track_id"]])
    q = lambda v, a: ("Q1" if v>=0.5 and a>=0.5 else "Q2" if v<0.5 and a>=0.5
                      else "Q3" if v<0.5 and a<0.5 else "Q4")
    print(f"\n  Saved → {OUT_LABELS}")
    print("\n=== v5c label distribution ===")
    for lbl, cnt in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {lbl:15} {cnt:5}  ({cnt/len(out)*100:.1f}%)")
    q_counts = Counter(q(vals[i], arousal_v3[i]) for i in range(n))
    print(f"\n=== Quadrant distribution (v5c) vs (v5b) ===")
    v5b_aro = np.array([float(json.load(open('data/emotion_labels_v5b.json')).get(
        df.iloc[i]['track_id'],{}).get('arousal',0.5)) for i in range(n)])
    q5b = Counter(q(vals[i], v5b_aro[i]) for i in range(n))
    for quad in ['Q1','Q2','Q3','Q4']:
        print(f"  {quad}: {q_counts[quad]/n:.1%}  (v5b: {q5b[quad]/n:.1%})")

    # 6. Save sensitivity curve for reproducibility
    report = {
        "w_star": w_star, "w_grid": [round(w, 2) for w in W_GRID.tolist()],
        "sensitivity": sensitivity,
        "deam_reference": {"n": len(deam_ref), "mean": round(float(deam_ref.mean()), 4),
                           "std": round(float(deam_ref.std()), 4)},
        "v3_stats": {"mean": round(float(arousal_v3.mean()), 4),
                     "std": round(float(arousal_v3.std()), 4),
                     "pct_above_07": round(float((arousal_v3>0.7).mean()), 4)},
        "spearman_v2_v3": round(float(rho_v2v3), 4),
        "method": "quantile_map_CDF_to_DEAM (Maraun 2013)",
        "basis": "Blend weight tuned by Σ Spearman vs culture-neutral proxies; "
                 "distribution aligned to DEAM n=1802 via CDF mapping.",
    }
    os.makedirs("var/runtime/backtest/reports", exist_ok=True)
    json.dump(report, open("var/runtime/backtest/reports/arousal_b3_report.json", "w"),
              ensure_ascii=False, indent=2)
    print(f"\n  Sensitivity report → var/runtime/backtest/reports/arousal_b3_report.json")
    print(f"\nNext: python -m tools.validate_arousal v3")
    return w_star, arousal_v3


if __name__ == "__main__":
    run()
