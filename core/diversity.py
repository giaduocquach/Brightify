"""
Diversity-aware reranking: MMR and DPP.

MMR  — Carbonell & Goldstein 1998 (SIGIR)
DPP  — Chen et al. 2018 fast greedy MAP (arXiv 1709.05135)
"""

from __future__ import annotations

import numpy as np
from typing import List


def mmr_rerank(
    candidates: List[int],
    relevance: np.ndarray,
    emb_normalized: np.ndarray,
    top_k: int = 10,
    lambda_: float = 0.7,
) -> List[int]:
    """
    Maximal Marginal Relevance reranking.

    score(i) = λ·rel(i) − (1−λ)·max_{j∈S} cos(i, j)

    candidates   : global song indices of candidate pool
    relevance    : score per global index (shape = n_songs)
    emb_normalized: L2-normalised embedding matrix (n_songs × dim)
    """
    n = len(candidates)
    top_k = min(top_k, n)
    if n == 0:
        return []

    cand_arr = np.array(candidates)
    rel = relevance[cand_arr]              # (n,)
    vecs = emb_normalized[cand_arr]        # (n, dim) — already unit-norm
    sim_mat = vecs @ vecs.T               # (n, n) pairwise cosine sim

    selected: List[int] = []
    remaining = list(range(n))

    for _ in range(top_k):
        if not remaining:
            break
        if not selected:
            best_local = int(np.argmax(rel))
        else:
            sel = np.array(selected)
            # max sim to any already-selected candidate
            max_sim = sim_mat[:, sel].max(axis=1)   # (n,)
            mmr = lambda_ * rel - (1 - lambda_) * max_sim
            # restrict to remaining
            mmr_remaining = {i: mmr[i] for i in remaining}
            best_local = max(mmr_remaining, key=mmr_remaining.get)

        selected.append(best_local)
        remaining.remove(best_local)

    return [candidates[i] for i in selected]


def dpp_greedy_map(
    candidates: List[int],
    relevance: np.ndarray,
    emb_normalized: np.ndarray,
    top_k: int = 10,
) -> List[int]:
    """
    Fast Greedy MAP for Determinantal Point Process (Chen et al. 2018).

    P(S) ∝ det(L_S),  L_ij = sqrt(rel_i)·K_ij·sqrt(rel_j)
    K_ij = cosine_sim(i, j)  — quality-weighted RBF kernel on embeddings.
    """
    n = len(candidates)
    top_k = min(top_k, n)
    if n == 0:
        return []

    cand_arr = np.array(candidates)
    rel = np.clip(relevance[cand_arr], 1e-6, None)   # (n,) must be > 0
    vecs = emb_normalized[cand_arr]
    K = vecs @ vecs.T
    np.fill_diagonal(K, 1.0)

    r = np.sqrt(rel)
    L = np.outer(r, r) * K    # (n, n) quality-weighted kernel

    selected: List[int] = []
    remaining = list(range(n))
    di2 = np.diag(L).copy().astype(np.float64)
    c = np.zeros((n, top_k), dtype=np.float64)

    for step in range(top_k):
        if not remaining:
            break

        best_local = max(remaining, key=lambda i: di2[i])
        selected.append(best_local)
        remaining.remove(best_local)

        if step + 1 >= top_k or not remaining:
            break

        ei = L[:, best_local].astype(np.float64)
        if step > 0:
            ei -= c[:, :step] @ c[best_local, :step]

        d_best = np.sqrt(max(di2[best_local], 1e-10))
        c[:, step] = ei / d_best
        di2 -= c[:, step] ** 2
        di2 = np.maximum(di2, 0.0)

    return [candidates[i] for i in selected]
