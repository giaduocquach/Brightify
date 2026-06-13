"""
Extract Vietnamese Sentence-BERT embeddings for lyrics (replaces PhoBERT mean-pool).

Problem with current PhoBERT mean-pool (core/emotion_analysis.py:encode_lyrics):
  avg pairwise cosine = 0.856 — severely anisotropic. BERT embeddings occupy a
  narrow cone in vector space; cosine similarity is nearly meaningless without
  contrastive training (SimCSE paper, Gao et al. EMNLP 2021).

Fix: dangvantuan/vietnamese-embedding — SimCSE contrastive-trained on Vietnamese,
  avg pairwise cosine = 0.587 (vs 0.856). Still 768-dim, PhoBERT backbone, but
  with proper cosine geometry for retrieval. Tested against 2 other VN models:
    vietnamese-sbert:               0.682
    sup-SimCSE-VietNamese-phobert:  0.701
    dangvantuan/vietnamese-embedding: 0.587  ← best

Output:
    data/vnsbert_embeddings.npy     (N, 768) float32, L2-normalised
    data/vnsbert_metadata.json      stats

Usage:
    python -m tools.extract_vnsbert_embeddings [--batch 64]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import config as cfg

MODEL_ID = "dangvantuan/vietnamese-embedding"
OUT_NPY  = str(cfg.DATA_DIR / "vnsbert_embeddings.npy")
OUT_META = str(cfg.DATA_DIR / "vnsbert_metadata.json")
DIM = 768


def run(batch_size: int = 64, verbose: bool = True) -> None:
    import pandas as pd
    from sentence_transformers import SentenceTransformer

    df = pd.read_csv(cfg.PROCESSED_FILE)
    n  = len(df)

    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"
    lyrics  = df[lyr_col].fillna("").astype(str).tolist()

    if verbose:
        print(f"[vnsbert] Model: {MODEL_ID}")
        print(f"[vnsbert] Songs: {n}  batch_size={batch_size}")

    os.environ.setdefault("HF_TOKEN", os.environ.get("HF_TOKEN", ""))

    t0 = time.time()
    model = SentenceTransformer(MODEL_ID)
    if verbose:
        print(f"[vnsbert] Model loaded in {time.time()-t0:.1f}s")

    t1 = time.time()
    embeddings = model.encode(
        lyrics,
        batch_size=batch_size,
        normalize_embeddings=True,   # L2-norm → cosine = dot product
        show_progress_bar=verbose,
        convert_to_numpy=True,
    )
    elapsed = time.time() - t1

    # Verify
    assert embeddings.shape == (n, DIM), f"Shape mismatch: {embeddings.shape}"
    norms = np.linalg.norm(embeddings, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4), "Not unit-norm"

    # Anisotropy check
    rng  = np.random.default_rng(42)
    idx  = rng.choice(n, size=min(500, n), replace=False)
    sub  = embeddings[idx]
    cos  = sub @ sub.T
    mask = ~np.eye(len(sub), dtype=bool)
    avg_cos = float(cos[mask].mean())

    np.save(OUT_NPY, embeddings.astype(np.float32))
    meta = {
        "model": MODEL_ID,
        "n_songs": n, "dim": DIM,
        "elapsed_s": round(elapsed, 1),
        "avg_pairwise_cosine": round(avg_cos, 4),
        "phobert_avg_cosine_baseline": 0.8563,
        "note": "SimCSE contrastive-trained; lower avg cosine = less anisotropic = better for retrieval",
    }
    with open(OUT_META, "w") as fh:
        json.dump(meta, fh, indent=2)

    if verbose:
        print(f"\n[vnsbert] Done in {elapsed:.1f}s")
        print(f"[vnsbert] avg pairwise cosine: {avg_cos:.4f}  (PhoBERT baseline: 0.8563)")
        print(f"[vnsbert] Saved → {OUT_NPY}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args(argv)
    os.chdir(str(PROJECT_ROOT))
    run(batch_size=args.batch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
