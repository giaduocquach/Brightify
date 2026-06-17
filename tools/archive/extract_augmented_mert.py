"""
Hướng B: Extract augmented MERT embeddings for contrastive training.

Literature (arXiv:2401.08889, ISMIR 2024):
  - Time-stretching = most effective augmentation for music similarity
  - Pitch-shift + time-stretch → model invariant to tempo/key, sensitive to genre/mood
  - Counterintuitive: pitch-shift↑ tempo sensitivity; time-stretch↑ pitch sensitivity

Positive pairs: MERT(original) + MERT(pitch_shifted ±2) or MERT(time_stretched 1.1x)
Cosine similarity: ~0.91 (pitch) / ~0.95 (time) → good positive pair quality

Output: data/mert_augmented_pairs.npz
  'anchors': (N, 768)   — original embeddings (same as mert_embeddings_multilayer)
  'positives': (N, 768)  — augmented version embeddings
  'aug_type': (N,)       — 0=pitch_shift, 1=time_stretch (alternating)

Usage: python -m tools.extract_augmented_mert [--workers 1]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import config as cfg

OUT_NPZ  = str(cfg.DATA_DIR / "mert_augmented_pairs.npz")
OUT_META = str(cfg.DATA_DIR / "mert_augmented_meta.json")


def _extract_one(args):
    idx, track_id, mp3_path, aug_type = args
    try:
        import librosa, torch
        from core.mert_encoder import MERTEncoder

        global _ENC
        if _ENC is None:
            _ENC = MERTEncoder(layers=list(range(1, 13)))
            _ENC._load()

        # Load original clip (same as extract_mert_multilayer)
        try:
            total_dur = librosa.get_duration(path=mp3_path)
        except Exception:
            total_dur = 180.0
        offset = min(30.0, max(0.0, total_dur * 0.15))
        wav, _ = librosa.load(mp3_path, sr=24000, mono=True, offset=offset, duration=15.0)
        if len(wav) < 400:
            return idx, track_id, None

        # Apply augmentation
        if aug_type == 0:
            wav_aug = librosa.effects.pitch_shift(wav, sr=24000, n_steps=2)
        else:
            wav_aug = librosa.effects.time_stretch(wav, rate=1.1)
            wav_aug = wav_aug[:len(wav)] if len(wav_aug) > len(wav) else wav_aug

        if len(wav_aug) < 400:
            return idx, track_id, None

        def _encode(w):
            t = torch.tensor(w.astype(np.float32)).unsqueeze(0)
            device = next(_ENC._model.parameters()).device
            t = t.to(device)
            with torch.no_grad():
                out = _ENC._model(t, output_hidden_states=True)
            stacked = torch.stack(list(out.hidden_states[1:13]), dim=0)
            emb = stacked.mean(0).mean(1).squeeze(0).cpu().numpy().astype(np.float32)
            n = float(np.linalg.norm(emb))
            return emb / n if n > 1e-9 else emb

        aug_emb = _encode(wav_aug)
        return idx, track_id, aug_emb

    except Exception as e:
        log.warning(f"  [{idx}] {track_id}: {e}")
        return idx, track_id, None


_ENC = None


def run(workers: int = 1, resume: bool = True) -> None:
    import time
    import pandas as pd

    df = pd.read_csv(cfg.PROCESSED_FILE)
    n = len(df)
    log.info(f"Catalog: {n} songs | augmentation: pitch_shift(even) / time_stretch(odd)")

    # Load anchor embeddings (original MERT multilayer)
    anchors = np.load(cfg.MERT_EMBEDDINGS_FILE).astype(np.float32)
    norms = np.linalg.norm(anchors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    anchors = anchors / norms

    positives = np.zeros_like(anchors)
    aug_types = np.zeros(n, dtype=np.int8)
    done_mask = np.zeros(n, dtype=bool)

    if resume and Path(OUT_NPZ).exists():
        saved = np.load(OUT_NPZ)
        if "positives" in saved and saved["positives"].shape == positives.shape:
            positives = saved["positives"]
            aug_types = saved.get("aug_type", aug_types)
            done_mask = np.linalg.norm(positives, axis=1) > 0.1
            log.info(f"Resuming: {done_mask.sum()}/{n} already done")

    music_dir = PROJECT_ROOT / "music_files"
    tasks = []
    for i, row in df.iterrows():
        if done_mask[i]:
            continue
        mp3 = music_dir / f"{row['track_id']}.mp3"
        if mp3.exists():
            tasks.append((int(i), str(row["track_id"]), str(mp3), int(i) % 2))

    log.info(f"Remaining: {len(tasks)}/{n}")
    if not tasks:
        log.info("All done.")
        return

    t0 = time.time()
    n_done = n_fail = 0

    def _init():
        global _ENC
        _ENC = None
        import os as _os
        _os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    if workers == 1:
        _init()
        for task in tasks:
            idx, tid, emb = _extract_one(task)
            if emb is not None:
                positives[idx] = emb
                aug_types[idx] = task[3]
                done_mask[idx] = True
                n_done += 1
            else:
                n_fail += 1
            total = n_done + n_fail
            if total % 50 == 0:
                np.savez(OUT_NPZ, anchors=anchors, positives=positives, aug_type=aug_types)
                elapsed = time.time() - t0
                rate = total / elapsed
                eta = (len(tasks) - total) / max(rate, 1e-6)
                log.info(f"  {total}/{len(tasks)}  ok={n_done} fail={n_fail}  "
                         f"{rate:.1f} s/s  eta={eta/60:.1f}min")

    np.savez(OUT_NPZ, anchors=anchors, positives=positives, aug_type=aug_types)
    meta = {"n_songs": n, "n_done": int(done_mask.sum()), "n_fail": n_fail,
            "aug_types": "0=pitch_shift(+2), 1=time_stretch(1.1x)",
            "elapsed_s": round(time.time() - t0, 1)}
    with open(OUT_META, "w") as fh:
        json.dump(meta, fh, indent=2)
    log.info(f"Done: {n_done}/{n}  fail={n_fail} → {OUT_NPZ}")


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
