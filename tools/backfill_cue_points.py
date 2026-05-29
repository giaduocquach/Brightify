"""Backfill crossfade cue points + downbeats for all songs with a local MP3.

Computes via tools.extract_cue_points (librosa structural segmentation +
beat tracking). Writes to Song.fade_out_cue_s, Song.fade_in_cue_s, and
Song.downbeat_times_json (the latter only for danceable tracks).

Usage:
    source .venv/bin/activate
    python -m tools.backfill_cue_points
    python -m tools.backfill_cue_points --limit 100
    python -m tools.backfill_cue_points --force
    python -m tools.backfill_cue_points --workers 4
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.engine import SessionLocal
from db.models import Song
from tools.extract_cue_points import extract_cue_points

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("backfill_cue_points")

MUSIC_DIR = ROOT / "music_files"
DANCEABILITY_THRESHOLD = 0.7


def _resolve_mp3(track_id: str, mp3_path: str | None) -> str | None:
    if mp3_path and os.path.isabs(mp3_path) and os.path.exists(mp3_path):
        return mp3_path
    default = MUSIC_DIR / f"{track_id}.mp3"
    if default.exists():
        return str(default)
    if mp3_path:
        rel = ROOT / mp3_path
        if rel.exists():
            return str(rel)
    return None


def _process_one(track_id: str, mp3_path: str | None, is_danceable: bool):
    """Worker: returns (track_id, result_dict or None, error_str or None)."""
    mp3 = _resolve_mp3(track_id, mp3_path)
    if not mp3:
        return track_id, None, "mp3_missing"
    result = extract_cue_points(mp3, is_danceable=is_danceable)
    return track_id, result, None if result else "extract_fail"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    session = SessionLocal()
    q = session.query(Song.track_id, Song.mp3_path, Song.danceability).filter(Song.has_mp3.is_(True))
    if not args.force:
        q = q.filter(Song.fade_out_cue_s.is_(None))
    if args.limit:
        q = q.limit(args.limit)
    rows = q.all()
    session.close()

    total = len(rows)
    if total == 0:
        log.info("Nothing to backfill — all songs already have cue points.")
        return

    log.info(f"Extracting cue points for {total} songs with {args.workers} worker(s)...")
    payload = [(tid, mp3, bool(d and d >= DANCEABILITY_THRESHOLD)) for tid, mp3, d in rows]

    results = []
    if args.workers <= 1:
        for i, (tid, mp3, dance) in enumerate(payload):
            results.append(_process_one(tid, mp3, dance))
            if (i + 1) % 25 == 0:
                log.info(f"  processed {i+1}/{total}")
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(_process_one, tid, mp3, dance): tid for tid, mp3, dance in payload}
            done = 0
            for fut in as_completed(futures):
                results.append(fut.result())
                done += 1
                if done % 25 == 0:
                    log.info(f"  processed {done}/{total}")

    session = SessionLocal()
    updated = 0
    with_downbeats = 0
    errors: dict[str, int] = {}
    for tid, data, err in results:
        if not data:
            errors[err or "unknown"] = errors.get(err or "unknown", 0) + 1
            continue
        song = session.query(Song).filter(Song.track_id == tid).first()
        if song is None:
            continue
        song.fade_out_cue_s = data["fade_out_cue_s"]
        song.fade_in_cue_s = data["fade_in_cue_s"]
        if data.get("downbeat_times_json"):
            song.downbeat_times_json = data["downbeat_times_json"]
            with_downbeats += 1
        updated += 1
        if updated % 50 == 0:
            session.commit()
            log.info(f"  committed {updated} updates")
    session.commit()
    session.close()

    log.info(f"Done. Updated={updated} (downbeats on {with_downbeats}) Errors={errors}")


if __name__ == "__main__":
    main()
