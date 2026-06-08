"""
Extract MuQ-large audio embeddings for the full catalog (Phase 3).

MuQ (OpenMuQ/MuQ-large-msd-iter, Zhu et al. 2025, arXiv:2501.01108):
  - 12-layer transformer, 1024-dim hidden states (vs MERT-95M's 768-dim)
  - SOTA on MARBLE benchmark (avg 77.0), outperforms MERT on MIR tasks
  - Same 24kHz input as MERT — same clip strategy (2 clips/song @ 15s)
  - Multi-layer: mean across all 12 transformer hidden layers (same rationale
    as multilayer MERT — arXiv:2604.20847)

Output:
    data/muq_embeddings.npy          (N, 1024) float32, L2-normalised
    data/muq_metadata.json           index → track_id + stats

Drop-in with recommendation_engine.py: set MERT_EMBEDDINGS_FILE to this file.
Engine now accepts any dim (not hardcoded 768) — patched in Phase 3.

Usage:
    python -m tools.extract_muq_embeddings [--workers N] [--no-resume]
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

MUQ_MODEL_ID = "OpenMuQ/MuQ-large-msd-iter"
MUQ_EMBEDDINGS_FILE = str(cfg.DATA_DIR / "muq_embeddings.npy")
MUQ_METADATA_FILE   = str(cfg.DATA_DIR / "muq_metadata.json")
MUQ_DIM   = 1024
MUQ_SR    = 24_000
CLIP_DUR  = 15.0
LAYERS    = list(range(0, 13))   # all 13 hidden states including input embedding


# ── Worker ────────────────────────────────────────────────────────────────────

_MODEL = None


def _init_worker():
    global _MODEL
    import torch
    from dotenv import load_dotenv
    load_dotenv(os.path.join(str(PROJECT_ROOT), ".env"))
    token = os.environ.get("HF_TOKEN", "").strip()
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    from muq import MuQ
    log.info(f"[MuQ] Loading {MUQ_MODEL_ID} …")
    _MODEL = MuQ.from_pretrained(MUQ_MODEL_ID, token=token if token else None)
    _MODEL = _MODEL.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _MODEL = _MODEL.to(device)
    log.info(f"[MuQ] Ready on {device}")


def _extract_one(args: tuple) -> tuple:
    idx, track_id, mp3_path = args
    try:
        emb = _encode_mp3(mp3_path)
    except Exception as e:
        emb = None
        log.warning(f"  [{idx}] {track_id}: {e}")
    return idx, track_id, emb


def _encode_mp3(mp3_path: str) -> np.ndarray | None:
    import librosa, torch
    clip_len = int(CLIP_DUR * MUQ_SR)
    try:
        total_dur = librosa.get_duration(path=mp3_path)
    except Exception:
        total_dur = 180.0

    offsets = [min(30.0, max(0.0, total_dur * 0.15))]
    if total_dur > 90.0:
        offsets.append(min(75.0, total_dur * 0.45))

    device = next(_MODEL.parameters()).device
    clip_embs = []

    for offset in offsets:
        try:
            wav, _ = librosa.load(mp3_path, sr=MUQ_SR, mono=True,
                                  offset=offset, duration=CLIP_DUR)
        except Exception:
            continue
        if len(wav) < 400:
            continue

        wav_t = torch.tensor(wav, dtype=torch.float32).unsqueeze(0).to(device)
        with torch.no_grad():
            out = _MODEL(wav_t, output_hidden_states=True)
        # Mean across all hidden-state layers, then mean over time
        stacked = torch.stack(list(out.hidden_states), dim=0)  # (L, 1, T, D)
        emb = stacked.mean(0).mean(1).squeeze(0).cpu().numpy()  # (D,)
        clip_embs.append(emb)

    if not clip_embs:
        # Last-resort: first clip
        try:
            wav, _ = librosa.load(mp3_path, sr=MUQ_SR, mono=True, duration=CLIP_DUR)
            if len(wav) >= 400:
                wav_t = torch.tensor(wav, dtype=torch.float32).unsqueeze(0).to(device)
                with torch.no_grad():
                    out = _MODEL(wav_t, output_hidden_states=True)
                stacked = torch.stack(list(out.hidden_states), dim=0)
                emb = stacked.mean(0).mean(1).squeeze(0).cpu().numpy()
                clip_embs.append(emb)
        except Exception:
            return None

    if not clip_embs:
        return None

    song_emb = np.mean(clip_embs, axis=0).astype(np.float32)
    norm = float(np.linalg.norm(song_emb))
    if norm < 1e-9:
        return None
    return song_emb / norm


# ── Main ──────────────────────────────────────────────────────────────────────

def run(workers: int = 1, resume: bool = True) -> None:
    import pandas as pd

    df = pd.read_csv(cfg.PROCESSED_FILE)
    n  = len(df)
    log.info(f"Catalog: {n} songs  model={MUQ_MODEL_ID}  layers={len(LAYERS)}")

    out_npy  = Path(MUQ_EMBEDDINGS_FILE)
    out_meta = Path(MUQ_METADATA_FILE)

    if resume and out_npy.exists() and out_meta.exists():
        log.info(f"Resuming from {out_npy}")
        emb_matrix = np.load(str(out_npy))
        with open(out_meta) as fh:
            meta = json.load(fh)
        done_set = set(meta.get("done_track_ids", []))
    else:
        emb_matrix = np.zeros((n, MUQ_DIM), dtype=np.float32)
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
        log.info("All embeddings already extracted.")
        _finalize(emb_matrix, meta, out_npy, out_meta, n, 0, 0, 0.0)
        return

    t0 = time.time()
    n_done = n_fail = 0

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
                elapsed = time.time() - t0
                rate = total / elapsed
                eta = (len(tasks) - total) / max(rate, 1e-6)
                log.info(f"  {total}/{len(tasks)}  ok={n_done} fail={n_fail}  "
                         f"{rate:.1f} songs/s  eta={eta/60:.1f}min")
    else:
        import multiprocessing
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
        "model": MUQ_MODEL_ID,
        "layers": LAYERS,
        "strategy": "mean_all_hidden_states_then_time",
        "dim": MUQ_DIM,
        "elapsed_s": round(elapsed, 1),
    })
    with open(out_meta, "w") as fh:
        json.dump(meta, fh, indent=2)
    log.info(f"Done: {n_done}/{n} ({coverage:.1f}%)  fail={n_fail}  "
             f"elapsed={elapsed/60:.1f}min")
    log.info(f"Saved → {out_npy}")


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
