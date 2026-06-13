"""Archive data artifacts that are not required by the production runtime."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import config as cfg


PROJECT_ROOT = cfg.PROJECT_ROOT
DEFAULT_ARCHIVE_ROOT = cfg.ARCHIVE_ROOT

ROOT_DIR_CANDIDATES = [
    PROJECT_ROOT / "backups",
    PROJECT_ROOT / "incremental_runs",
    PROJECT_ROOT / "var" / "runtime" / "backtest",
]

DATA_PATTERNS = [
    "catalog_refilter_summary_*.md",
    "filtered_out_tracks_*.csv",
    "duplicate_clusters_*.csv",
    "catalog_audio_quality_audit*.csv",
    "short_track_replacement_audit*.csv",
    "duration_mismatch_replacement_audit.csv",
    "catalog_audit_removed_*.csv",
    "album_release_year_audit.csv",
    "*.bak.csv",
    "*.bak.npy",
]

DATA_EXPLICIT_FILES = [
    "arousal_v2.json",
    "arousal_v3.json",
    "audio_embeddings.json",
    "clap_emotions.json",
    "clap_emotions_checkpoint.json",
    "emotion_labels_v2.json",
    "emotion_labels_v3.json",
    "emotion_labels_v3_llm_sample.json",
    "emotion_labels_v4.json",
    "emotion_labels_v5.json",
    "emotion_labels_v5b.json",
    "filtered_out_tracks_20260606_summary.md",
    "kg_embeddings_meta.json",
    "lyrics_backup.json",
    "mert_arousal.json",
]

MUSIC_PATTERNS = [
    "*.part",
    "*.part.*",
    "*.ytdl",
]


def _collect_candidates() -> list[Path]:
    candidates: list[Path] = []
    for path in ROOT_DIR_CANDIDATES:
        if path.exists():
            candidates.append(path)

    data_dir = Path(cfg.DATA_DIR)
    for pattern in DATA_PATTERNS:
        candidates.extend(sorted(data_dir.glob(pattern)))
    for filename in DATA_EXPLICIT_FILES:
        path = data_dir / filename
        if path.exists():
            candidates.append(path)

    music_dir = cfg.MUSIC_DIR
    for pattern in MUSIC_PATTERNS:
        candidates.extend(sorted(music_dir.glob(pattern)))

    # Deduplicate while preserving order.
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path not in seen:
            deduped.append(path)
            seen.add(path)
    return deduped


def _relative_target(path: Path) -> Path:
    return path.relative_to(PROJECT_ROOT)


def archive_candidates(archive_root: Path, paths: list[Path]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_root = archive_root / timestamp
    batch_root.mkdir(parents=True, exist_ok=False)

    manifest_entries = []
    for src in paths:
        rel = _relative_target(src)
        dst = batch_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        manifest_entries.append({
            "source": str(rel),
            "archived_to": str(dst.relative_to(batch_root)),
            "is_dir": dst.is_dir(),
        })

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entries": manifest_entries,
    }
    (batch_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return batch_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    candidates = _collect_candidates()
    print(f"[archive] candidates={len(candidates)}")
    for path in candidates:
        print(f"  - {path.relative_to(PROJECT_ROOT)}")

    if not args.apply:
        return

    batch_root = archive_candidates(args.archive_root.resolve(), candidates)
    print(f"[archive] moved {len(candidates)} entries -> {batch_root}")


if __name__ == "__main__":
    main()
