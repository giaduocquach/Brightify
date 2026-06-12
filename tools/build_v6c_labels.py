"""Build emotion_labels_v6c.json — valence from the Vietnamese emotion lexicon.

Why v6c (2026-06-11): v6b valence was ~93% (by variance) the ENGLISH NRC-VAD
lexicon applied to Vietnamese lyrics — coverage 7.5%, mostly code-switched English
tokens. It correlated only ρ=0.14 with the trusted Gemini v5d valence and flipped
44% of songs' valence sign, which broke recommend-by-color's valence axis.

The project's own Vietnamese emotion lexicon (core.emotion_analysis) ACTUALLY reads
Vietnamese — its valence correlates ρ=0.445 with Gemini v5d (3× better than NRC-EN).
So v6c rebuilds valence ORDER from the VN lexicon, blended with MERT-audio valence
for songs (per MER literature valence still benefits from audio), then calibrates the
marginal to a healthy spread. No LLM is used; only the ORDER comes from VN-lexicon +
MERT. Arousal is inherited UNCHANGED from v6a (the fixed MERT-audio arousal).

Blend (in RANK space, so scale mismatches cannot leak in):
  v_score = w_lyr · rank(VN_lexicon_valence) + w_aud · rank(MERT_valence)   [has lyric signal]
          = rank(MERT_valence)                                             [no lyric signal]
  valence = affine_calibrate(rank(v_score)) → mean≈0.50, std≈0.18, clip[0,1]

Gates (vs v6b):
  corr(v6c_V, v5d_V) ≫ 0.198   (must recover agreement with the trusted reference)
  TE ≤ ~0.018 via tools.color_eval_rigor   (must not regress materially)
  r(V,A) reasonable (orthogonality is secondary to correctness — see V6 bug post-mortem)

Run: python -m tools.build_v6c_labels [--w-lyr 0.70] [--w-aud 0.30]
"""
import argparse
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.stats import rankdata, pearsonr

warnings.filterwarnings("ignore")

import config as cfg

V6A_PATH = "data/emotion_labels_v6a.json"          # arousal source (fixed MERT-audio)
MERT_V_PATH = "data/mert_valence.json"             # audio valence (all-layers probe)
V5D_PATH = "data/emotion_labels_v5d.json"          # Gemini reference — agreement check only
OUT_DEFAULT = "data/emotion_labels_v6c.json"

TARGET_V_MEAN = 0.50
TARGET_V_STD = 0.18


def _rank_norm(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Rank-normalise arr[mask] to uniform [0,1]; entries outside mask → NaN."""
    out = np.full(len(arr), np.nan)
    if mask.sum() > 1:
        out[mask] = (rankdata(arr[mask]) - 1) / (mask.sum() - 1)
    return out


def _calibrate(arr: np.ndarray) -> np.ndarray:
    """Affine-calibrate to TARGET_V_MEAN/STD (preserves rank order), clip [0,1]."""
    mu, sd = float(arr.mean()), float(arr.std()) + 1e-9
    cal = TARGET_V_MEAN + (arr - mu) / sd * TARGET_V_STD
    return np.clip(cal, 0.0, 1.0)


def _vn_lexicon_valence(tids, lyrics_lookup):
    """Per-song VN-lexicon valence + has-signal mask (lexical, no model needed)."""
    from core.emotion_analysis import get_emotion_analyzer

    lex, clf, _ = get_emotion_analyzer()
    vals = np.full(len(tids), np.nan)
    has_signal = np.zeros(len(tids), dtype=bool)
    for i, tid in enumerate(tids):
        lyr = lyrics_lookup.get(tid)
        if not lyr:
            continue
        scores = lex.analyze_lyrics(lyr)
        if sum(v for v in scores.values() if v > 0) <= 0:
            continue  # no emotion word matched → leave to audio
        v, _a = clf.emotions_to_valence_arousal(scores)
        vals[i] = float(v)
        has_signal[i] = True
    return vals, has_signal


def build(w_lyr: float = 1.0, w_aud: float = 0.0, out_path: str = OUT_DEFAULT) -> None:
    for path, name in [(V6A_PATH, "emotion_labels_v6a"), (MERT_V_PATH, "mert_valence")]:
        if not os.path.exists(path):
            print(f"[ERROR] missing {name}: {path}")
            sys.exit(1)

    v6a = json.load(open(V6A_PATH))
    mert_v = json.load(open(MERT_V_PATH))
    tids = list(v6a.keys())

    # Lyrics lookup
    df = pd.read_csv(cfg.PROCESSED_FILE)
    idc = next(c for c in ["track_id", "id", "song_id", "ID"] if c in df.columns)
    lyc = next(c for c in ["lyrics_cleaned", "lyrics", "lyric", "plain_lyrics"]
               if c in df.columns)
    lyrics_lookup = {
        str(r[idc]): str(r[lyc]) for _, r in df[[idc, lyc]].iterrows()
        if isinstance(r[lyc], str) and r[lyc].strip()
    }

    vn_val, has_lyr = _vn_lexicon_valence(tids, lyrics_lookup)
    mert_arr = np.array([float(mert_v.get(t, np.nan)) for t in tids])
    has_mert = ~np.isnan(mert_arr)

    # Rank-normalise each signal independently
    vn_rank = _rank_norm(vn_val, has_lyr)
    mert_rank = _rank_norm(mert_arr, has_mert)

    # Blend in rank space (audio-only fallback when no lyric signal)
    total = w_lyr + w_aud
    blended = np.full(len(tids), np.nan)
    both = has_lyr & has_mert
    blended[both] = (w_lyr * vn_rank[both] + w_aud * mert_rank[both]) / total
    only_lyr = has_lyr & ~has_mert
    blended[only_lyr] = vn_rank[only_lyr]
    only_mert = ~has_lyr & has_mert
    blended[only_mert] = mert_rank[only_mert]
    # neither → neutral
    blended[np.isnan(blended)] = 0.5

    # Final rank-norm + affine calibrate to healthy spread
    final_rank = (rankdata(blended) - 1) / (len(blended) - 1)
    valence = _calibrate(final_rank)

    out = {}
    for i, tid in enumerate(tids):
        entry = v6a[tid]
        out[tid] = {
            "valence": round(float(valence[i]), 4),
            "arousal": entry.get("arousal"),          # fixed MERT-audio arousal
            "label": entry.get("label"),
            "valence_vnlex": None if np.isnan(vn_val[i]) else round(float(vn_val[i]), 4),
            "valence_mert": None if np.isnan(mert_arr[i]) else round(float(mert_arr[i]), 4),
            "src": f"v6c_vnlex{int(w_lyr * 100)}_mert{int(w_aud * 100)}",
        }
    json.dump(out, open(out_path, "w"), ensure_ascii=False)

    # ---- Report + gates ----
    val_all = np.array([out[t]["valence"] for t in tids])
    aro_all = np.array([out[t]["arousal"] for t in tids
                        if out[t]["arousal"] is not None])
    r_va, _ = pearsonr(
        [out[t]["valence"] for t in tids if out[t]["arousal"] is not None],
        [out[t]["arousal"] for t in tids if out[t]["arousal"] is not None],
    )
    v5d = json.load(open(V5D_PATH)) if os.path.exists(V5D_PATH) else {}
    g = np.array([v5d.get(t, {}).get("valence", np.nan)
                  if isinstance(v5d.get(t), dict) else np.nan for t in tids])
    m = ~np.isnan(g)
    r_ref = np.corrcoef(val_all[m], g[m])[0, 1] if m.sum() > 10 else float("nan")

    print(f"[build_v6c] {len(out)} songs → {out_path}")
    print(f"  lyric signal: {int(has_lyr.sum())}/{len(tids)} songs "
          f"({100 * has_lyr.mean():.1f}%); audio-only fallback: {int(only_mert.sum())}")
    print(f"  V distribution: mean={val_all.mean():.3f} std={val_all.std():.3f} "
          f"p5={np.percentile(val_all, 5):.3f} p95={np.percentile(val_all, 95):.3f}")
    print(f"  corr(v6c_V, v5d/Gemini) = {r_ref:+.3f}   (v6b was +0.198 — must improve)")
    print(f"  r(V, A) = {r_va:+.4f}")
    print(f"\n  Next: python -m tools.color_eval_rigor --emotions-file {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--w-lyr", type=float, default=1.0)
    ap.add_argument("--w-aud", type=float, default=0.0)
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args()
    build(w_lyr=args.w_lyr, w_aud=args.w_aud, out_path=args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
