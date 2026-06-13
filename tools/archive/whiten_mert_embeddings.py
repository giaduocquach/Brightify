"""
Fix MERT embedding anisotropy via mean-centering (All-but-the-Top, Mu et al. 2018).

Problem: MERT multilayer embeddings have avg pairwise cosine = 0.892 (σ=0.035).
  Signal range = max-min = 0.347. Only 0.035/0.347 = 10% of range is used for
  ranking. Most of the "cosine similarity" is shared cone offset (junk), not
  actual musical difference (signal).

Root cause: corpus mean vector norm = 0.945 — all embeddings point roughly in
  the same direction. Removing this shared offset via mean-centering + L2-renorm
  is the "All-but-the-Top" approach (Mu et al. 2018, All-but-the-Top: Simple
  and Effective Postprocessing for Word Representations).

After mean-centering:
  avg pairwise cosine ≈ 0.000 (σ=0.212), signal range = 1.491 (4.3× wider).
  Rankings change substantially because the cone offset no longer dominates.

Literature:
  Mu et al. 2018: "All-but-the-Top: Simple and Effective Postprocessing
    for Word Representations" — subtract mean + remove top PCs.
  Su et al. 2021 (arXiv:2103.15316): "Whitening Sentence Representations
    for Better Semantics and Faster Retrieval."
  Dev.to/gabrielanhaia: mean-centering is fastest and usually sufficient fix.

Output: data/mert_embeddings_centered.npy  (same shape, L2-normalised)
        data/mert_centered_metadata.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import config as cfg

OUT_NPY  = str(cfg.DATA_DIR / "mert_embeddings_centered.npy")
OUT_META = str(cfg.DATA_DIR / "mert_centered_metadata.json")


def pairwise_cosine_stats(emb: np.ndarray, n_sample: int = 1000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(emb), min(n_sample, len(emb)), replace=False)
    sub = emb[idx].astype(np.float64)
    cos = sub @ sub.T
    mask = ~np.eye(len(sub), dtype=bool)
    vals = cos[mask]
    return {
        "mean": round(float(vals.mean()), 4),
        "std":  round(float(vals.std()),  4),
        "min":  round(float(vals.min()),  4),
        "max":  round(float(vals.max()),  4),
        "range": round(float(vals.max() - vals.min()), 4),
    }


def center_embeddings(emb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Subtract corpus mean, L2-renorm. Returns (centered, mean_vec)."""
    mean_vec = emb.mean(axis=0)
    centered = emb.astype(np.float64) - mean_vec.astype(np.float64)
    norms = np.linalg.norm(centered, axis=1, keepdims=True)
    norms[norms < 1e-9] = 1.0
    return (centered / norms).astype(np.float32), mean_vec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=cfg.MERT_EMBEDDINGS_FILE,
                    help="Source MERT .npy (default: current MERT_EMBEDDINGS_FILE)")
    args = ap.parse_args(argv)

    os.chdir(str(PROJECT_ROOT))

    print(f"[whiten] Loading: {args.source}")
    emb = np.load(args.source).astype(np.float32)
    print(f"[whiten] Shape: {emb.shape}  mean_vec_norm={np.linalg.norm(emb.mean(0)):.4f}")

    print("[whiten] Before centering:")
    before = pairwise_cosine_stats(emb)
    for k, v in before.items():
        print(f"  {k}: {v}")

    print("\n[whiten] Applying mean-centering…")
    centered, mean_vec = center_embeddings(emb)

    print("[whiten] After centering:")
    after = pairwise_cosine_stats(centered)
    for k, v in after.items():
        print(f"  {k}: {v}")

    signal_gain = round(after["range"] / max(before["range"], 1e-9), 2)
    print(f"\n[whiten] Signal range gain: {before['range']:.4f} → {after['range']:.4f} ({signal_gain}×)")

    np.save(OUT_NPY, centered)
    meta = {
        "source": args.source,
        "method": "mean-centering (All-but-the-Top, Mu et al. 2018)",
        "mean_vec_norm_before": round(float(np.linalg.norm(mean_vec)), 4),
        "before": before,
        "after": after,
        "signal_gain": signal_gain,
        "n_songs": len(centered),
        "dim": centered.shape[1],
    }
    with open(OUT_META, "w") as fh:
        json.dump(meta, fh, indent=2)

    print(f"[whiten] Saved → {OUT_NPY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
