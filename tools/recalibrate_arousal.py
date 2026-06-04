"""Phase 1 — Recalibrate MERT-arousal: proxy-anchor + blend + variance expansion.

Root cause: Ridge probe (DEAM→Vietnamese) compresses variance via domain-shift
shrinkage (Hu&Yang 2017 IEEE TAC). Result: mean=0.475, std=0.095, gym=0.461.

Fix (Flow-1 research 2026-06-04, doc COLOR_NO_HUMAN_IMPROVEMENT_PLAN_V20.md):
  1. Proxy-arousal (label-free) from culture-neutral Essentia audio features:
     energy(+0.448), loudness_lufs(+0.364), -danceability(-0.653 → negated).
     Schubert 2004 / Gabrielsson&Lindström 2001: loudness+tempo drive arousal
     cross-culturally. danceability negated = rhythmic-complexity proxy.
  2. Blend: 0.65·MERT + 0.35·proxy  → corrects per-song ranking.
  3. Variance expansion: rescale blend → std≈0.18 (double current MERT std 0.09)
     → restores plausible cross-corpus range (DEAM/PMEmo std ~0.20).

IMPORTANT: quantile-expansion is monotone → Spearman ranking unchanged from
blend; it only fixes the absolute scale needed for colour-V-A RBF distance.

Outputs: data/arousal_v2.json   (tid→arousal float 0-1)
         data/emotion_labels_v5b.json  (v5 valence + recalibrated arousal)
Config update: RELABELED_EMOTIONS_FILE → v5b after validation.

Run: python -m tools.recalibrate_arousal
Gate: python -m tools.validate_arousal
"""
import json, os, sys
import numpy as np
import pandas as pd
from scipy import stats
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

OUT_ARO   = "data/arousal_v2.json"
OUT_LABELS = "data/emotion_labels_v5b.json"

# Blend weights (MERT vs proxy) — MERT carries semantic info, proxy fixes scale
W_MERT  = 0.65
W_PROXY = 0.35

# Target std for variance expansion (plausible cross-corpus arousal range)
# DEAM/PMEmo std ~0.20; current MERT std ~0.095. Target = 2× current.
TARGET_STD  = 0.18
TARGET_MEAN = 0.50   # centre at neutral; let data float around here


def build_proxy(df: pd.DataFrame) -> np.ndarray:
    """Label-free audio-arousal proxy from Essentia features.

    Feature selection based on Spearman(feature, MERT-arousal) on catalog:
      energy       rho=+0.448  (Schubert 2004: energy = arousal driver)
      loudness_lufs rho=+0.364  (LUFS normalised loudness)
      -danceability rho=+0.653  (negated: high danceability=clear slow beat=ballad=low arousal)

    Each z-scored independently, then weighted sum → z-score of combined.
    """
    def zscore(x: np.ndarray) -> np.ndarray:
        s = x.std()
        return (x - x.mean()) / s if s > 1e-9 else np.zeros_like(x)

    energy    = zscore(df['energy'].fillna(df['energy'].median()).values)
    lufs      = zscore(df['loudness_lufs'].fillna(df['loudness_lufs'].median()).values)
    neg_dance = zscore(-df['danceability'].fillna(df['danceability'].median()).values)

    # Weight proportional to |Spearman| with MERT-arousal
    # energy 0.448, lufs 0.364, neg_dance 0.653 → normalise
    w = np.array([0.448, 0.364, 0.653])
    w = w / w.sum()
    combined = w[0] * energy + w[1] * lufs + w[2] * neg_dance
    # Return as z-score [no clipping yet — done after blend]
    return combined


def variance_expand(arr: np.ndarray, target_mean: float, target_std: float) -> np.ndarray:
    """Expand variance to target_std while keeping ranking (monotone transform).
    Clips to [0.05, 0.95] to stay in valid range.
    """
    cur_mean = arr.mean()
    cur_std  = arr.std()
    if cur_std < 1e-9:
        return np.full_like(arr, target_mean)
    expanded = (arr - cur_mean) / cur_std * target_std + target_mean
    return np.clip(expanded, 0.05, 0.95)


def run():
    print("[recalibrate_arousal] Loading data...")
    df = pd.read_csv(cfg.PROCESSED_FILE,
                     usecols=['track_id', 'energy', 'loudness_lufs',
                               'danceability', 'loudness'])
    df['track_id'] = df['track_id'].astype(str)
    n = len(df)
    print(f"  Catalog: {n} songs")

    # Load MERT arousal (current)
    mert_raw = json.load(open('data/mert_arousal.json'))
    mert_arr = np.array([float(mert_raw.get(tid, 0.475))
                         for tid in df['track_id']])
    print(f"  MERT arousal: mean={mert_arr.mean():.3f}  std={mert_arr.std():.3f}  "
          f">0.7: {(mert_arr>0.7).mean():.1%}")

    # 1. Build proxy
    proxy_z = build_proxy(df)
    # Map proxy_z → [0,1] roughly using sigmoid-like scaling
    proxy_01 = 1 / (1 + np.exp(-proxy_z * 1.5))
    print(f"  Proxy arousal: mean={proxy_01.mean():.3f}  std={proxy_01.std():.3f}  "
          f">0.7: {(proxy_01>0.7).mean():.1%}")

    # 2. Blend MERT + proxy
    blend = W_MERT * mert_arr + W_PROXY * proxy_01
    print(f"  Blend ({W_MERT}/{W_PROXY}): mean={blend.mean():.3f}  std={blend.std():.3f}  "
          f">0.7: {(blend>0.7).mean():.1%}")

    # 3. Variance expansion to plausible cross-corpus range
    arousal_v2 = variance_expand(blend, TARGET_MEAN, TARGET_STD)
    print(f"  Arousal v2:  mean={arousal_v2.mean():.3f}  std={arousal_v2.std():.3f}  "
          f">0.7: {(arousal_v2>0.7).mean():.1%}")

    # Spearman check vs proxy (should be high positive)
    rho_proxy, _ = stats.spearmanr(proxy_01, arousal_v2)
    rho_mert,  _ = stats.spearmanr(mert_arr, arousal_v2)
    print(f"\n  Spearman(proxy, v2)={rho_proxy:.3f}  Spearman(mert, v2)={rho_mert:.3f}")

    # 4. Save arousal_v2.json
    aro_dict = {str(df.iloc[i]['track_id']): round(float(arousal_v2[i]), 4)
                for i in range(n)}
    json.dump(aro_dict, open(OUT_ARO, 'w'), ensure_ascii=False)
    print(f"\n  Saved arousal_v2 → {OUT_ARO}")

    # 5. Merge into v5b labels (valence from Gemini v5, arousal from v2)
    print("[recalibrate_arousal] Merging with v5 Gemini labels → v5b...")
    v5 = json.load(open(cfg.RELABELED_EMOTIONS_FILE))  # v5

    from core.emotion_analysis import get_emotion_analyzer
    _, _, fusion = get_emotion_analyzer()

    out = {}
    for tid, new_aro in aro_dict.items():
        e = dict(v5.get(tid, {}))
        gem_v = float(e.get('valence', 0.5))
        label = fusion.get_emotion_label(gem_v, new_aro)
        e['arousal'] = new_aro
        e['label']   = label
        e['src']     = 'gemini_v5b'
        out[tid] = e

    json.dump(out, open(OUT_LABELS, 'w'), ensure_ascii=False)

    # Distribution report
    from collections import Counter
    labels = [v.get('label') for v in out.values()]
    dist = Counter(labels)
    print(f"\n  Saved v5b labels → {OUT_LABELS}")
    print("\n=== v5b label distribution ===")
    for lbl, cnt in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {lbl:15} {cnt:5}  ({cnt/len(labels)*100:.1f}%)")

    # Quadrant breakdown
    aros = arousal_v2
    vals = np.array([float(v5.get(tid,{}).get('valence',0.5)) for tid in df['track_id']])
    q1 = ((vals>=0.5)&(aros>=0.5)).mean()
    q2 = ((vals<0.5) &(aros>=0.5)).mean()
    q3 = ((vals<0.5) &(aros<0.5)).mean()
    q4 = ((vals>=0.5)&(aros<0.5)).mean()
    print(f"\n=== Quadrant distribution (v5b) ===")
    print(f"  Q1 happy/excited: {q1:.1%}  (was {((vals>=0.5)&(mert_arr>=0.5)).mean():.1%})")
    print(f"  Q2 tense/angry:   {q2:.1%}  (was {((vals<0.5) &(mert_arr>=0.5)).mean():.1%})")
    print(f"  Q3 sad/depressed: {q3:.1%}  (was {((vals<0.5) &(mert_arr<0.5)).mean():.1%})")
    print(f"  Q4 calm/peaceful: {q4:.1%}  (was {((vals>=0.5)&(mert_arr<0.5)).mean():.1%})")
    print(f"\nNext: python -m tools.validate_arousal")


if __name__ == "__main__":
    run()
