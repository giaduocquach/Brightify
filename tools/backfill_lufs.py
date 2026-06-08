"""Backfill integrated LUFS for all existing songs that have a local MP3.

Reads from music_files/{track_id}.mp3, runs pyloudnorm ITU-R BS.1770 meter,
writes Song.loudness_lufs.

Usage:
    source .venv/bin/activate
    python -m tools.backfill_lufs                 # process all unfilled
    python -m tools.backfill_lufs --limit 50      # cap for smoke testing
    python -m tools.backfill_lufs --force         # re-measure even if value exists
    python -m tools.backfill_lufs --workers 4     # parallel processes

Notes:
- Skips songs where MP3 file is missing on disk.
- Skips songs whose integrated loudness is outside [-70, 0] (silence / clip-bombs).
- Commits every 50 songs so a crash doesn't lose all progress.
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

# Ensure project root is on path when invoked as a script
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as cfg
from db.engine import SessionLocal
from db.models import Song

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("backfill_lufs")

MUSIC_DIR = cfg.MUSIC_DIR


def _measure_one(track_id: str) -> tuple[str, float | None, str | None]:
    """Return (track_id, lufs, error). lufs is None on failure."""
    try:
        import librosa
        import pyloudnorm as pyln
    except ImportError as e:
        return track_id, None, f"import_fail:{e}"

    # Resolve mp3 path
    candidate = None
    default = MUSIC_DIR / f"{track_id}.mp3"
    if default.exists():
        candidate = str(default)

    if not candidate:
        return track_id, None, "mp3_missing"

    try:
        audio, sr = librosa.load(candidate, sr=None, mono=True)
        if audio is None or len(audio) < int(0.5 * sr):
            return track_id, None, "too_short"
        meter = pyln.Meter(sr)
        loudness = float(meter.integrated_loudness(audio))
        if not np.isfinite(loudness) or loudness < -70 or loudness > 0:
            return track_id, None, f"out_of_range:{loudness:.2f}"
        return track_id, round(loudness, 2), None
    except Exception as e:
        return track_id, None, f"measure_fail:{e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap number of songs (0 = all)")
    ap.add_argument("--workers", type=int, default=1, help="parallel processes")
    ap.add_argument("--force", action="store_true", help="re-measure even if value exists")
    args = ap.parse_args()

    session = SessionLocal()
    q = session.query(Song.track_id).filter(Song.has_mp3.is_(True))
    if not args.force:
        q = q.filter(Song.loudness_lufs.is_(None))
    if args.limit:
        q = q.limit(args.limit)
    rows = q.all()
    session.close()

    total = len(rows)
    if total == 0:
        log.info("Nothing to backfill — all songs already have loudness_lufs.")
        return

    log.info(f"Backfilling LUFS for {total} songs with {args.workers} worker(s)...")

    results: list[tuple[str, float | None, str | None]] = []
    if args.workers <= 1:
        for i, (tid,) in enumerate(rows):
            results.append(_measure_one(tid))
            if (i + 1) % 25 == 0:
                log.info(f"  measured {i+1}/{total}")
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(_measure_one, tid): tid for (tid,) in rows}
            done = 0
            for fut in as_completed(futures):
                results.append(fut.result())
                done += 1
                if done % 25 == 0:
                    log.info(f"  measured {done}/{total}")

    # Bulk update — commit in batches of 50
    session = SessionLocal()
    updated = 0
    skipped = 0
    error_counts: dict[str, int] = {}
    for i, (tid, lufs, err) in enumerate(results):
        if lufs is None:
            skipped += 1
            key = (err or "unknown").split(":")[0]
            error_counts[key] = error_counts.get(key, 0) + 1
            continue
        song = session.query(Song).filter(Song.track_id == tid).first()
        if song is not None:
            song.loudness_lufs = lufs
            updated += 1
            if updated % 50 == 0:
                session.commit()
                log.info(f"  committed {updated} updates")
    session.commit()
    session.close()

    log.info(f"Done. Updated={updated}  Skipped={skipped}  Total={total}")
    if error_counts:
        log.info(f"Skip reasons: {error_counts}")


if __name__ == "__main__":
    main()
