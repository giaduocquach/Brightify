#!/usr/bin/env python3
"""Prune duplicate incremental tracks and merge a completed batch into catalog."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from tools.filter_data import (
    _artist_identity_sets,
    canonical_track_title,
    is_non_original_version,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_DATA_DIR = PROJECT_ROOT / "data"
MAIN_MUSIC_DIR = PROJECT_ROOT / "music_files"


def _load_metadata(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _validate_bundle(df: pd.DataFrame, embeddings: np.ndarray, metadata: dict) -> None:
    ids = df["track_id"].astype(str).tolist()
    if len(ids) != len(set(ids)):
        raise ValueError("Bundle contains duplicate track IDs")
    if embeddings.ndim != 2 or len(embeddings) != len(df):
        raise ValueError(
            f"Embedding alignment mismatch: rows={len(df)}, shape={embeddings.shape}"
        )
    if metadata.get("track_ids") != ids:
        raise ValueError("Metadata track IDs are not aligned with CSV rows")


def _find_rejections(
    main_df: pd.DataFrame,
    incremental_df: pd.DataFrame,
) -> pd.DataFrame:
    main_by_title: dict[str, list[pd.Series]] = {}
    for _, row in main_df.iterrows():
        title = canonical_track_title(row.get("track_name", ""))
        main_by_title.setdefault(title, []).append(row)

    records: list[dict] = []
    rejected_ids: set[str] = set()
    for _, row in incremental_df.iterrows():
        track_id = str(row["track_id"])
        title = canonical_track_title(row.get("track_name", ""))
        row_names, row_ids = _artist_identity_sets(row)
        for existing in main_by_title.get(title, []):
            existing_names, existing_ids = _artist_identity_sets(existing)
            if row_names & existing_names or row_ids & existing_ids:
                records.append(
                    {
                        "track_id": track_id,
                        "track_name": row.get("track_name"),
                        "artists": row.get("artists"),
                        "reason": "existing_song_same_title_artist",
                        "existing_track_id": str(existing["track_id"]),
                        "existing_track_name": existing.get("track_name"),
                        "existing_artists": existing.get("artists"),
                    }
                )
                rejected_ids.add(track_id)
                break

    for _, row in incremental_df.iterrows():
        track_id = str(row["track_id"])
        if track_id in rejected_ids:
            continue
        if is_non_original_version(
            row.get("track_name", ""),
            row.get("album_name", ""),
        ):
            records.append(
                {
                    "track_id": track_id,
                    "track_name": row.get("track_name"),
                    "artists": row.get("artists"),
                    "reason": "non_original_version",
                    "existing_track_id": None,
                    "existing_track_name": None,
                    "existing_artists": None,
                }
            )

    return pd.DataFrame(
        records,
        columns=[
            "track_id",
            "track_name",
            "artists",
            "reason",
            "existing_track_id",
            "existing_track_name",
            "existing_artists",
        ],
    )


def _metadata_for(df: pd.DataFrame, embeddings: np.ndarray, source: dict) -> dict:
    return {
        "created_at": datetime.now().isoformat(),
        "model": source.get("model", "vinai/phobert-base-v2"),
        "num_songs": int(len(df)),
        "embedding_dim": int(embeddings.shape[1]),
        "encoded_count": int(len(df)),
        "fallback_count": 0,
        "track_ids": df["track_id"].astype(str).tolist(),
        "track_names": df["track_name"].astype(str).tolist(),
    }


def _atomic_csv(df: pd.DataFrame, path: Path) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(temp_path, index=False, encoding="utf-8-sig")
    temp_path.replace(path)


def _atomic_npy(array: np.ndarray, path: Path) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("wb") as handle:
        np.save(handle, array)
    temp_path.replace(path)


def _atomic_json(payload, path: Path) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    _write_json(temp_path, payload)
    temp_path.replace(path)


def merge_batch(run_root: Path, apply: bool) -> None:
    incremental_data_dir = run_root / "data"
    incremental_music_dir = run_root / "music_files"
    logs_dir = run_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    main_csv = MAIN_DATA_DIR / "vietnamese_music_processed_full.csv"
    main_npy = MAIN_DATA_DIR / "vietnamese_music_embeddings_full.npy"
    main_meta_path = MAIN_DATA_DIR / "embeddings_metadata.json"
    main_log_path = MAIN_MUSIC_DIR / "download_log.json"
    incremental_csv = incremental_data_dir / "vietnamese_music_processed_full.csv"
    incremental_npy = incremental_data_dir / "vietnamese_music_embeddings_full.npy"
    incremental_meta_path = incremental_data_dir / "embeddings_metadata.json"
    incremental_log_path = incremental_music_dir / "download_log.json"

    main_df = pd.read_csv(main_csv)
    incremental_df = pd.read_csv(incremental_csv)
    main_df["track_id"] = main_df["track_id"].astype(str)
    incremental_df["track_id"] = incremental_df["track_id"].astype(str)
    main_embeddings = np.load(main_npy)
    incremental_embeddings = np.load(incremental_npy)
    main_meta = _load_metadata(main_meta_path)
    incremental_meta = _load_metadata(incremental_meta_path)
    _validate_bundle(main_df, main_embeddings, main_meta)
    _validate_bundle(incremental_df, incremental_embeddings, incremental_meta)

    collision_ids = set(main_df["track_id"]) & set(incremental_df["track_id"])
    if collision_ids:
        raise ValueError(f"Incremental bundle has {len(collision_ids)} existing track IDs")

    rejected = _find_rejections(main_df, incremental_df)
    report_path = logs_dir / "final_cross_catalog_duplicates.csv"
    rejected.to_csv(report_path, index=False, encoding="utf-8-sig")
    rejected_ids = set(rejected["track_id"].astype(str))
    keep_mask = ~incremental_df["track_id"].isin(rejected_ids)
    kept_df = incremental_df.loc[keep_mask].reset_index(drop=True)
    kept_embeddings = incremental_embeddings[np.flatnonzero(keep_mask.to_numpy())]

    print(f"Main catalog: {len(main_df):,}")
    print(f"Incremental processed: {len(incremental_df):,}")
    print(f"Rejected final duplicates/variants: {len(rejected):,}")
    print(f"Ready to merge: {len(kept_df):,}")
    print(f"Report: {report_path}")
    if not apply:
        return

    missing_mp3 = [
        track_id
        for track_id in kept_df["track_id"]
        if not (incremental_music_dir / f"{track_id}.mp3").exists()
    ]
    if missing_mp3:
        raise ValueError(f"Missing {len(missing_mp3)} incremental MP3 files")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = run_root / "backups" / f"final_merge_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_sources = (
        ("main", main_csv),
        ("main", main_npy),
        ("main", main_meta_path),
        ("main", main_log_path),
        ("incremental", incremental_csv),
        ("incremental", incremental_npy),
        ("incremental", incremental_meta_path),
        ("incremental", incremental_log_path),
    )
    for group, source in backup_sources:
        if source.exists():
            target_dir = backup_dir / group
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_dir / source.name)

    quarantine_dir = run_root / "quarantine_final_duplicates"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    for track_id in rejected_ids:
        source = incremental_music_dir / f"{track_id}.mp3"
        if source.exists():
            shutil.move(str(source), quarantine_dir / source.name)

    incremental_log = (
        _load_metadata(incremental_log_path)
        if incremental_log_path.exists()
        else {}
    )
    kept_log = {
        str(track_id): value
        for track_id, value in incremental_log.items()
        if str(track_id) in set(kept_df["track_id"])
    }
    kept_meta = _metadata_for(kept_df, kept_embeddings, incremental_meta)
    _atomic_csv(kept_df, incremental_csv)
    _atomic_npy(kept_embeddings, incremental_npy)
    _atomic_json(kept_meta, incremental_meta_path)
    _atomic_json(kept_log, incremental_log_path)

    aligned_incremental = kept_df.reindex(columns=main_df.columns)
    merged_df = pd.concat([main_df, aligned_incremental], ignore_index=True)
    merged_embeddings = np.concatenate([main_embeddings, kept_embeddings], axis=0)
    merged_meta = _metadata_for(merged_df, merged_embeddings, main_meta)
    _validate_bundle(merged_df, merged_embeddings, merged_meta)

    for track_id in kept_df["track_id"]:
        source = incremental_music_dir / f"{track_id}.mp3"
        target = MAIN_MUSIC_DIR / source.name
        if target.exists():
            raise ValueError(f"Refusing to overwrite existing MP3: {target}")
        shutil.copy2(source, target)

    main_log = _load_metadata(main_log_path) if main_log_path.exists() else {}
    main_log.update(kept_log)
    _atomic_csv(merged_df, main_csv)
    _atomic_npy(merged_embeddings, main_npy)
    _atomic_json(merged_meta, main_meta_path)
    _atomic_json(main_log, main_log_path)

    print(f"Merged catalog: {len(merged_df):,} (+{len(kept_df):,})")
    print(f"Backup: {backup_dir}")
    print(f"Quarantine: {quarantine_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    merge_batch(args.run_root.resolve(), args.apply)


if __name__ == "__main__":
    main()
