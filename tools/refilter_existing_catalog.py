#!/usr/bin/env python3
"""Re-filter the canonical catalog and keep its file artifacts aligned."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.filter_data import (
    MIN_DURATION_MS,
    _audio_similarity,
    _normalize_match_text,
    are_duplicate_song_rows,
    catalog_quality_rejection_reason,
    canonical_track_title,
    foreign_lyrics_language,
    is_allowed_short_track,
    is_known_foreign_identity_release,
    is_old_genre_track,
    is_non_original_version,
    is_seasonal_track,
    run_filter,
)


DATA_DIR = PROJECT_ROOT / "data"
MUSIC_DIR = PROJECT_ROOT / "music_files"
CATALOG_PATH = DATA_DIR / "vietnamese_music_processed_full.csv"
EMBEDDINGS_PATH = DATA_DIR / "vietnamese_music_embeddings_full.npy"
METADATA_PATH = DATA_DIR / "embeddings_metadata.json"
MERT_EMBEDDINGS_PATH = DATA_DIR / "mert_embeddings.npy"
MERT_METADATA_PATH = DATA_DIR / "mert_metadata.json"
EMOTION_LABELS_PATH = DATA_DIR / "emotion_labels_v5c.json"
DOWNLOAD_LOG_PATH = MUSIC_DIR / "download_log.json"
AUDIO_EMBEDDINGS_PATH = DATA_DIR / "audio_embeddings.json"
AUDIO_QUALITY_AUDIT_PATH = DATA_DIR / "catalog_audio_quality_audit.csv"
ALBUM_YEAR_AUDIT_PATH = DATA_DIR / "album_release_year_audit.csv"


def _dedup_key(row: pd.Series) -> str:
    artist = row.get("primary_artist", row.get("artists", ""))
    return "|".join(
        (
            _normalize_match_text(row.get("track_name", "")),
            _normalize_match_text(artist),
        )
    )


def _atomic_write_json(path: Path, payload: dict) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _build_removed_report(
    original: pd.DataFrame,
    filtered: pd.DataFrame,
    audio_embeddings: dict[str, list[float]] | None = None,
) -> pd.DataFrame:
    kept_ids = set(filtered["track_id"].astype(str))
    removed = original[~original["track_id"].astype(str).isin(kept_ids)].copy()
    kept_keys = set(filtered.apply(_dedup_key, axis=1))
    kept_by_title = {
        title: group
        for title, group in filtered.groupby(
            filtered["track_name"].apply(canonical_track_title),
            sort=False,
        )
        if title
    }
    if audio_embeddings is None:
        audio_embeddings = {}
        audio_path = DATA_DIR / "audio_embeddings.json"
        if audio_path.exists():
            audio_embeddings = json.loads(audio_path.read_text(encoding="utf-8"))
    audio_quality_by_id: dict[str, dict] = {}
    if AUDIO_QUALITY_AUDIT_PATH.exists():
        audio_quality = pd.read_csv(AUDIO_QUALITY_AUDIT_PATH)
        audio_quality_by_id = {
            str(row["track_id"]): row.to_dict()
            for _, row in audio_quality.iterrows()
        }
    album_year_by_id: dict[str, float] = {}
    if ALBUM_YEAR_AUDIT_PATH.exists():
        album_years = pd.read_csv(ALBUM_YEAR_AUDIT_PATH)
        album_year_by_id = dict(
            zip(
                album_years["album_id"].astype(str),
                pd.to_numeric(album_years["resolved_year"], errors="coerce"),
            )
        )

    audio_candidates: dict[str, list[pd.Series]] = {}
    kept_with_audio = filtered[
        filtered["track_id"].astype(str).isin(audio_embeddings)
    ]
    removed_with_audio = removed[
        removed["track_id"].astype(str).isin(audio_embeddings)
    ]
    if not kept_with_audio.empty and not removed_with_audio.empty:
        from sklearn.neighbors import NearestNeighbors

        kept_vectors = np.asarray(
            [
                audio_embeddings[str(track_id)]
                for track_id in kept_with_audio["track_id"]
            ],
            dtype=np.float32,
        )
        removed_vectors = np.asarray(
            [
                audio_embeddings[str(track_id)]
                for track_id in removed_with_audio["track_id"]
            ],
            dtype=np.float32,
        )
        neighbor_count = min(6, len(kept_with_audio))
        model = NearestNeighbors(
            n_neighbors=neighbor_count,
            metric="cosine",
            algorithm="brute",
            n_jobs=-1,
        ).fit(kept_vectors)
        distances, positions = model.kneighbors(removed_vectors)
        kept_rows = list(kept_with_audio.iterrows())
        for row_position, (_, removed_row) in enumerate(
            removed_with_audio.iterrows()
        ):
            candidates = []
            for distance, kept_position in zip(
                distances[row_position],
                positions[row_position],
            ):
                if 1.0 - float(distance) < 0.995:
                    continue
                candidates.append(kept_rows[int(kept_position)][1])
            audio_candidates[str(removed_row.get("track_id"))] = candidates

    reasons = []
    duplicate_ids = []
    duplicate_names = []

    def matches_report_duplicate(
        removed_row: pd.Series,
        kept_row: pd.Series,
        similarity: float | None,
    ) -> bool:
        if are_duplicate_song_rows(removed_row, kept_row, similarity):
            return True
        return (
            similarity is not None
            and similarity >= 0.995
            and canonical_track_title(removed_row.get("track_name", ""))
            == canonical_track_title(kept_row.get("track_name", ""))
        )

    for _, row in removed.iterrows():
        duplicate_match = None
        title_key = canonical_track_title(row.get("track_name", ""))
        candidates = kept_by_title.get(title_key)
        if candidates is not None:
            for _, candidate in candidates.iterrows():
                similarity = _audio_similarity(
                    row.get("track_id"),
                    candidate.get("track_id"),
                    audio_embeddings,
                )
                if matches_report_duplicate(row, candidate, similarity):
                    duplicate_match = candidate
                    break
        if duplicate_match is None:
            for candidate in audio_candidates.get(str(row.get("track_id")), []):
                similarity = _audio_similarity(
                    row.get("track_id"),
                    candidate.get("track_id"),
                    audio_embeddings,
                )
                if matches_report_duplicate(row, candidate, similarity):
                    duplicate_match = candidate
                    break

        catalog_quality_reason = catalog_quality_rejection_reason(
            row,
            audio_quality_by_id.get(str(row.get("track_id", ""))),
        )
        release_year = None
        for value in (
            row.get("year"),
            row.get("release_date"),
            album_year_by_id.get(str(row.get("album_id", ""))),
            row.get("upload_year"),
            row.get("upload_date"),
        ):
            if value is None or pd.isna(value):
                continue
            try:
                release_year = int(str(value).strip()[:4])
                break
            except (TypeError, ValueError):
                continue
        if duplicate_match is not None:
            reason = "duplicate_song_entity"
        elif catalog_quality_reason is not None:
            reason = catalog_quality_reason
        elif release_year is not None and release_year < 2013:
            reason = "pre_2013_release"
        elif (
            pd.notna(
                pd.to_numeric(
                    pd.Series([row.get("track_duration_ms")]),
                    errors="coerce",
                ).iloc[0]
            )
            and float(
                pd.to_numeric(
                    pd.Series([row.get("track_duration_ms")]),
                    errors="coerce",
                ).iloc[0]
            ) < MIN_DURATION_MS
            and not is_allowed_short_track(row)
        ):
            reason = "short_track"
        elif is_non_original_version(
            row.get("track_name", ""),
            row.get("album_name", ""),
        ):
            reason = "non_original_version"
        elif is_seasonal_track(
            row.get("track_name", ""),
            row.get("album_name", ""),
            row.get("plain_lyrics", ""),
        ):
            reason = "seasonal"
        elif is_old_genre_track(
            row.get("track_name", ""),
            row.get("album_name", ""),
            row.get("genres", ""),
        ):
            reason = "old_genre"
        elif (
            foreign_lyrics_language(row.get("plain_lyrics", "")) is not None
            and is_known_foreign_identity_release(
                row.get("primary_artist", ""),
                row.get("album_name", ""),
            )
        ):
            reason = "foreign_language_or_identity"
        elif _dedup_key(row) in kept_keys:
            reason = "duplicate_name_artist"
        else:
            reason = "catalog_quality_filter"

        reasons.append(reason)
        duplicate_ids.append(
            duplicate_match.get("track_id") if duplicate_match is not None else None
        )
        duplicate_names.append(
            duplicate_match.get("track_name") if duplicate_match is not None else None
        )

    removed["filter_reason"] = reasons
    removed["duplicate_of_track_id"] = duplicate_ids
    removed["duplicate_of_track_name"] = duplicate_names

    preferred_columns = [
        "track_id",
        "track_name",
        "artists",
        "primary_artist",
        "album_name",
        "filter_reason",
        "duplicate_of_track_id",
        "duplicate_of_track_name",
        "track_popularity",
        "view_count",
        "year",
        "release_date",
    ]
    columns = [column for column in preferred_columns if column in removed.columns]
    remaining = [column for column in removed.columns if column not in columns]
    return removed[columns + remaining]


def _validate_artifacts(
    original: pd.DataFrame,
    filtered: pd.DataFrame,
    embeddings: np.ndarray,
    metadata: dict,
    mert_embeddings: np.ndarray | None = None,
    mert_metadata: dict | None = None,
    emotion_labels: dict | None = None,
) -> None:
    original_ids = original["track_id"].astype(str).tolist()
    filtered_ids = filtered["track_id"].astype(str).tolist()
    metadata_ids = [str(track_id) for track_id in metadata.get("track_ids", [])]

    if len(original_ids) != len(set(original_ids)):
        raise ValueError("Current catalog contains duplicate track_id values")
    if len(filtered_ids) != len(set(filtered_ids)):
        raise ValueError("Filtered catalog contains duplicate track_id values")
    if not set(filtered_ids).issubset(original_ids):
        raise ValueError("Filtered catalog contains IDs absent from the source")
    if embeddings.shape[0] != len(metadata_ids):
        raise ValueError("Embedding rows do not match metadata track IDs")
    if metadata_ids != original_ids:
        raise ValueError("Embedding metadata order does not match the current catalog")
    if mert_embeddings is not None and mert_metadata is not None:
        mert_ids = [str(track_id) for track_id in mert_metadata.get("track_ids", [])]
        if mert_embeddings.shape[0] != len(mert_ids):
            raise ValueError("MERT embedding rows do not match MERT metadata track IDs")
        if mert_ids != original_ids:
            raise ValueError("MERT metadata order does not match the current catalog")
    if emotion_labels is not None:
        emotion_ids = [str(track_id) for track_id in emotion_labels.keys()]
        if emotion_ids != original_ids:
            raise ValueError("Emotion label order does not match the current catalog")


def _write_summary(
    path: Path,
    original_count: int,
    filtered_count: int,
    removed: pd.DataFrame,
    quarantined_count: int,
    backup_dir: Path | None,
    filter_report: str,
) -> None:
    reason_counts = removed["filter_reason"].value_counts().to_dict()
    lines = [
        "# Existing catalog re-filter",
        "",
        f"- Input tracks: {original_count:,}",
        f"- Kept tracks: {filtered_count:,}",
        f"- Removed tracks: {len(removed):,}",
        f"- Non-original versions: {reason_counts.get('non_original_version', 0):,}",
        f"- Duplicate song entities: {reason_counts.get('duplicate_song_entity', 0):,}",
        f"- Exact duplicate name/artist: {reason_counts.get('duplicate_name_artist', 0):,}",
        f"- Short tracks: {reason_counts.get('short_track', 0):,}",
        f"- Seasonal tracks: {reason_counts.get('seasonal', 0):,}",
        f"- Other catalog filters: {reason_counts.get('catalog_quality_filter', 0):,}",
        f"- MP3 files quarantined: {quarantined_count:,}",
    ]
    if backup_dir:
        lines.append(f"- Backup: `{backup_dir.relative_to(PROJECT_ROOT)}`")
    lines.extend(("", "## Filter output", "", "```text", filter_report.strip(), "```", ""))
    path.write_text("\n".join(lines), encoding="utf-8")


def refilter_catalog(
    apply: bool,
    source_catalog: Path = CATALOG_PATH,
    source_embeddings: Path = EMBEDDINGS_PATH,
    source_metadata: Path = METADATA_PATH,
    recovery_music_dir: Path | None = None,
    source_download_log: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, Path | None]:
    original = pd.read_csv(source_catalog)
    embeddings = np.load(source_embeddings)
    metadata = json.loads(source_metadata.read_text(encoding="utf-8"))
    mert_embeddings = np.load(MERT_EMBEDDINGS_PATH) if MERT_EMBEDDINGS_PATH.exists() else None
    mert_metadata = (
        json.loads(MERT_METADATA_PATH.read_text(encoding="utf-8"))
        if MERT_METADATA_PATH.exists()
        else None
    )
    emotion_labels = (
        json.loads(EMOTION_LABELS_PATH.read_text(encoding="utf-8"))
        if EMOTION_LABELS_PATH.exists()
        else None
    )
    source_audio_embeddings = (
        json.loads(AUDIO_EMBEDDINGS_PATH.read_text(encoding="utf-8"))
        if AUDIO_EMBEDDINGS_PATH.exists()
        else {}
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    day = datetime.now().strftime("%Y%m%d")
    backup_dir = PROJECT_ROOT / "backups" / f"catalog_refilter_{stamp}" if apply else None

    with tempfile.TemporaryDirectory(prefix="brightify_refilter_") as temp_dir_value:
        temp_dir = Path(temp_dir_value)
        filtered_path = temp_dir / "filtered.csv"
        filter_report_path = temp_dir / "filter_report.md"
        filtered = run_filter(
            input_path=source_catalog,
            output_path=filtered_path,
            report_path=filter_report_path,
        )
        _validate_artifacts(
            original,
            filtered,
            embeddings,
            metadata,
            mert_embeddings=mert_embeddings,
            mert_metadata=mert_metadata,
            emotion_labels=emotion_labels,
        )
        removed = _build_removed_report(
            original,
            filtered,
            audio_embeddings=source_audio_embeddings,
        )

        if not apply:
            removed_report_path = DATA_DIR / f"filtered_out_tracks_{day}_dry_run.csv"
            summary_path = DATA_DIR / f"catalog_refilter_summary_{day}_dry_run.md"
            removed.to_csv(removed_report_path, index=False)
            _write_summary(
                summary_path,
                len(original),
                len(filtered),
                removed,
                0,
                None,
                filter_report_path.read_text(encoding="utf-8"),
            )
            return filtered, removed, None

        assert backup_dir is not None
        unavailable_mp3 = [
            track_id
            for track_id in filtered["track_id"].astype(str)
            if not (MUSIC_DIR / f"{track_id}.mp3").exists()
            and not (
                recovery_music_dir
                and (recovery_music_dir / f"{track_id}.mp3").exists()
            )
        ]
        if unavailable_mp3:
            raise RuntimeError(
                f"{len(unavailable_mp3)} kept tracks have no active or recovery MP3"
            )

        removed_report_path = DATA_DIR / f"filtered_out_tracks_{day}.csv"
        summary_path = DATA_DIR / f"catalog_refilter_summary_{day}.md"
        backup_data_dir = backup_dir / "data"
        backup_music_dir = backup_dir / "music_files"
        backup_data_dir.mkdir(parents=True)
        backup_music_dir.mkdir(parents=True)

        for source in (
            CATALOG_PATH,
            EMBEDDINGS_PATH,
            METADATA_PATH,
            MERT_EMBEDDINGS_PATH,
            MERT_METADATA_PATH,
            EMOTION_LABELS_PATH,
            AUDIO_EMBEDDINGS_PATH,
        ):
            if not source.exists():
                continue
            shutil.copy2(source, backup_data_dir / source.name)
        if DOWNLOAD_LOG_PATH.exists():
            shutil.copy2(DOWNLOAD_LOG_PATH, backup_music_dir / DOWNLOAD_LOG_PATH.name)

        original_index = {
            str(track_id): index
            for index, track_id in enumerate(metadata["track_ids"])
        }
        filtered_ids = filtered["track_id"].astype(str).tolist()
        kept_indices = [original_index[track_id] for track_id in filtered_ids]
        filtered_embeddings = embeddings[kept_indices]
        filtered_mert_embeddings = (
            mert_embeddings[kept_indices] if mert_embeddings is not None else None
        )

        filtered_metadata = dict(metadata)
        filtered_metadata.update(
            {
                "created_at": datetime.now().isoformat(),
                "num_songs": len(filtered),
                "encoded_count": len(filtered),
                "track_ids": filtered_ids,
                "track_names": filtered["track_name"].astype(str).tolist(),
            }
        )
        filtered_metadata["fallback_count"] = min(
            int(filtered_metadata.get("fallback_count", 0)),
            len(filtered),
        )

        temp_embeddings_path = EMBEDDINGS_PATH.with_suffix(".npy.tmp")
        with temp_embeddings_path.open("wb") as handle:
            np.save(handle, filtered_embeddings)

        shutil.copy2(filtered_path, CATALOG_PATH.with_suffix(".csv.tmp"))
        os.replace(CATALOG_PATH.with_suffix(".csv.tmp"), CATALOG_PATH)
        os.replace(temp_embeddings_path, EMBEDDINGS_PATH)
        _atomic_write_json(METADATA_PATH, filtered_metadata)
        if filtered_mert_embeddings is not None:
            temp_mert_path = MERT_EMBEDDINGS_PATH.with_suffix(".npy.tmp")
            with temp_mert_path.open("wb") as handle:
                np.save(handle, filtered_mert_embeddings)
            os.replace(temp_mert_path, MERT_EMBEDDINGS_PATH)
        if mert_metadata is not None:
            filtered_mert_metadata = dict(mert_metadata)
            filtered_mert_metadata.update(
                {
                    "n_songs": len(filtered),
                    "n_done": len(filtered),
                    "n_fail": 0,
                    "coverage_pct": 100.0,
                    "done_track_ids": filtered_ids,
                    "track_ids": filtered_ids,
                }
            )
            _atomic_write_json(MERT_METADATA_PATH, filtered_mert_metadata)
        if emotion_labels is not None:
            _atomic_write_json(
                EMOTION_LABELS_PATH,
                {
                    track_id: emotion_labels[track_id]
                    for track_id in filtered_ids
                    if track_id in emotion_labels
                },
            )
        if AUDIO_EMBEDDINGS_PATH.exists():
            audio_embeddings = json.loads(
                AUDIO_EMBEDDINGS_PATH.read_text(encoding="utf-8")
            )
            _atomic_write_json(
                AUDIO_EMBEDDINGS_PATH,
                {
                    track_id: audio_embeddings[track_id]
                    for track_id in filtered_ids
                    if track_id in audio_embeddings
                },
            )

        kept_id_set = set(filtered_ids)
        if recovery_music_dir:
            for track_id in filtered_ids:
                active_path = MUSIC_DIR / f"{track_id}.mp3"
                recovery_path = recovery_music_dir / f"{track_id}.mp3"
                if not active_path.exists() and recovery_path.exists():
                    shutil.copy2(recovery_path, active_path)

        quarantined_count = 0
        for mp3_path in MUSIC_DIR.glob("*.mp3"):
            if mp3_path.stem in kept_id_set:
                continue
            shutil.move(str(mp3_path), backup_music_dir / mp3_path.name)
            quarantined_count += 1

        log_source = source_download_log or DOWNLOAD_LOG_PATH
        if log_source.exists():
            download_log = json.loads(log_source.read_text(encoding="utf-8"))
            filtered_log = {
                str(track_id): value
                for track_id, value in download_log.items()
                if str(track_id) in kept_id_set
            }
            _atomic_write_json(DOWNLOAD_LOG_PATH, filtered_log)

        missing_mp3 = [
            track_id
            for track_id in filtered_ids
            if not (MUSIC_DIR / f"{track_id}.mp3").exists()
        ]
        if missing_mp3:
            raise RuntimeError(f"{len(missing_mp3)} kept tracks are missing MP3 files")

        removed.to_csv(removed_report_path, index=False)
        _write_summary(
            summary_path,
            len(original),
            len(filtered),
            removed,
            quarantined_count,
            backup_dir,
            filter_report_path.read_text(encoding="utf-8"),
        )

    return filtered, removed, backup_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag, only write audit reports.",
    )
    parser.add_argument("--source-catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--source-embeddings", type=Path, default=EMBEDDINGS_PATH)
    parser.add_argument("--source-metadata", type=Path, default=METADATA_PATH)
    parser.add_argument("--recovery-music-dir", type=Path)
    parser.add_argument("--source-download-log", type=Path)
    args = parser.parse_args()

    filtered, removed, backup_dir = refilter_catalog(
        apply=args.apply,
        source_catalog=args.source_catalog.resolve(),
        source_embeddings=args.source_embeddings.resolve(),
        source_metadata=args.source_metadata.resolve(),
        recovery_music_dir=(
            args.recovery_music_dir.resolve()
            if args.recovery_music_dir
            else None
        ),
        source_download_log=(
            args.source_download_log.resolve()
            if args.source_download_log
            else None
        ),
    )
    print(f"Kept: {len(filtered):,}")
    print(f"Removed: {len(removed):,}")
    print(removed["filter_reason"].value_counts().to_string())
    if backup_dir:
        print(f"Backup: {backup_dir}")


if __name__ == "__main__":
    main()
