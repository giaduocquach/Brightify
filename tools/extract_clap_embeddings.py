"""
Hướng C: Extract CLAP zero-shot sub-genre embeddings (laion/larger_clap_music).

Research: LAION-CLAP 71% GTZAN genre accuracy, 71.9% human agreement on Inst-Sim-ABX.
CLAP trained on (audio, text) pairs → captures genre/mood conceptually.
Expected to distinguish sub-genres (rap/ballad/indie/pop) better than MERT.

laion/larger_clap_music: 630K audio-text pairs, music-domain focused.

Output: data/clap_embeddings.npy  (N, 512) L2-normalised audio embeddings
        data/clap_metadata.json

Usage: python -m tools.extract_clap_embeddings [--workers 1]
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

MODEL_ID     = "laion/larger_clap_music"
OUT_NPY      = str(cfg.DATA_DIR / "clap_embeddings.npy")
OUT_META     = str(cfg.DATA_DIR / "clap_metadata.json")
CLAP_SR      = 48_000   # CLAP native sample rate
CLIP_DUR     = 10.0     # seconds per clip


_CLAP_MODEL  = None
_CLAP_PROC   = None


def _init_clap():
    global _CLAP_MODEL, _CLAP_PROC
    if _CLAP_MODEL is not None:
        return
    from dotenv import load_dotenv
    load_dotenv(os.path.join(str(PROJECT_ROOT), ".env"))
    token = os.environ.get("HF_TOKEN", "").strip()

    from transformers import ClapModel, ClapProcessor
    log.info(f"[CLAP] Loading {MODEL_ID} …")
    _CLAP_PROC  = ClapProcessor.from_pretrained(MODEL_ID, token=token)
    _CLAP_MODEL = ClapModel.from_pretrained(MODEL_ID, token=token)
    _CLAP_MODEL.eval()
    log.info("[CLAP] Ready")


def _encode_mp3(mp3_path: str) -> np.ndarray | None:
    try:
        import librosa, torch

        _init_clap()

        # Load at CLAP native sample rate
        try:
            total_dur = librosa.get_duration(path=mp3_path)
        except Exception:
            total_dur = 180.0
        offset = min(30.0, max(0.0, total_dur * 0.15))

        wav, _ = librosa.load(mp3_path, sr=CLAP_SR, mono=True,
                              offset=offset, duration=CLIP_DUR)
        if len(wav) < 400:
            return None

        inputs = _CLAP_PROC(
            audio=wav, sampling_rate=CLAP_SR, return_tensors="pt"
        )
        with torch.no_grad():
            out = _CLAP_MODEL.get_audio_features(**inputs)
            emb_t = out if isinstance(out, torch.Tensor) else out.pooler_output
            emb = emb_t.cpu().numpy()[0]

        n = float(np.linalg.norm(emb))
        return emb.astype(np.float32) / n if n > 1e-9 else emb.astype(np.float32)

    except Exception as e:
        log.warning(f"  CLAP failed {mp3_path}: {e}")
        return None


def run(workers: int = 1, resume: bool = True) -> None:
    import pandas as pd

    df = pd.read_csv(cfg.PROCESSED_FILE)
    n  = len(df)
    log.info(f"Catalog: {n} songs | model={MODEL_ID}")

    # Init once to get embedding dim
    _init_clap()
    import torch
    dummy = np.zeros(int(CLAP_SR * CLIP_DUR), dtype=np.float32)
    inputs = _CLAP_PROC(audio=dummy, sampling_rate=CLAP_SR, return_tensors="pt")
    with torch.no_grad():
        out = _CLAP_MODEL.get_audio_features(**inputs)
        out_t = out if isinstance(out, torch.Tensor) else out.pooler_output
        dim = out_t.shape[1]
    log.info(f"[CLAP] Embedding dim: {dim}")

    # Resume
    emb_matrix = np.zeros((n, dim), dtype=np.float32)
    done_set: set = set()
    if resume and Path(OUT_NPY).exists():
        emb_matrix = np.load(OUT_NPY)
        if Path(OUT_META).exists():
            with open(OUT_META) as fh:
                meta = json.load(fh)
            done_set = set(meta.get("done_track_ids", []))
            log.info(f"Resuming: {len(done_set)}/{n} done")

    music_dir = PROJECT_ROOT / "music_files"
    tasks = []
    for i, row in df.iterrows():
        tid = str(row["track_id"])
        if tid in done_set:
            continue
        mp3 = music_dir / f"{tid}.mp3"
        if mp3.exists():
            tasks.append((int(i), tid, str(mp3)))

    log.info(f"Remaining: {len(tasks)}/{n}")
    if not tasks:
        log.info("All done.")
        return

    t0 = time.time()
    n_done = n_fail = 0

    for idx, tid, mp3_path in tasks:
        emb = _encode_mp3(mp3_path)
        if emb is not None:
            emb_matrix[idx] = emb
            done_set.add(tid)
            n_done += 1
        else:
            n_fail += 1

        total = n_done + n_fail
        if total % 50 == 0:
            np.save(OUT_NPY, emb_matrix)
            meta = {"done_track_ids": list(done_set), "n_done": n_done,
                    "n_fail": n_fail, "dim": dim, "model": MODEL_ID}
            with open(OUT_META, "w") as fh:
                json.dump(meta, fh, indent=2)
            elapsed = time.time() - t0
            rate = total / elapsed
            eta = (len(tasks) - total) / max(rate, 1e-6)
            log.info(f"  {total}/{len(tasks)}  ok={n_done} fail={n_fail}  "
                     f"{rate:.1f} songs/s  eta={eta/60:.1f}min")

    np.save(OUT_NPY, emb_matrix)
    elapsed = time.time() - t0
    coverage = len(done_set) / n * 100
    meta = {"done_track_ids": list(done_set), "model": MODEL_ID,
            "n_songs": n, "n_done": n_done, "n_fail": n_fail,
            "coverage_pct": round(coverage, 2), "dim": dim,
            "elapsed_s": round(elapsed, 1)}
    with open(OUT_META, "w") as fh:
        json.dump(meta, fh, indent=2)
    log.info(f"Done: {n_done}/{n} ({coverage:.1f}%)  fail={n_fail}  elapsed={elapsed/60:.1f}min")
    log.info(f"Saved → {OUT_NPY}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    args = ap.parse_args(argv)
    os.chdir(str(PROJECT_ROOT))
    run(workers=args.workers, resume=args.resume)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
