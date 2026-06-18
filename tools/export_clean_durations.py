"""Export reconciled per-track duration (ms) → data/clean_durations.csv.

The DB's `duration_ms` has been reconciled to the real audio length (ffprobe); the
catalog CSV's `track_duration_ms` is the stale metadata value. Production can't
ffprobe (audio lives on the CDN, not local disk), so we ship the reconciled
durations as a portable artifact and apply them with `tools.backfill_durations`
after the DB seed — mirroring how `vocal_regions.csv` feeds the vocal backfill.

Usage:
    source .venv/bin/activate
    python -m tools.export_clean_durations
"""

from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as cfg

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("export_clean_durations")

OUT_CSV = Path(cfg.CLEAN_DURATIONS_FILE)   # DATA_DIR/clean_durations.csv (repo data/ locally)


def main():
    from db.engine import SessionLocal
    from db.models import Song

    session = SessionLocal()
    rows = session.query(Song.track_id, Song.duration_ms).filter(Song.duration_ms.isnot(None)).all()
    session.close()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["track_id", "duration_ms"])
        for tid, dur in rows:
            if tid and dur:
                writer.writerow([tid, int(dur)])
                written += 1
    log.info(f"Wrote {written} rows → {OUT_CSV}")


if __name__ == "__main__":
    main()
