"""Build emotion_labels_v6a.json — Phase 1: arousal from audio, valence unchanged.

V6a formula:
  A = 0.80 * MERT_arousal_probe(audio, DEAM)  [data/mert_arousal.json]
    + 0.20 * NRC-VAD_arousal(lyrics)           [var/data/nrc_vad_lexicon.txt]
  V = v5d valence (unchanged — still Gemini-blend for now)

If NRC-VAD arousal is NaN for a song: fall back to 100% MERT arousal.

Gates (printed, not enforced here — run color_eval_rigor.py to check):
  TE  ≤ 0.0245   (must not regress from v5d)
  r(V,A) < 0.20  (arousal should decouple from valence; v5d = 0.313)

Run: python -m tools.build_v6a_labels [--w-mert 0.80] [--out data/emotion_labels_v6a.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg
from tools.nrc_vad_score import load_nrc_vad, score_lyrics

W_MERT_DEFAULT = 0.80
MERT_AROUSAL_PATH = "data/mert_arousal.json"
OUT_DEFAULT = "data/emotion_labels_v6a.json"
# DEAM arousal distribution after normalization to [0,1] (1..9 → 0..1)
DEAM_AROUSAL_MEAN = 0.48
DEAM_AROUSAL_STD  = 0.16


def _calibrate_to_deam(arr: np.ndarray) -> np.ndarray:
    """Scale predictions to match DEAM arousal distribution (mean=0.48, std=0.16).

    MERT probe regresses to the mean (predictions std≈0.07 vs DEAM 0.16).
    This preserves rank ordering while restoring realistic spread.
    """
    mu, sd = float(arr.mean()), float(arr.std()) + 1e-9
    calibrated = mu + (arr - mu) / sd * DEAM_AROUSAL_STD
    # Shift mean toward DEAM target while keeping relative ordering
    calibrated += DEAM_AROUSAL_MEAN - calibrated.mean()
    return np.clip(calibrated, 0.0, 1.0)


def build(w_mert: float = W_MERT_DEFAULT, out_path: str = OUT_DEFAULT,
          calibrate: bool = True) -> None:
    if not os.path.exists(MERT_AROUSAL_PATH):
        print(f"[ERROR] {MERT_AROUSAL_PATH} not found.")
        print("  Run: python -m tools.mert_arousal_probe train")
        sys.exit(1)

    base_path = cfg.RELABELED_EMOTIONS_FILE
    if not os.path.exists(base_path):
        print(f"[ERROR] Base labels not found: {base_path}")
        sys.exit(1)

    mert_arousal_raw: dict[str, float] = json.load(open(MERT_AROUSAL_PATH))
    base_labels: dict = json.load(open(base_path))
    lexicon = load_nrc_vad()

    # Calibrate MERT arousal to match DEAM distribution
    if calibrate:
        vals = np.array(list(mert_arousal_raw.values()), dtype=float)
        calibrated_vals = _calibrate_to_deam(vals)
        mert_arousal = {k: float(v) for k, v in zip(mert_arousal_raw.keys(), calibrated_vals)}
        print(f"[build_v6a] MERT arousal calibrated: "
              f"std {vals.std():.3f}→{calibrated_vals.std():.3f}, "
              f"mean {vals.mean():.3f}→{calibrated_vals.mean():.3f}")
    else:
        mert_arousal = mert_arousal_raw

    lyrics_lookup: dict[str, str] = {}
    if lexicon:
        import pandas as pd
        df = pd.read_csv(cfg.PROCESSED_FILE)
        id_col = next(
            (c for c in ["track_id", "id", "song_id", "ID"] if c in df.columns), None
        )
        lyr_col = next(
            (c for c in ["lyrics", "lyrics_cleaned", "lyrics_clean", "lyric", "plain_lyrics"]
             if c in df.columns),
            None,
        )
        if id_col and lyr_col:
            lyrics_lookup = {
                str(row[id_col]): str(row[lyr_col])
                for _, row in df[[id_col, lyr_col]].iterrows()
                if row[lyr_col] == row[lyr_col]
            }

    n_mert_only = 0
    n_blended = 0
    out: dict = {}

    for tid, entry in base_labels.items():
        mert_a = mert_arousal.get(tid)
        if mert_a is None:
            out[tid] = {**entry, "src": "v6a_no_mert"}
            continue

        nrc_a = float("nan")
        if lexicon and tid in lyrics_lookup:
            nrc_a = score_lyrics(lyrics_lookup[tid], lexicon, dim="arousal")

        if np.isnan(nrc_a):
            arousal = float(mert_a)
            n_mert_only += 1
        else:
            # NRC-VAD lexicon is bipolar [-1,1] (neutral=0); MERT arousal is [0,1]
            # (neutral=0.5). Rescale NRC to [0,1] BEFORE blending so both signals
            # share a scale — else the 0.20 lyrics term drags arousal down ~0.12 and
            # collapses the catalog's high-arousal region (recommend-by-color bug).
            nrc_a01 = (float(nrc_a) + 1.0) / 2.0
            arousal = w_mert * float(mert_a) + (1 - w_mert) * nrc_a01
            n_blended += 1

        # Both terms now in [0,1]; clip guards float edges only.
        arousal = round(float(np.clip(arousal, 0.0, 1.0)), 4)

        out[tid] = {
            "valence": entry.get("valence"),
            "arousal": arousal,
            "label": entry.get("label"),
            "arousal_mert": round(float(mert_a), 4),
            "arousal_nrc": None if np.isnan(nrc_a) else round(float(nrc_a), 4),
            "src": "v6a_mert80_nrc20",
        }

    json.dump(out, open(out_path, "w"), ensure_ascii=False)

    arousal_vals = np.array([v["arousal"] for v in out.values() if v.get("arousal") is not None])
    valence_vals = np.array([v["valence"] for v in out.values() if v.get("valence") is not None])

    print(f"[build_v6a] {len(out)} songs → {out_path}")
    print(f"  A source: blended={n_blended}, mert_only={n_mert_only}")
    print(f"  A distribution: mean={arousal_vals.mean():.3f}  std={arousal_vals.std():.3f}")

    if len(valence_vals) > 10 and len(arousal_vals) > 10:
        from scipy.stats import pearsonr
        # Align arrays (same keys)
        v_arr = np.array([out[t]["valence"] for t in out
                          if out[t].get("valence") is not None and out[t].get("arousal") is not None])
        a_arr = np.array([out[t]["arousal"] for t in out
                          if out[t].get("valence") is not None and out[t].get("arousal") is not None])
        r_va, _ = pearsonr(v_arr, a_arr)
        print(f"  r(V, A) = {r_va:+.4f}  (target <0.20; v5d baseline = 0.313)")
        if abs(r_va) < 0.20:
            print(f"  ✓ V-A orthogonality improved")
        else:
            print(f"  ✗ r(V,A) still high — investigate valence entanglement")

    print(f"\n  Next: python -m tools.color_eval_rigor --emotions-file {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--w-mert", type=float, default=W_MERT_DEFAULT,
                    help="Weight for MERT arousal (1-w goes to NRC-VAD; default 0.80)")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--no-calibrate", action="store_true",
                    help="Skip DEAM distribution calibration (keep raw MERT predictions)")
    args = ap.parse_args()
    build(w_mert=args.w_mert, out_path=args.out, calibrate=not args.no_calibrate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
