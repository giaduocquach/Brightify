"""
Batch MERT embedding extraction for the full catalog.

Usage:
    python -m tools.extract_mert_embeddings
    python -m tools.extract_mert_embeddings --workers 4 --resume

Outputs:
    data/mert_embeddings.npy         (N, 768) float32 L2-normalised
    data/mert_metadata.json          index → track_id mapping + stats
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config as cfg


# ──────────────────────────────────────────────────────────────────────────────
# Worker (runs in its own process — loads MERT once per worker)
# ──────────────────────────────────────────────────────────────────────────────

def _init_worker():
    """Called once in each worker process to load the MERT model."""
    global _ENC
    # Suppress HF progress bars in sub-processes
    os.environ.setdefault("HF_DATASETS_OFFLINE", "0")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from core.mert_encoder import MERTEncoder
    _ENC = MERTEncoder()
    _ENC._load()


def _extract_one(args: tuple) -> tuple:
    """(idx, track_id, mp3_path) → (idx, track_id, emb|None)"""
    idx, track_id, mp3_path = args
    try:
        emb = _ENC.extract(mp3_path)
    except Exception as e:
        emb = None
        log.warning(f"  [{idx}] {track_id}: {e}")
    return idx, track_id, emb


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def run(workers: int = 1, resume: bool = True) -> None:
    import pandas as pd

    # Load catalog
    df = pd.read_csv(cfg.PROCESSED_FILE)
    n = len(df)
    log.info(f"Catalog: {n} songs")

    out_npy  = Path(cfg.MERT_EMBEDDINGS_FILE)
    out_meta = Path(cfg.MERT_EMBEDDINGS_META_FILE)

    # Partial results buffer
    if resume and out_npy.exists() and out_meta.exists():
        log.info(f"Resuming from {out_npy}")
        emb_matrix = np.load(str(out_npy))
        with open(out_meta) as fh:
            meta = json.load(fh)
        done_set = set(meta.get("done_track_ids", []))
    else:
        emb_matrix = np.zeros((n, 768), dtype=np.float32)
        meta       = {"done_track_ids": []}
        done_set   = set()

    # Build task list
    music_dir = PROJECT_ROOT / "music_files"
    tasks = []
    for i, row in df.iterrows():
        tid = row["track_id"]
        if tid in done_set:
            continue
        mp3 = music_dir / f"{tid}.mp3"
        if mp3.exists():
            tasks.append((int(i), tid, str(mp3)))
        else:
            log.warning(f"  Missing MP3 for {tid}")

    log.info(f"Remaining: {len(tasks)} / {n}  (workers={workers})")
    if not tasks:
        log.info("Nothing to do.")
        return

    t_start = time.time()
    n_done = 0
    n_fail = 0

    if workers == 1:
        # Single-process: initialise encoder in main process
        _init_worker()
        for task in tasks:
            idx, tid, emb = _extract_one(task)
            if emb is not None:
                emb_matrix[idx] = emb
                meta["done_track_ids"].append(tid)
                n_done += 1
            else:
                n_fail += 1

            if (n_done + n_fail) % 100 == 0:
                _checkpoint(emb_matrix, meta, out_npy, out_meta)
                elapsed = time.time() - t_start
                rate = (n_done + n_fail) / elapsed
                remaining = (len(tasks) - n_done - n_fail) / max(rate, 1e-6)
                log.info(
                    f"  {n_done+n_fail}/{len(tasks)}  "
                    f"ok={n_done} fail={n_fail}  "
                    f"eta={remaining/60:.1f}min"
                )
    else:
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(processes=workers, initializer=_init_worker) as pool:
            for idx, tid, emb in pool.imap_unordered(_extract_one, tasks, chunksize=4):
                if emb is not None:
                    emb_matrix[idx] = emb
                    meta["done_track_ids"].append(tid)
                    n_done += 1
                else:
                    n_fail += 1

                total = n_done + n_fail
                if total % 100 == 0:
                    _checkpoint(emb_matrix, meta, out_npy, out_meta)
                    elapsed = time.time() - t_start
                    rate = total / elapsed
                    remaining = (len(tasks) - total) / max(rate, 1e-6)
                    log.info(
                        f"  {total}/{len(tasks)}  "
                        f"ok={n_done} fail={n_fail}  "
                        f"eta={remaining/60:.1f}min"
                    )

    # Final save
    _checkpoint(emb_matrix, meta, out_npy, out_meta)
    elapsed = time.time() - t_start
    coverage = n_done / n * 100

    # Write final metadata
    meta.update({
        "n_songs": n,
        "n_done": n_done,
        "n_fail": n_fail,
        "coverage_pct": round(coverage, 2),
        "model": cfg.MERT_MODEL,
        "layer": cfg.MERT_LAYER,
        "clip_duration_s": cfg.MERT_CLIP_DURATION,
        "dim": 768,
        "elapsed_s": round(elapsed, 1),
    })
    with open(out_meta, "w") as fh:
        json.dump(meta, fh, indent=2)

    log.info(
        f"Done: {n_done}/{n} ({coverage:.1f}%) in {elapsed/60:.1f}min  "
        f"| fail={n_fail}"
    )
    log.info(f"Saved: {out_npy}  {out_meta}")


def _checkpoint(matrix: np.ndarray, meta: dict, npy_path: Path, meta_path: Path) -> None:
    npy_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(npy_path), matrix)
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=2)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of parallel worker processes (default: 1)")
    parser.add_argument("--no-resume", dest="resume", action="store_false",
                        help="Start fresh (ignore existing partial results)")
    args = parser.parse_args(argv)

    os.chdir(str(PROJECT_ROOT))
    run(workers=args.workers, resume=args.resume)
    return 0


if __name__ == "__main__":
    sys.exit(main())
