#!/usr/bin/env python3
"""Synchronize PostgreSQL songs with the canonical filtered catalog."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import inspect

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.engine import SessionLocal
from db.models import Song, SongArtist, SongEmbedding
from db.seed import run_seed


CATALOG_PATH = PROJECT_ROOT / "data" / "vietnamese_music_processed_full.csv"
BATCH_SIZE = 500


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _serialize_rows(rows) -> list[dict]:
    serialized = []
    for row in rows:
        values = {}
        for attribute in inspect(row.__class__).mapper.column_attrs:
            values[attribute.key] = _json_value(getattr(row, attribute.key))
        serialized.append(values)
    return serialized


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _batches(values: list[str]):
    for index in range(0, len(values), BATCH_SIZE):
        yield values[index:index + BATCH_SIZE]


def _catalog_ids() -> list[str]:
    df = pd.read_csv(CATALOG_PATH, usecols=["track_id"])
    ids = df["track_id"].astype(str).tolist()
    if len(ids) != len(set(ids)):
        raise ValueError("Canonical catalog contains duplicate track IDs")
    return ids


def inspect_database() -> tuple[list[str], list[str], int]:
    catalog_ids = _catalog_ids()
    catalog_set = set(catalog_ids)
    session = SessionLocal()
    try:
        database_ids = [str(track_id) for (track_id,) in session.query(Song.track_id).all()]
    finally:
        session.close()

    database_set = set(database_ids)
    stale_ids = sorted(database_set - catalog_set)
    missing_ids = sorted(catalog_set - database_set)
    return stale_ids, missing_ids, len(database_ids)


def _backup_stale_rows(backup_dir: Path, stale_ids: list[str]) -> None:
    database_dir = backup_dir / "database"
    database_dir.mkdir(parents=True, exist_ok=True)

    session = SessionLocal()
    try:
        songs = []
        song_artists = []
        embedding_ids = []
        for batch in _batches(stale_ids):
            songs.extend(session.query(Song).filter(Song.track_id.in_(batch)).all())
            song_artists.extend(
                session.query(SongArtist).filter(SongArtist.track_id.in_(batch)).all()
            )
            embedding_ids.extend(
                str(track_id)
                for (track_id,) in session.query(SongEmbedding.track_id)
                .filter(SongEmbedding.track_id.in_(batch))
                .all()
            )

        _write_json(database_dir / "songs.json", _serialize_rows(songs))
        _write_json(database_dir / "song_artists.json", _serialize_rows(song_artists))
        _write_json(database_dir / "song_embedding_ids.json", embedding_ids)
    finally:
        session.close()


def _purge_stale_rows(stale_ids: list[str]) -> dict[str, int]:
    counts = {
        "song_embeddings": 0,
        "song_artists": 0,
        "songs": 0,
    }
    session = SessionLocal()
    try:
        for batch in _batches(stale_ids):
            counts["song_embeddings"] += (
                session.query(SongEmbedding)
                .filter(SongEmbedding.track_id.in_(batch))
                .delete(synchronize_session=False)
            )
            counts["song_artists"] += (
                session.query(SongArtist)
                .filter(SongArtist.track_id.in_(batch))
                .delete(synchronize_session=False)
            )
            counts["songs"] += (
                session.query(Song)
                .filter(Song.track_id.in_(batch))
                .delete(synchronize_session=False)
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return counts


def sync_database(backup_dir: Path) -> None:
    stale_ids, missing_ids, database_count = inspect_database()
    print(f"Database songs: {database_count:,}")
    print(f"Stale songs: {len(stale_ids):,}")
    print(f"Missing songs: {len(missing_ids):,}")

    if stale_ids:
        _backup_stale_rows(backup_dir, stale_ids)

    # Upsert current rows before deleting stale rows. A seed failure therefore
    # leaves the existing catalog untouched.
    run_seed()

    stale_ids, missing_ids, _ = inspect_database()
    if missing_ids:
        raise RuntimeError(f"Database is still missing {len(missing_ids)} catalog songs")

    counts = _purge_stale_rows(stale_ids) if stale_ids else {}
    print(f"Deleted: {counts}")

    stale_ids, missing_ids, database_count = inspect_database()
    if stale_ids or missing_ids:
        raise RuntimeError(
            f"Database mismatch after sync: stale={len(stale_ids)}, missing={len(missing_ids)}"
        )
    print(f"Database synchronized: {database_count:,} songs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()

    stale_ids, missing_ids, database_count = inspect_database()
    print(f"Database songs: {database_count:,}")
    print(f"Stale songs: {len(stale_ids):,}")
    print(f"Missing songs: {len(missing_ids):,}")

    if not args.apply:
        return
    if args.backup_dir is None:
        raise SystemExit("--backup-dir is required with --apply")
    sync_database(args.backup_dir.resolve())


if __name__ == "__main__":
    main()
