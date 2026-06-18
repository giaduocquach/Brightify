"""Freeze the current runtime dataset into a versioned serving release.

The release layout follows docs/PLAN_PRODUCTION_DATA_ARCHITECTURE_V24.md:

    <output_root>/<release_name>/
      manifest.json
      data/
      music_files/
      checkpoints/

Files are hard-linked by default for fast local packaging without duplicating
large MP3 payloads. Use --copy to materialize full copies instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config as cfg


PROJECT_ROOT = cfg.PROJECT_ROOT
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "var" / "serving_releases"

# (config value, dest subdir, required). Destination filename is derived from the
# source basename so the release always matches what config/runtime expects —
# no hardcoded names to drift. Active set reflects the current config (V41: MuQ
# backbone + e5-large lyrics + emotion_labels_v6i). Optional files are skipped
# when absent.
_RUNTIME_SPEC = [
    (cfg.PROCESSED_FILE,             "data",        True),   # song catalog
    (cfg.EMBEDDINGS_FILE,            "data",        True),   # lyrics_e5large.npy
    (cfg.EMBEDDINGS_META_FILE,       "data",        True),   # embeddings_metadata.json
    (cfg.MUQ_EMBEDDINGS_FILE,        "data",        True),   # muq_embeddings.npy (active backbone)
    (cfg.MUQ_METADATA_FILE,          "data",        True),   # muq_metadata.json
    (cfg.RELABELED_EMOTIONS_FILE,    "data",        True),   # emotion_labels_v6i.json
    (cfg.PHASE1_ARTISTS_FILE,        "checkpoints", True),
    (cfg.MERT_EMBEDDINGS_FILE,       "data",        False),  # optional (ENABLE_MERT)
    (cfg.MERT_EMBEDDINGS_META_FILE,  "data",        False),
    (cfg.COVER_INDEX_FILE,           "data",        False),  # cover dedup clusters
    (cfg.CLEAN_BPM_FILE,             "data",        False),  # tempo signal
    (cfg.AUDIO_MANIFEST_FILE,        "data",        False),  # has_audio source in CDN mode
    (cfg.VOCAL_REGIONS_FILE,         "data",        False),  # crossfade vocal-region backfill input
    (cfg.CLEAN_DURATIONS_FILE,       "data",        False),  # crossfade reconciled-duration backfill input
]

RUNTIME_FILES = [
    (f"{subdir}/{Path(value).name}", Path(value))
    for value, subdir, required in _RUNTIME_SPEC
    if required or Path(value).exists()
]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_or_link(src: Path, dst: Path, copy_mode: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    if copy_mode:
        shutil.copy2(src, dst)
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _validate_runtime_contract(no_music: bool) -> dict[str, int]:
    df = pd.read_csv(cfg.PROCESSED_FILE, low_memory=False)
    n_songs = len(df)

    lyrics = np.load(cfg.EMBEDDINGS_FILE, mmap_mode="r")
    muq = np.load(cfg.MUQ_EMBEDDINGS_FILE, mmap_mode="r")
    with open(cfg.EMBEDDINGS_META_FILE, "r", encoding="utf-8") as handle:
        embedding_meta = json.load(handle)
    with open(cfg.RELABELED_EMOTIONS_FILE, "r", encoding="utf-8") as handle:
        emotions = json.load(handle)

    # Per-song counts must equal the catalog size. Optional/superset files
    # (cover_index, clean_bpm — keyed lookups) are intentionally not enforced.
    checks = {
        "songs": n_songs,
        "lyrics_embeddings": int(lyrics.shape[0]),
        "muq_embeddings": int(muq.shape[0]),
        "embedding_meta_track_ids": len(embedding_meta.get("track_ids", [])),
        "emotion_labels": len(emotions),
    }
    if not no_music:
        checks["music_files"] = len(sorted(cfg.MUSIC_DIR.glob("*.mp3")))

    mismatches = {
        key: value for key, value in checks.items()
        if key != "songs" and value != n_songs
    }
    if mismatches:
        details = ", ".join(f"{key}={value}" for key, value in mismatches.items())
        raise RuntimeError(f"Runtime contract mismatch against catalog({n_songs}): {details}")
    return checks


def _link_music_files(dst_root: Path, copy_mode: bool) -> dict[str, int]:
    music_dir = dst_root / "music_files"
    music_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    total_bytes = 0
    for src in sorted(cfg.MUSIC_DIR.glob("*.mp3")):
        dst = music_dir / src.name
        _copy_or_link(src, dst, copy_mode=copy_mode)
        count += 1
        total_bytes += src.stat().st_size
    return {"count": count, "total_bytes": total_bytes}


def build_release(output_root: Path, release_name: str, copy_mode: bool, no_music: bool = False) -> Path:
    checks = _validate_runtime_contract(no_music=no_music)
    release_dir = output_root / release_name
    if release_dir.exists():
        raise FileExistsError(f"Release already exists: {release_dir}")
    release_dir.mkdir(parents=True, exist_ok=False)

    manifest_files = []
    for relative_path, src in RUNTIME_FILES:
        if not src.exists():
            raise FileNotFoundError(f"Required runtime file missing: {src}")
        dst = release_dir / relative_path
        _copy_or_link(src, dst, copy_mode=copy_mode)
        manifest_files.append({
            "path": relative_path,
            "source": str(src),
            "size_bytes": src.stat().st_size,
            "sha256": _sha256_file(src),
        })

    if no_music:
        music_stats = {"count": 0, "total_bytes": 0, "skipped": True}
    else:
        music_stats = _link_music_files(release_dir, copy_mode=copy_mode)

    manifest = {
        "release_name": release_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "serving_root": str(release_dir),
        "mode": "copy" if copy_mode else "hardlink",
        "contract_counts": checks,
        "music_files": music_stats,
        "files": manifest_files,
    }
    manifest_path = release_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    current_link = output_root / "current"
    if current_link.is_symlink() or current_link.is_file():
        current_link.unlink()
    elif current_link.is_dir():
        shutil.rmtree(current_link)
    current_link.symlink_to(release_dir.name)
    return release_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--release-name", type=str)
    parser.add_argument("--copy", action="store_true", help="copy files instead of hard-linking")
    parser.add_argument("--no-music", action="store_true",
                        help="data-only release (AWS: MP3s live in S3, not in the release)")
    args = parser.parse_args()

    release_name = args.release_name or datetime.now().strftime("%Y-%m-%d_%H%M%S")
    release_dir = build_release(args.output_root.resolve(), release_name,
                                copy_mode=args.copy, no_music=args.no_music)
    print(f"[serving-release] created {release_dir}")


if __name__ == "__main__":
    main()
