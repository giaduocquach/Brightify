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

RUNTIME_FILES = [
    ("data/vietnamese_music_processed_full.csv", Path(cfg.PROCESSED_FILE)),
    ("data/vietnamese_music_embeddings_full.npy", Path(cfg.EMBEDDINGS_FILE)),
    ("data/embeddings_metadata.json", Path(cfg.EMBEDDINGS_META_FILE)),
    ("data/mert_embeddings.npy", Path(cfg.MERT_EMBEDDINGS_FILE)),
    ("data/mert_metadata.json", Path(cfg.MERT_EMBEDDINGS_META_FILE)),
    ("data/emotion_labels_v5c.json", Path(cfg.RELABELED_EMOTIONS_FILE)),
    ("checkpoints/phase1_artists.csv", Path(cfg.PHASE1_ARTISTS_FILE)),
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


def _validate_runtime_contract() -> dict[str, int]:
    df = pd.read_csv(cfg.PROCESSED_FILE)
    n_songs = len(df)

    embeddings = np.load(cfg.EMBEDDINGS_FILE, mmap_mode="r")
    mert = np.load(cfg.MERT_EMBEDDINGS_FILE, mmap_mode="r")
    with open(cfg.EMBEDDINGS_META_FILE, "r", encoding="utf-8") as handle:
        embedding_meta = json.load(handle)
    with open(cfg.RELABELED_EMOTIONS_FILE, "r", encoding="utf-8") as handle:
        emotions = json.load(handle)

    mp3_files = sorted(cfg.MUSIC_DIR.glob("*.mp3"))

    checks = {
        "songs": n_songs,
        "lyrics_embeddings": int(embeddings.shape[0]),
        "embedding_meta_track_ids": len(embedding_meta.get("track_ids", [])),
        "mert_rows": int(mert.shape[0]),
        "emotion_labels": len(emotions),
        "music_files": len(mp3_files),
    }
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


def build_release(output_root: Path, release_name: str, copy_mode: bool) -> Path:
    checks = _validate_runtime_contract()
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
    args = parser.parse_args()

    release_name = args.release_name or datetime.now().strftime("%Y-%m-%d_%H%M%S")
    release_dir = build_release(args.output_root.resolve(), release_name, copy_mode=args.copy)
    print(f"[serving-release] created {release_dir}")


if __name__ == "__main__":
    main()
