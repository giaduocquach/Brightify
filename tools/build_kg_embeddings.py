"""
Pillar F — KG embedding builder.

Constructs a 64-dim embedding for every song based on the artist-album
bipartite graph using Truncated SVD on a TF-IDF-weighted co-occurrence matrix.

Graph structure:
  - Song ↔ primary_artist (performs)
  - Song ↔ album_id       (in_album)
  - Song ↔ artist_ids     (featured artists, if multiple)

This captures artist community structure so songs from the same artist/album
cluster together in 64-dim space.  The resulting matrix can be used as a
lightweight collaboration signal in recommend_by_song.

Output: data/kg_embeddings.npy  (n_songs × KG_DIM, float32, L2-normalised)
        data/kg_embeddings_meta.json

Usage:
    python -m tools.build_kg_embeddings
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

CSV_PATH = cfg.PROCESSED_FILE
OUT_EMB  = "data/kg_embeddings.npy"
OUT_META = "data/kg_embeddings_meta.json"


def build_kg_embeddings(df: pd.DataFrame, dim: int = 64) -> np.ndarray:
    """Return (n_songs, dim) L2-normalised KG embeddings."""
    from scipy.sparse import csr_matrix
    from sklearn.decomposition import TruncatedSVD
    from sklearn.preprocessing import normalize

    n = len(df)
    logger.info(f"[KG] Building bipartite graph for {n} songs ...")

    # --- Build entity vocabulary ---
    # Entities: primary_artist + album_id (+ additional artist_ids)
    entities: list[str] = []
    entity_set: set[str] = set()

    def _add(e: str) -> None:
        if e and e not in entity_set:
            entity_set.add(e)
            entities.append(e)

    for _, row in df.iterrows():
        _add(f"artist:{row.get('primary_artist_id', row.get('primary_artist', ''))}")
        _add(f"album:{row.get('album_id', '')}")
        # Multi-artist (artist_ids is a single string like "UCxxxxx")
        aids = str(row.get("artist_ids", "") or "")
        for aid in aids.split(","):
            aid = aid.strip()
            if aid:
                _add(f"artist:{aid}")

    ent2idx = {e: i for i, e in enumerate(entities)}
    n_ent = len(entities)
    logger.info(f"[KG] {n_ent} unique entities (artists + albums)")

    # --- Build song-entity incidence matrix ---
    rows_, cols_, data_ = [], [], []
    for song_idx, row in df.iterrows():
        pos = int(song_idx)

        def _add_edge(e: str, weight: float = 1.0) -> None:
            eid = ent2idx.get(e)
            if eid is not None:
                rows_.append(pos)
                cols_.append(eid)
                data_.append(weight)

        _add_edge(f"artist:{row.get('primary_artist_id', row.get('primary_artist', ''))}", 1.5)
        _add_edge(f"album:{row.get('album_id', '')}", 1.0)
        for aid in str(row.get("artist_ids", "") or "").split(","):
            aid = aid.strip()
            if aid:
                _add_edge(f"artist:{aid}", 0.8)

    mat = csr_matrix((data_, (rows_, cols_)), shape=(n, n_ent), dtype=np.float32)
    logger.info(f"[KG] Incidence matrix: {mat.shape}, nnz={mat.nnz}")

    # --- TF-IDF weighting (down-weight highly shared entities) ---
    # IDF: log(n / (1 + count_per_entity))
    col_counts = np.asarray(mat.sum(axis=0)).ravel()
    idf = np.log(n / (1.0 + col_counts)).astype(np.float32)
    mat = mat.multiply(idf)

    # --- Truncated SVD → low-dim song embeddings ---
    actual_dim = min(dim, n_ent - 1, n - 1)
    svd = TruncatedSVD(n_components=actual_dim, random_state=cfg.RANDOM_SEED)
    emb = svd.fit_transform(mat).astype(np.float32)   # (n_songs, actual_dim)

    # Pad to dim if needed
    if emb.shape[1] < dim:
        pad = np.zeros((n, dim - emb.shape[1]), dtype=np.float32)
        emb = np.hstack([emb, pad])

    # L2-normalise
    emb = normalize(emb, norm="l2").astype(np.float32)
    logger.info(f"[KG] Embeddings shape: {emb.shape}  (explained variance: "
                f"{svd.explained_variance_ratio_.sum()*100:.1f}%)")
    return emb


def main() -> int:
    df = pd.read_csv(CSV_PATH)
    emb = build_kg_embeddings(df, dim=cfg.KG_DIM)
    np.save(OUT_EMB, emb)
    meta = {
        "n_songs": len(df),
        "dim": emb.shape[1],
        "csv_path": CSV_PATH,
        "method": "bipartite-svd",
        "date": str(__import__("datetime").date.today()),
    }
    with open(OUT_META, "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"[KG] Saved {OUT_EMB}  ({emb.shape})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
