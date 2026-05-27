"""
Batch CLAP zero-shot emotion extraction (Pillar E).

Processes all songs in the processed CSV, predicts an emotion label via
core.clap_emotion.CLAPEmotionPredictor, and saves results to
data/clap_emotions.json (track_id → label string).

Supports resume: intermediate state is checkpointed every 50 songs to
data/clap_emotions_checkpoint.json.

Usage:
    python -m tools.extract_clap_emotions [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import pandas as pd
from loguru import logger

CSV_PATH = "data/vietnamese_music_processed_full.csv"
MUSIC_DIR = "music_files"
OUT_PATH = "data/clap_emotions.json"
CHECKPOINT_PATH = "data/clap_emotions_checkpoint.json"
CHECKPOINT_EVERY = 50


def _find_mp3(track_id: str) -> str | None:
    p = os.path.join(MUSIC_DIR, f"{track_id}.mp3")
    return p if os.path.exists(p) else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract CLAP emotion labels")
    parser.add_argument("--limit", type=int, default=None, help="Cap at N songs (for testing)")
    parser.add_argument("--no-resume", action="store_true", help="Restart from scratch")
    args = parser.parse_args()

    df = pd.read_csv(CSV_PATH)
    if args.limit:
        df = df.head(args.limit)
    n_total = len(df)
    logger.info(f"[CLAP] Processing {n_total} songs …")

    # Load checkpoint
    results: dict[str, str | None] = {}
    if not args.no_resume and os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH) as f:
            results = json.load(f)
        logger.info(f"[CLAP] Resumed: {len(results)} previously processed")

    from core.clap_emotion import get_clap_emotion_predictor
    predictor = get_clap_emotion_predictor()

    errors = 0
    t0 = time.time()

    for pos, (_, row) in enumerate(df.iterrows()):
        track_id = str(row.get("track_id", pos))
        if track_id in results:
            continue

        mp3 = _find_mp3(track_id)
        if mp3 is None:
            logger.warning(f"[CLAP] [{pos+1}/{n_total}] MP3 not found for {track_id}")
            results[track_id] = None
            errors += 1
            continue

        label = predictor.predict(mp3)
        results[track_id] = label

        done_count = len(results)
        if done_count % CHECKPOINT_EVERY == 0 or (pos + 1) == n_total:
            with open(CHECKPOINT_PATH, "w") as f:
                json.dump(results, f)
            elapsed = time.time() - t0
            n_labeled = sum(1 for v in results.values() if v is not None)
            rate = done_count / max(elapsed, 1.0)
            eta_s = (n_total - done_count) / max(rate, 1e-4)
            logger.info(
                f"[CLAP] [{done_count}/{n_total}] labeled={n_labeled} "
                f"errors={errors} | {rate:.1f} songs/s | ETA {eta_s/60:.0f}m"
            )

    # Final save
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    n_labeled = sum(1 for v in results.values() if v is not None)
    coverage = n_labeled / n_total * 100
    logger.info(
        f"[CLAP] Done: {n_labeled}/{n_total} ({coverage:.1f}%) labeled. "
        f"Saved → {OUT_PATH}"
    )

    # Print distribution
    from collections import Counter
    dist = Counter(v for v in results.values() if v)
    for label, count in dist.most_common():
        logger.info(f"  {label:12s}: {count:5d} ({count/n_total*100:.1f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
