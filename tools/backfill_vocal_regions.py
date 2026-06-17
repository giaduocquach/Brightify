"""Backfill vocal regions into the DB (Smart Crossfade Tier 3).

Reads data/vocal_regions.csv (produced by tools.extract_vocal_regions, which may
have been run on a GPU box) and writes Song.vocal_start_s / Song.vocal_end_s.
Pure-instrumental tracks have empty cells → stored as NULL (graceful fallback).

Usage:
    source .venv/bin/activate
    python -m tools.backfill_vocal_regions
    python -m tools.backfill_vocal_regions --csv data/vocal_regions.csv
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("backfill_vocal_regions")

DEFAULT_CSV = ROOT / "data" / "vocal_regions.csv"


def _to_float(s: str | None) -> float | None:
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    args = ap.parse_args()

    from db.engine import SessionLocal
    from db.models import Song

    csv_path = Path(args.csv)
    if not csv_path.exists():
        log.error(f"CSV not found: {csv_path} — run tools.extract_vocal_regions first.")
        return

    with csv_path.open() as f:
        records = list(csv.DictReader(f))
    log.info(f"Read {len(records)} rows from {csv_path}")

    session = SessionLocal()
    updated = 0
    for rec in records:
        tid = rec.get("track_id")
        if not tid:
            continue
        song = session.query(Song).filter(Song.track_id == tid).first()
        if song is None:
            continue
        song.vocal_start_s = _to_float(rec.get("vocal_start_s"))
        song.vocal_end_s = _to_float(rec.get("vocal_end_s"))
        updated += 1
        if updated % 50 == 0:
            session.commit()
            log.info(f"  committed {updated}")
    session.commit()
    session.close()
    log.info(f"Done. Updated={updated}")


if __name__ == "__main__":
    main()
