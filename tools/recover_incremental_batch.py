from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
RUN_ROOT = PROJECT_ROOT / "incremental_runs" / "20260606_142235" / "pipeline_new_only"
CHECKPOINT_DIR = RUN_ROOT / "checkpoints"
INCREMENTAL_DATA_DIR = RUN_ROOT / "data"
MAIN_DATA_DIR = PROJECT_ROOT / "data"
MUSIC_DIR = PROJECT_ROOT / "music_files"
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
BATCH_LIMIT = 100


def run_cmd(args: list[str], *, env: dict[str, str] | None = None) -> None:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    print("\n$", " ".join(args), flush=True)
    subprocess.run(args, cwd=str(PROJECT_ROOT), env=merged_env, check=True)


def count_mp3_progress() -> tuple[int, int]:
    phase2 = pd.read_csv(CHECKPOINT_DIR / "phase2_filtered.csv", usecols=["track_id"])
    mp3_ids = {p.stem for p in MUSIC_DIR.glob("*.mp3")}
    done = int(phase2["track_id"].astype(str).isin(mp3_ids).sum())
    return done, int(len(phase2) - done)


def write_pending_csv() -> tuple[Path, int]:
    phase2 = pd.read_csv(CHECKPOINT_DIR / "phase2_filtered.csv")
    mp3_ids = {p.stem for p in MUSIC_DIR.glob("*.mp3")}
    pending = phase2[~phase2["track_id"].astype(str).isin(mp3_ids)].copy()
    out = CHECKPOINT_DIR / "phase2_pending_mp3.csv"
    pending.to_csv(out, index=False, encoding="utf-8-sig")
    return out, len(pending)


def gate_remove_no_mp3() -> None:
    import tools.pipeline as pipeline

    pipeline.CHECKPOINT_DIR = CHECKPOINT_DIR
    pipeline.MUSIC_DIR = MUSIC_DIR
    if not pipeline.gate_remove_no_mp3():
        raise RuntimeError("gate_remove_no_mp3 failed")


def gate_remove_no_lyrics() -> None:
    import tools.pipeline as pipeline

    pipeline.CHECKPOINT_DIR = CHECKPOINT_DIR
    if not pipeline.gate_remove_no_lyrics():
        raise RuntimeError("gate_remove_no_lyrics failed")


def gate_remove_incomplete_features() -> None:
    import tools.pipeline as pipeline

    pipeline.CHECKPOINT_DIR = CHECKPOINT_DIR
    if not pipeline.gate_remove_incomplete_features():
        raise RuntimeError("gate_remove_incomplete_features failed")


def process_incremental() -> None:
    hf_env = {
        "HF_HOME": str(PROJECT_ROOT / "var" / "volumes" / "hf_cache"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    run_cmd(
        [
            str(PYTHON),
            "-m",
            "tools.process_data",
            "--input",
            str(CHECKPOINT_DIR / "phase5_features.csv"),
            "--output",
            str(INCREMENTAL_DATA_DIR / "vietnamese_music_processed_full.csv"),
            "--embeddings",
            str(INCREMENTAL_DATA_DIR / "vietnamese_music_embeddings_full.npy"),
            "--metadata",
            str(INCREMENTAL_DATA_DIR / "embeddings_metadata.json"),
            "--force",
        ],
        env=hf_env,
    )


def merge_into_main() -> int:
    main_csv = MAIN_DATA_DIR / "vietnamese_music_processed_full.csv"
    main_npy = MAIN_DATA_DIR / "vietnamese_music_embeddings_full.npy"
    main_meta = MAIN_DATA_DIR / "embeddings_metadata.json"
    inc_csv = INCREMENTAL_DATA_DIR / "vietnamese_music_processed_full.csv"
    inc_npy = INCREMENTAL_DATA_DIR / "vietnamese_music_embeddings_full.npy"
    inc_meta = INCREMENTAL_DATA_DIR / "embeddings_metadata.json"
    backup_dir = RUN_ROOT.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for src in (main_csv, main_npy, main_meta):
        shutil.copy2(src, backup_dir / f"{src.name}.{stamp}.bak")

    main_df = pd.read_csv(main_csv)
    inc_df = pd.read_csv(inc_csv)
    main_df["track_id"] = main_df["track_id"].astype(str)
    inc_df["track_id"] = inc_df["track_id"].astype(str)
    main_ids = set(main_df["track_id"])
    new_df = inc_df[~inc_df["track_id"].isin(main_ids)].copy().reset_index(drop=True)

    if new_df.empty:
        print("No new processed rows to merge.", flush=True)
        return 0

    main_emb = np.load(main_npy)
    inc_emb = np.load(inc_npy)
    with open(inc_meta, encoding="utf-8") as fh:
        inc_metadata = json.load(fh)
    inc_id_to_idx = {str(tid): i for i, tid in enumerate(inc_metadata["track_ids"])}
    new_indices = [inc_id_to_idx[tid] for tid in new_df["track_id"]]
    new_emb = inc_emb[new_indices]

    merged_df = pd.concat([main_df, new_df], ignore_index=True)
    merged_emb = np.concatenate([main_emb, new_emb], axis=0)

    merged_df.to_csv(main_csv, index=False, encoding="utf-8-sig")
    np.save(main_npy, merged_emb)
    new_meta = {
        "created_at": datetime.now().isoformat(),
        "model": "vinai/phobert-base-v2",
        "num_songs": int(len(merged_df)),
        "embedding_dim": int(merged_emb.shape[1]),
        "encoded_count": int(len(merged_df)),
        "fallback_count": 0,
        "track_ids": merged_df["track_id"].astype(str).tolist(),
        "track_names": merged_df["track_name"].astype(str).tolist(),
    }
    with open(main_meta, "w", encoding="utf-8") as fh:
        json.dump(new_meta, fh, ensure_ascii=False, indent=2)

    print(f"Merged +{len(new_df)} rows into main dataset.", flush=True)
    return int(len(new_df))


def seed_main_db() -> None:
    run_cmd([str(PYTHON), "-m", "db.seed"])


def run_cycle() -> tuple[int, int, int]:
    done_before, pending_before = count_mp3_progress()
    print(f"\n=== Cycle start | mp3_done={done_before} pending={pending_before} ===", flush=True)

    if pending_before > 0:
        pending_csv, pending_count = write_pending_csv()
        batch_limit = min(BATCH_LIMIT, pending_count)
        run_cmd(
            [
                str(PYTHON),
                "-m",
                "tools.download_music",
                "--input",
                str(pending_csv),
                "--workers",
                "1",
                "--delay",
                "4",
                "--skip-metadata",
                "--limit",
                str(batch_limit),
            ]
        )

    gate_remove_no_mp3()
    run_cmd(
        [
            str(PYTHON),
            "-m",
            "tools.collect_data",
            "--phase",
            "lyrics",
            "--resume",
            "--output-root",
            str(RUN_ROOT),
        ]
    )
    gate_remove_no_lyrics()
    run_cmd(
        [
            str(PYTHON),
            "-m",
            "tools.extract_audio_features",
            "--input",
            str(CHECKPOINT_DIR / "phase4_lyrics_gated.csv"),
            "--output",
            str(CHECKPOINT_DIR / "phase5_features.csv"),
            "--music-dir",
            "music_files",
            "--workers",
            "2",
            "--checkpoint-interval",
            "25",
        ]
    )
    gate_remove_incomplete_features()
    process_incremental()
    merged = merge_into_main()
    if merged:
        seed_main_db()

    done_after, pending_after = count_mp3_progress()
    print(
        f"=== Cycle end | mp3_done={done_after} pending={pending_after} merged={merged} ===",
        flush=True,
    )
    return done_before, pending_after, merged


def main() -> None:
    stagnant_cycles = 0

    while True:
        pending_before = count_mp3_progress()[1]
        done_before, pending_after, merged = run_cycle()

        if pending_after == 0:
            print("All pending MP3 tracks processed.", flush=True)
            break

        if pending_after >= pending_before and merged == 0:
            stagnant_cycles += 1
        else:
            stagnant_cycles = 0

        if stagnant_cycles >= 3:
            print("No further progress after 3 cycles. Stopping.", flush=True)
            break


if __name__ == "__main__":
    main()
