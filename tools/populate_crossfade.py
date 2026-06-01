"""Populate Smart-Crossfade features into the processed CSV (2026-06-01).

These are all DSP / pyloudnorm (sample-rate-robust — NOT affected by the 16kHz EffNet
bug): loudness_lufs (ITU-R BS.1770), fade_out_cue_s, fade_in_cue_s, downbeat_times_json,
duration_s. Extraction functions already exist in extract_audio_features.py; this just
runs them over all mp3s and merges the columns. Resumable + multiprocessed.

Usage: python -m tools.populate_crossfade [workers]
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

MUSIC_DIR = Path("music_files")
CKPT = "data/crossfade_features.json"
COLS = ["loudness_lufs", "fade_out_cue_s", "fade_in_cue_s", "downbeat_times_json", "duration_s"]


def _one(tid: str):
    from tools.extract_audio_features import (
        _load_audio_safe, measure_lufs, _extract_cue_points_from_array, SAMPLE_RATE)
    mp3 = MUSIC_DIR / f"{tid}.mp3"
    if not mp3.exists():
        return tid, None
    audio = _load_audio_safe(mp3)
    if audio is None:
        return tid, None
    out = {"duration_s": round(len(audio) / SAMPLE_RATE, 2)}
    lufs = measure_lufs(audio, SAMPLE_RATE)
    if lufs is not None:
        out["loudness_lufs"] = lufs
    # is_danceable=True for ALL — danceability feature is degenerate, so don't gate
    # downbeat extraction on it; beat-matched crossfade is useful for any track.
    cue = _extract_cue_points_from_array(audio, SAMPLE_RATE, is_danceable=True)
    if cue:
        out.update(cue)
    return tid, out


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    workers = int(argv[0]) if argv else max(1, (os.cpu_count() or 4) - 2)

    df = pd.read_csv(cfg.PROCESSED_FILE)
    tids = df["track_id"].astype(str).tolist()

    results: dict = {}
    if os.path.exists(CKPT):
        results = json.load(open(CKPT))
        print(f"[crossfade] resuming — {len(results)} already done")
    todo = [t for t in tids if t not in results]
    print(f"[crossfade] {len(todo)} to process (of {len(tids)}), workers={workers}")

    import time
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, (tid, out) in enumerate(ex.map(_one, todo, chunksize=8), 1):
            results[tid] = out or {}
            if i % 100 == 0:
                json.dump(results, open(CKPT, "w"))
                eta = (time.time() - t0) / i * (len(todo) - i) / 60
                print(f"  {i}/{len(todo)}  ({(time.time()-t0)/i:.1f}s/song, ETA {eta:.0f} min)")
    json.dump(results, open(CKPT, "w"))

    # --- merge into CSV (backup first) ---
    bak = cfg.PROCESSED_FILE.replace(".csv", ".precrossfade.bak.csv")
    if not os.path.exists(bak):
        df.to_csv(bak, index=False)
        print(f"[crossfade] backup → {bak}")
    for col in COLS:
        df[col] = df["track_id"].astype(str).map(lambda t: results.get(t, {}).get(col))
    df.to_csv(cfg.PROCESSED_FILE, index=False)

    pop = {c: int(df[c].notna().sum()) for c in COLS}
    print(f"[crossfade] DONE — populated {pop} / {len(df)} → {cfg.PROCESSED_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
