"""Acoustically-coherent on-mood selection for recommend-by-color (V37).
Extracted verbatim from MusicRecommender (behaviour-preserving) — the recommender
passes its precomputed matrices/arrays in. Determinism: float64 greedy centroid
cascade + argsort_desc_stable tie-break preserved exactly."""
import numpy as np
from core.ranking._stable import argsort_desc_stable


def coherent_cluster_select(scores, top_k, diversity_penalty, *,
                            mert, artists, cover_excl, alpha, overfetch):
    """V-A relevance (`scores`) picks the colour's mood region; MERT cosine to the
    growing set's centroid makes the chosen songs an acoustically tight cluster.

    `mert`: full (n_songs, D) centred-or-raw L2-normalised audio matrix.
    `artists`: full per-song artist array (or None). `cover_excl`: {global_idx: {blocked idxs}}.
    `alpha` = COLOR_COHERENCE_ALPHA, `overfetch` = COLOR_COHERENCE_OVERFETCH.
    """
    n_songs = len(scores)
    n_cand = min(top_k * overfetch, n_songs)
    cand = argsort_desc_stable(scores, n_cand)              # top V-A candidates (global idx)
    rel = scores[cand].astype(float)
    rel = (rel - rel.min()) / (rel.max() - rel.min() + 1e-9)   # → [0,1]
    # float64: the coherence matmul drives a greedy cascade (one different pick shifts the
    # centroid → whole list diverges). float32 BLAS differs ~1e-5 across CPUs; float64 → ~1e-13.
    M = mert[cand].astype(np.float64)                       # (n_cand, D), L2-normalised

    selected: list = []          # local indices into `cand`
    remaining = list(range(len(cand)))
    blocked: set = set()         # global idxs blocked by the cover filter
    artist_counts: dict = {}
    centroid = None

    while len(selected) < top_k and remaining:
        if centroid is None:
            combo = rel[remaining].copy()                  # seed = best V-A song
        else:
            coh = M[remaining] @ centroid                  # cosine (M is normalised)
            combo = alpha * rel[remaining] + (1.0 - alpha) * coh
        if diversity_penalty > 0 and artists is not None:
            for j, li in enumerate(remaining):
                cnt = artist_counts.get(artists[cand[li]], 0)
                if cnt:
                    combo[j] *= max(0.0, 1.0 - diversity_penalty * min(cnt, 3))
        pick = None
        for j in argsort_desc_stable(combo):
            li = remaining[int(j)]
            if int(cand[li]) in blocked:
                continue
            pick = li
            break
        if pick is None:
            break
        selected.append(pick)
        remaining.remove(pick)
        gi = int(cand[pick])
        sel_M = M[selected].mean(0)
        centroid = sel_M / (np.linalg.norm(sel_M) + 1e-9)
        if artists is not None:
            a = artists[gi]
            artist_counts[a] = artist_counts.get(a, 0) + 1
        blocked |= cover_excl.get(gi, set())

    return [int(cand[li]) for li in selected]
