"""Backfill reconciled duration_ms into the DB from data/clean_durations.csv.

Mirrors tools.backfill_vocal_regions: a portable CSV artifact → DB column. Idempotent
(re-running writes the same values). Run after `db.seed` in the deploy pipeline so the
production DB's `duration_ms` matches the ffprobe-reconciled local values — the catalog
CSV's `track_duration_ms` (what the seed loads) is stale, which throws off the crossfade
outro/regime decision (`tailA = duration − vocal_end`).

Usage:
    source .venv/bin/activate
    python -m tools.backfill_durations
    python -m tools.backfill_durations --csv data/clean_durations.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as cfg

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("backfill_durations")

DEFAULT_CSV = Path(cfg.CLEAN_DURATIONS_FILE)   # DATA_DIR-resolved → serving release in prod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    args = ap.parse_args()

    from db.engine import SessionLocal
    from db.models import Song

    csv_path = Path(args.csv)
    if not csv_path.exists():
        log.error(f"CSV not found: {csv_path} — run tools.export_clean_durations first.")
        return

    with csv_path.open() as f:
        records = list(csv.DictReader(f))
    log.info(f"Read {len(records)} rows from {csv_path}")

    session = SessionLocal()
    updated = 0
    for rec in records:
        tid = rec.get("track_id")
        raw = rec.get("duration_ms")
        if not tid or not raw:
            continue
        try:
            dur = int(float(raw))
        except ValueError:
            continue
        song = session.query(Song).filter(Song.track_id == tid).first()
        if song is None:
            continue
        song.duration_ms = dur
        updated += 1
        if updated % 500 == 0:
            session.commit()
            log.info(f"  committed {updated}")
    session.commit()
    session.close()
    log.info(f"Done. Updated={updated}")


if __name__ == "__main__":
    main()
