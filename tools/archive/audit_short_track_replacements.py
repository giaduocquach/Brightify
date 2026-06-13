#!/usr/bin/env python3
"""Find complete YouTube Music replacements for suspicious short catalog tracks."""

from __future__ import annotations

import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from tools.filter_data import (
    _normalize_match_text,
    canonical_track_title,
    is_non_original_version,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = PROJECT_ROOT / "data" / "vietnamese_music_processed_full.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "short_track_replacement_audit.csv"


def _base_title(title: str) -> str:
    title = re.sub(r"\s*(?:[#\[]\s*\d+\s*\]?)\s*$", " ", str(title or ""))
    title = re.sub(
        r"\b(?:audio cut|short version|snippet|teaser|intro|interlude|outro|"
        r"prologue|epilogue|special thanks)\b",
        " ",
        title,
        flags=re.IGNORECASE,
    )
    return canonical_track_title(title)


def _artist_names(result: dict) -> list[str]:
    return [
        str(item.get("name", "")).strip()
        for item in result.get("artists", [])
        if item.get("name")
    ]


def _match_score(expected_title: str, expected_artist: str, result: dict) -> float:
    candidate_title = canonical_track_title(result.get("title", ""))
    if candidate_title != expected_title:
        return 0.0
    title_score = SequenceMatcher(
        None,
        expected_title,
        candidate_title,
        autojunk=False,
    ).ratio()
    expected_artist_norm = _normalize_match_text(expected_artist)
    candidate_artists = {_normalize_match_text(name) for name in _artist_names(result)}
    if expected_artist_norm not in candidate_artists:
        return 0.0
    artist_score = max(
        (
            SequenceMatcher(None, expected_artist_norm, candidate, autojunk=False).ratio()
            for candidate in candidate_artists
            if candidate
        ),
        default=0.0,
    )
    return title_score * 0.72 + artist_score * 0.28


def _search_one(row: dict) -> dict:
    from ytmusicapi import YTMusic

    track_id = str(row["track_id"])
    title = str(row.get("track_name", ""))
    artist = str(row.get("primary_artist", ""))
    expected_title = _base_title(title)
    query_title = expected_title or _normalize_match_text(title)
    query = f"{artist} {query_title}"
    output = {
        "track_id": track_id,
        "track_name": title,
        "primary_artist": artist,
        "album_name": row.get("album_name"),
        "current_duration_s": round(float(row["track_duration_ms"]) / 1000, 3),
        "query": query,
    }
    try:
        results = YTMusic().search(query, filter="songs", limit=20)
    except Exception as exc:
        output["error"] = str(exc)
        return output

    candidates = []
    for result in results:
        video_id = result.get("videoId")
        if not video_id or str(video_id) == track_id:
            continue
        duration = result.get("duration_seconds")
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            continue
        if duration < 150 or duration > 360:
            continue
        album = result.get("album")
        album_name = album.get("name", "") if isinstance(album, dict) else str(album or "")
        if is_non_original_version(result.get("title", ""), album_name):
            continue
        score = _match_score(expected_title, artist, result)
        if score < 0.98:
            continue
        candidates.append((score, duration, result, album_name))

    if not candidates:
        output["replacement_found"] = False
        return output

    score, duration, result, album_name = max(
        candidates,
        key=lambda item: (item[0], item[1]),
    )
    output.update(
        {
            "replacement_found": True,
            "replacement_track_id": result.get("videoId"),
            "replacement_title": result.get("title"),
            "replacement_artists": ", ".join(_artist_names(result)),
            "replacement_album": album_name,
            "replacement_duration_s": duration,
            "replacement_score": round(float(score), 5),
        }
    )
    return output


def audit(
    catalog_path: Path,
    output_path: Path,
    resume: bool,
    workers: int,
    limit: int | None,
) -> pd.DataFrame:
    catalog = pd.read_csv(catalog_path)
    duration = pd.to_numeric(catalog["track_duration_ms"], errors="coerce")
    short = catalog[duration < 150_000].copy()
    if limit:
        short = short.head(limit)

    existing = pd.DataFrame()
    if resume and output_path.exists():
        existing = pd.read_csv(output_path)
    done_ids = set(existing.get("track_id", pd.Series(dtype=str)).astype(str))
    pending = [
        row.to_dict()
        for _, row in short.iterrows()
        if str(row["track_id"]) not in done_ids
    ]
    records: list[dict] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_search_one, row): row["track_id"] for row in pending}
        for index, future in enumerate(as_completed(futures), start=1):
            try:
                records.append(future.result())
            except Exception as exc:
                records.append({"track_id": futures[future], "error": str(exc)})
            if index % 25 == 0:
                combined = pd.concat([existing, pd.DataFrame(records)], ignore_index=True)
                combined.to_csv(output_path, index=False, encoding="utf-8-sig")
                time.sleep(1)

    combined = pd.concat([existing, pd.DataFrame(records)], ignore_index=True)
    combined = combined.drop_duplicates("track_id", keep="last")
    combined.to_csv(output_path, index=False, encoding="utf-8-sig")
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    result = audit(
        args.catalog.resolve(),
        args.output.resolve(),
        args.resume,
        max(1, args.workers),
        args.limit,
    )
    found = int(result.get("replacement_found", pd.Series(dtype=bool)).fillna(False).sum())
    print(f"Audited short tracks: {len(result):,}")
    print(f"Replacement candidates: {found:,}")
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()
