"""
Pillar F — KG embedding builder (v2: CONTENT-similarity graph).

Builds a 64-dim "musical neighbourhood" embedding for every song from a
k-NN content-similarity graph, NOT from artist/album co-membership.

Why the rewrite (2026-05-29):
  The v1 builder used an artist-album bipartite graph. Empirically the
  resulting embedding was ~100% artist identity (same-artist cosine ≈ 0.99)
  and the pillar-f-xartist backtest showed its gain COLLAPSED on cross-artist
  pairs ("CIRCULARITY LIKELY"). It made recommend_by_song prefer songs by the
  same artist regardless of how they actually sound. See
  docs/MASTER_UPGRADE_PLAN_V10.md §6.3.

v2 captures MUSICAL similarity instead, fusing the content modalities the
catalogue already has:
  - MERT audio embedding (Li et al. 2023)        — spectral/timbral character
  - mood_tags     (Essentia tag distribution)    — perceived mood
  - instrument_tags (Essentia tag distribution)  — instrumentation
  - core audio features (valence/energy/...)      — coarse musical shape

Each modality is L2-normalised into its own block, the blocks are weighted
and concatenated, a symmetric k-NN graph is built on cosine similarity, and
Truncated SVD on the affinity matrix yields a 64-dim community embedding.
No artist/album edges → no same-artist bias.

Output: data/kg_embeddings.npy  (n_songs × KG_DIM, float32, L2-normalised)
        data/kg_embeddings_meta.json

Usage:
    python -m tools.build_kg_embeddings
    python -m tools.build_kg_embeddings --neighbors 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

CSV_PATH = cfg.PROCESSED_FILE
OUT_EMB = "data/kg_embeddings.npy"
OUT_META = "data/kg_embeddings_meta.json"

# Per-modality block weights (applied after each block is L2-normalised).
# E2 (2026-05-30): "audio" block removed — ablation on 1050 GT queries showed
# all 6 metrics (NDCG/Prec/Recall/MRR/ILD/SameArtist) changed ≤ 0.0001 without
# it. MERT already captures audio shape; coarse-scalar block is redundant here.
# mood redistributed from 0.20→0.25, instrument 0.20→0.25 to keep Σ=1.
MODALITY_WEIGHTS = {"mert": 0.50, "mood": 0.25, "instrument": 0.25}
DEFAULT_NEIGHBORS = 25

# Coarse audio-shape features (must exist in the processed CSV).
_AUDIO_COLS = [
    "valence", "energy", "danceability", "acousticness",
    "instrumentalness", "arousal", "timbre_bright",
]


def _l2(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


def _tag_matrix(series: pd.Series) -> np.ndarray:
    """Parse a column of JSON tag dicts (e.g. {"slow":0.12,...}) → dense matrix
    over the union vocabulary. Missing/invalid → zero row."""
    parsed: list[dict] = []
    vocab: dict[str, int] = {}
    for raw in series:
        d = {}
        if isinstance(raw, str) and raw.strip():
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    d = {str(k): float(v) for k, v in obj.items()}
            except (ValueError, TypeError):
                d = {}
        for k in d:
            if k not in vocab:
                vocab[k] = len(vocab)
        parsed.append(d)
    mat = np.zeros((len(parsed), max(len(vocab), 1)), dtype=np.float32)
    for i, d in enumerate(parsed):
        for k, v in d.items():
            mat[i, vocab[k]] = v
    return mat


def _build_content_matrix(df: pd.DataFrame) -> np.ndarray:
    """Fuse available content modalities into one weighted, L2-normalised matrix."""
    n = len(df)
    blocks: list[np.ndarray] = []

    # --- MERT (positional alignment with the same CSV the recommender loads) ---
    if os.path.exists(cfg.MERT_EMBEDDINGS_FILE):
        mert = np.load(cfg.MERT_EMBEDDINGS_FILE)
        if mert.shape[0] == n:
            blocks.append(_l2(mert.astype(np.float32)) * MODALITY_WEIGHTS["mert"])
            logger.info(f"[KG] MERT block {mert.shape} (w={MODALITY_WEIGHTS['mert']})")
        else:
            logger.warning(f"[KG] MERT shape {mert.shape} != {n} songs — skipping MERT block")

    # --- Essentia tag distributions ---
    if "mood_tags" in df.columns:
        mood = _tag_matrix(df["mood_tags"])
        blocks.append(_l2(mood) * MODALITY_WEIGHTS["mood"])
        logger.info(f"[KG] mood_tags block {mood.shape} (w={MODALITY_WEIGHTS['mood']})")
    if "instrument_tags" in df.columns:
        inst = _tag_matrix(df["instrument_tags"])
        blocks.append(_l2(inst) * MODALITY_WEIGHTS["instrument"])
        logger.info(f"[KG] instrument_tags block {inst.shape} (w={MODALITY_WEIGHTS['instrument']})")

    # --- Coarse audio shape (E2: removed — ablation showed ≤0.0001 impact) ---
    if "audio" in MODALITY_WEIGHTS and MODALITY_WEIGHTS["audio"] > 0:
        audio_cols = [c for c in _AUDIO_COLS if c in df.columns]
        if audio_cols:
            audio = df[audio_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(np.float32)
            blocks.append(_l2(audio) * MODALITY_WEIGHTS["audio"])
            logger.info(f"[KG] audio block {audio.shape} cols={audio_cols} (w={MODALITY_WEIGHTS['audio']})")

    if not blocks:
        raise RuntimeError("[KG] No content modalities available — cannot build content graph.")

    content = np.hstack(blocks).astype(np.float32)
    logger.info(f"[KG] Fused content matrix: {content.shape}")
    return content


def build_kg_embeddings(df: pd.DataFrame, dim: int = 64, n_neighbors: int = DEFAULT_NEIGHBORS) -> np.ndarray:
    """Return (n_songs, dim) L2-normalised content-community KG embeddings."""
    from scipy.sparse import csr_matrix
    from sklearn.decomposition import TruncatedSVD
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import normalize

    n = len(df)
    content = _build_content_matrix(df)

    # --- k-NN graph on cosine similarity ---
    k = min(n_neighbors, n - 1)
    logger.info(f"[KG] Building k-NN content graph (k={k}) for {n} songs ...")
    nn = NearestNeighbors(n_neighbors=k + 1, metric="cosine", algorithm="brute")
    nn.fit(content)
    dist, idx = nn.kneighbors(content)  # (n, k+1); col 0 is self

    rows_, cols_, data_ = [], [], []
    for i in range(n):
        for j_pos in range(1, idx.shape[1]):  # skip self at col 0
            j = int(idx[i, j_pos])
            sim = float(1.0 - dist[i, j_pos])  # cosine similarity
            if sim <= 0:
                continue
            # symmetric affinity
            rows_.append(i); cols_.append(j); data_.append(sim)
            rows_.append(j); cols_.append(i); data_.append(sim)
    affinity = csr_matrix((data_, (rows_, cols_)), shape=(n, n), dtype=np.float32)
    logger.info(f"[KG] Affinity matrix {affinity.shape}, nnz={affinity.nnz}")

    # --- Truncated SVD → low-dim community embedding ---
    actual_dim = min(dim, n - 1)
    svd = TruncatedSVD(n_components=actual_dim, random_state=cfg.RANDOM_SEED)
    emb = svd.fit_transform(affinity).astype(np.float32)
    if emb.shape[1] < dim:
        emb = np.hstack([emb, np.zeros((n, dim - emb.shape[1]), dtype=np.float32)])
    emb = normalize(emb, norm="l2").astype(np.float32)
    logger.info(f"[KG] Embeddings {emb.shape}  (explained variance: "
                f"{svd.explained_variance_ratio_.sum()*100:.1f}%)")
    return emb


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--neighbors", type=int, default=DEFAULT_NEIGHBORS, help="k for the content k-NN graph")
    args = ap.parse_args()

    df = pd.read_csv(CSV_PATH)
    emb = build_kg_embeddings(df, dim=cfg.KG_DIM, n_neighbors=args.neighbors)
    np.save(OUT_EMB, emb)
    meta = {
        "n_songs": len(df),
        "dim": emb.shape[1],
        "csv_path": CSV_PATH,
        "method": "content-knn-svd",
        "modalities": list(MODALITY_WEIGHTS.keys()),
        "modality_weights": MODALITY_WEIGHTS,
        "n_neighbors": args.neighbors,
        "date": str(__import__("datetime").date.today()),
    }
    with open(OUT_META, "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"[KG] Saved {OUT_EMB}  ({emb.shape})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
