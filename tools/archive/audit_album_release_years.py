#!/usr/bin/env python3
"""Resolve original album years from YouTube Music with resumable checkpoints."""

from __future__ import annotations

import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = PROJECT_ROOT / "data" / "vietnamese_music_processed_full.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "album_release_year_audit.csv"
_local = threading.local()


def _client():
    if not hasattr(_local, "ytmusic"):
        from ytmusicapi import YTMusic

        _local.ytmusic = YTMusic()
    return _local.ytmusic


def _resolve(album_id: str) -> dict:
    record = {"album_id": album_id}
    try:
        album = _client().get_album(album_id)
        record.update(
            {
                "resolved_title": album.get("title"),
                "resolved_year": album.get("year"),
                "resolved_type": album.get("type"),
            }
        )
    except Exception as exc:
        record["error"] = str(exc)
    return record


def audit(catalog: Path, output: Path, workers: int, resume: bool) -> pd.DataFrame:
    df = pd.read_csv(catalog)
    album_ids = sorted(
        {
            str(value).strip()
            for value in df.get("album_id", pd.Series(dtype=str)).dropna()
            if len(str(value).strip()) > 3
        }
    )
    existing = pd.read_csv(output) if resume and output.exists() else pd.DataFrame()
    done = set(existing.get("album_id", pd.Series(dtype=str)).astype(str))
    pending = [album_id for album_id in album_ids if album_id not in done]
    records: list[dict] = []
    output.parent.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(_resolve, album_id): album_id for album_id in pending}
        for index, future in enumerate(as_completed(futures), start=1):
            try:
                records.append(future.result())
            except Exception as exc:
                records.append({"album_id": futures[future], "error": str(exc)})
            if index % 100 == 0:
                combined = pd.concat([existing, pd.DataFrame(records)], ignore_index=True)
                combined.to_csv(output, index=False, encoding="utf-8-sig")

    combined = pd.concat([existing, pd.DataFrame(records)], ignore_index=True)
    combined = combined.drop_duplicates("album_id", keep="last")
    combined.to_csv(output, index=False, encoding="utf-8-sig")
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    result = audit(
        args.catalog.resolve(),
        args.output.resolve(),
        args.workers,
        args.resume,
    )
    resolved = pd.to_numeric(result.get("resolved_year"), errors="coerce").notna().sum()
    print(f"Albums audited: {len(result):,}")
    print(f"Years resolved: {resolved:,}")
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()
