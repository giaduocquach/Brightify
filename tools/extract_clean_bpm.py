"""Clean BPM per song from librosa-derived downbeats (independent of the degenerate
Essentia-44.1kHz `tempo` column). Used to re-test the construct gate ρ(arousal, tempo),
which was failing partly because the Essentia tempo column is weak (ρ=0.44 vs this).

downbeat_times_json (in crossfade_features.json) are bar onsets (librosa). BPM is
estimated from the median inter-downbeat interval assuming 4 beats/bar:
    BPM = 4 * 60 / median_interval = 240 / median_interval
Robust to outliers via median; songs with <4 downbeats → NaN.

Run: python -m tools.extract_clean_bpm
"""
from __future__ import annotations
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

CF = "data/crossfade_features.json"
OUT = "data/clean_bpm.json"


def _bpm_from_downbeats(dbjson) -> float:
    try:
        db = json.loads(dbjson) if isinstance(dbjson, str) else dbjson
    except Exception:
        return float("nan")
    if not db or len(db) < 4:
        return float("nan")
    iv = np.diff(np.asarray(db, float))
    iv = iv[(iv > 0.1) & (iv < 8.0)]            # drop spurious gaps
    if len(iv) < 3:
        return float("nan")
    bpm = 240.0 / float(np.median(iv))          # 4 beats per bar
    # fold into a sane musical range
    while bpm < 60:  bpm *= 2
    while bpm > 200: bpm /= 2
    return round(bpm, 2)


def main() -> int:
    import pandas as pd
    from scipy.stats import spearmanr
    cf = json.load(open(CF))
    out = {}
    for tid, v in cf.items():
        if isinstance(v, dict) and v.get("downbeat_times_json"):
            b = _bpm_from_downbeats(v["downbeat_times_json"])
            if not np.isnan(b):
                out[str(tid)] = b
    json.dump(out, open(OUT, "w"))
    vals = np.array(list(out.values()))
    print(f"[clean-bpm] {len(out)} songs → {OUT}")
    print(f"  BPM: mean={vals.mean():.1f} std={vals.std():.1f} "
          f"p5={np.percentile(vals,5):.0f} p50={np.percentile(vals,50):.0f} p95={np.percentile(vals,95):.0f}")

    # sanity + the decisive correlations
    cat = pd.read_csv(cfg.PROCESSED_FILE)
    tids = cat["track_id"].astype(str).values
    clean = np.array([out.get(t, np.nan) for t in tids])
    ess = cat["tempo"].values.astype(float)
    mert_a = None
    try:
        ma = json.load(open("data/mert_arousal.json"))
        mert_a = np.array([ma.get(t, np.nan) for t in tids])
    except Exception:
        pass
    m = ~np.isnan(clean) & ~np.isnan(ess)
    print(f"  ρ(clean_bpm, essentia_tempo) = {spearmanr(clean[m], ess[m]).correlation:+.3f}  (n={m.sum()})")
    if mert_a is not None:
        m2 = ~np.isnan(clean) & ~np.isnan(mert_a)
        print(f"  ρ(MERT-arousal, clean_bpm)   = {spearmanr(mert_a[m2], clean[m2]).correlation:+.3f}  "
              f"(was −0.03 vs degenerate Essentia tempo; >0.20 = arousal tracks real tempo)")
        print(f"  ρ(MERT-arousal, essentia)    = {spearmanr(mert_a[m2], ess[m2]).correlation:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
