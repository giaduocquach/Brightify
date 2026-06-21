"""
Extract MERT multi-layer embeddings for the full catalog (Phase 1).

Mean across all 12 transformer hidden-state layers instead of single layer 8.
Literature: lower layers = timbre/pitch, middle = rhythm, upper = genre/emotion
(Li et al. 2023 probing; arXiv:2604.20847 — layer diversity complements single-layer).
Mean across layers is commutative with mean-over-time → output stays 768-dim,
fully drop-in compatible with existing cosine similarity code.

Output:
    data/mert_embeddings_multilayer.npy        (N, 768) float32 L2-normalised
    data/mert_metadata_multilayer.json         index → track_id + stats

Usage:
    python -m tools.extract_mert_multilayer [--workers N] [--no-resume]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config as cfg

LAYERS = list(range(1, 13))   # all 12 transformer layers


# ── worker (loads model once per process) ────────────────────────────────────

_ENC = None

def _init_worker():
    global _ENC
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from tools.mert_encoder import MERTEncoder
    _ENC = MERTEncoder(layers=LAYERS)
    _ENC._load()


def _extract_one(args: tuple) -> tuple:
    idx, track_id, mp3_path = args
    try:
        emb = _ENC.extract(mp3_path)
    except Exception as e:
        emb = None
        log.warning(f"  [{idx}] {track_id}: {e}")
    return idx, track_id, emb


# ── main ─────────────────────────────────────────────────────────────────────

def run(workers: int = 1, resume: bool = True) -> None:
    import multiprocessing
    import pandas as pd

    df = pd.read_csv(cfg.PROCESSED_FILE)
    n  = len(df)
    log.info(f"Catalog: {n} songs | multi-layer={LAYERS}")

    out_npy  = Path(cfg.MERT_EMBEDDINGS_MULTILAYER_FILE)
    out_meta = Path(cfg.MERT_EMBEDDINGS_MULTILAYER_META_FILE)

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

    music_dir = PROJECT_ROOT / "music_files"
    tasks = []
    for i, row in df.iterrows():
        tid = str(row["track_id"])
        if tid in done_set:
            continue
        mp3 = music_dir / f"{tid}.mp3"
        if mp3.exists():
            tasks.append((int(i), tid, str(mp3)))
        else:
            log.debug(f"  Missing MP3: {tid}")

    log.info(f"Remaining: {len(tasks)} / {n}  workers={workers}")
    if not tasks:
        log.info("Nothing to do — all embeddings already extracted.")
        _finalize(emb_matrix, meta, out_npy, out_meta, n, 0, 0, 0.0)
        return

    t0 = time.time()
    n_done = n_fail = 0

    def _progress():
        done = n_done + n_fail
        if done == 0:
            return
        elapsed = time.time() - t0
        rate    = done / elapsed
        eta_s   = (len(tasks) - done) / max(rate, 1e-6)
        log.info(f"  {done}/{len(tasks)}  ok={n_done} fail={n_fail}  "
                 f"{rate:.1f} songs/s  eta={eta_s/60:.1f}min")

    if workers == 1:
        _init_worker()
        for task in tasks:
            idx, tid, emb = _extract_one(task)
            if emb is not None:
                emb_matrix[idx] = emb
                meta["done_track_ids"].append(tid)
                n_done += 1
            else:
                n_fail += 1
            total = n_done + n_fail
            if total % 50 == 0:
                _checkpoint(emb_matrix, meta, out_npy, out_meta)
                _progress()
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
                if total % 50 == 0:
                    _checkpoint(emb_matrix, meta, out_npy, out_meta)
                    _progress()

    elapsed = time.time() - t0
    _checkpoint(emb_matrix, meta, out_npy, out_meta)
    _finalize(emb_matrix, meta, out_npy, out_meta, n, n_done, n_fail, elapsed)


def _checkpoint(matrix, meta, npy_path, meta_path):
    npy_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(npy_path), matrix)
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=2)


def _finalize(matrix, meta, out_npy, out_meta, n, n_done, n_fail, elapsed):
    coverage = (len(meta.get("done_track_ids", [])) / n * 100) if n else 0
    meta.update({
        "n_songs": n, "n_done": n_done, "n_fail": n_fail,
        "coverage_pct": round(coverage, 2),
        "model": cfg.MERT_MODEL,
        "layers": LAYERS,
        "strategy": "mean_across_layers_then_time",
        "dim": 768,
        "elapsed_s": round(elapsed, 1),
    })
    with open(out_meta, "w") as fh:
        json.dump(meta, fh, indent=2)
    log.info(f"Done: {n_done}/{n} ({coverage:.1f}%)  fail={n_fail}  "
             f"elapsed={elapsed/60:.1f}min")
    log.info(f"Saved: {out_npy}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers",   type=int, default=1)
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    args = ap.parse_args(argv)
    os.chdir(str(PROJECT_ROOT))
    run(workers=args.workers, resume=args.resume)
    return 0


if __name__ == "__main__":
    sys.exit(main())
