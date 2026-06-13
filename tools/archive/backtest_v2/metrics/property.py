"""Group A property metrics (no ground truth needed). §8 — Phase 1.

Exact formulas as specified in §8 of PLAN_BACKTEST_METRICS.md.

  ILD_lyrics     — mean pairwise cosine distance (PhoBERT 768-dim)
  ILD_audio      — mean pairwise cosine distance (Essentia audio_matrix)
  ILD_va         — mean pairwise Euclidean distance (V-A 2-dim)
  ILD_color      — mean pairwise CIEDE2000 (from color_hex → CIE L*a*b*)
  Coverage       — |unique recs| / n_catalog
  Artist Gini    — Gini coefficient of artist exposure
  MoodCoherence  — 1 − mean_pairwise_VA_dist / √2
  TempoCoherence — 1 − CV(BPM) within top-K
  ColorCoherence — 1 − mean_pairwise_CIEDE2000 / 100
  Calibration    — KL(p_seed_emotion ‖ q_recs_emotion), α=0.01, 13-class
  Symmetry       — Jaccard overlap: B∈rec(A) ⇒ A∈rec(B)?
  Serendipity    — mean(1 − cosine_sim(rec_i, seed)), PhoBERT space
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# CIEDE2000 — pure NumPy, no colormath dependency
# ---------------------------------------------------------------------------

def _hex_to_lab(hex_color: str) -> Optional[np.ndarray]:
    """Convert #RRGGBB hex string to CIE L*a*b* (D65 illuminant).

    Returns None for invalid / empty strings.
    """
    hex_color = hex_color.strip()
    if not hex_color or hex_color[0] != '#' or len(hex_color) < 7:
        return None
    try:
        r = int(hex_color[1:3], 16) / 255.0
        g = int(hex_color[3:5], 16) / 255.0
        b = int(hex_color[5:7], 16) / 255.0
    except ValueError:
        return None

    # sRGB → linear RGB
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)

    # Linear RGB → XYZ (D65, sRGB matrix)
    X = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    Y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    Z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    # Normalise by D65 white point
    X /= 0.95047
    Y /= 1.00000
    Z /= 1.08883

    # XYZ → L*a*b*
    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    L = 116.0 * f(Y) - 16.0
    a = 500.0 * (f(X) - f(Y))
    b_ = 200.0 * (f(Y) - f(Z))
    return np.array([L, a, b_], dtype=float)


def _ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> float:
    """CIEDE2000 color difference between two L*a*b* arrays.

    Reference: CIE 2001, Sharma et al. (2005).
    """
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = math.sqrt(a1 * a1 + b1 * b1)
    C2 = math.sqrt(a2 * a2 + b2 * b2)
    C_avg = (C1 + C2) / 2.0
    C_avg7 = C_avg ** 7
    G = 0.5 * (1.0 - math.sqrt(C_avg7 / (C_avg7 + 25.0 ** 7)))
    a1p = a1 * (1.0 + G)
    a2p = a2 * (1.0 + G)
    C1p = math.sqrt(a1p * a1p + b1 * b1)
    C2p = math.sqrt(a2p * a2p + b2 * b2)

    h1p = math.degrees(math.atan2(b1, a1p)) % 360.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0.0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180.0:
        dhp = h2p - h1p
    elif h2p - h1p > 180.0:
        dhp = h2p - h1p - 360.0
    else:
        dhp = h2p - h1p + 360.0

    dHp = 2.0 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))

    Lp_avg = (L1 + L2) / 2.0
    Cp_avg = (C1p + C2p) / 2.0

    if C1p * C2p == 0.0:
        hp_avg = h1p + h2p
    elif abs(h1p - h2p) <= 180.0:
        hp_avg = (h1p + h2p) / 2.0
    elif h1p + h2p < 360.0:
        hp_avg = (h1p + h2p + 360.0) / 2.0
    else:
        hp_avg = (h1p + h2p - 360.0) / 2.0

    T = (1.0
         - 0.17 * math.cos(math.radians(hp_avg - 30.0))
         + 0.24 * math.cos(math.radians(2.0 * hp_avg))
         + 0.32 * math.cos(math.radians(3.0 * hp_avg + 6.0))
         - 0.20 * math.cos(math.radians(4.0 * hp_avg - 63.0)))

    SL = 1.0 + 0.015 * (Lp_avg - 50.0) ** 2 / math.sqrt(20.0 + (Lp_avg - 50.0) ** 2)
    SC = 1.0 + 0.045 * Cp_avg
    SH = 1.0 + 0.015 * Cp_avg * T

    Cp_avg7 = Cp_avg ** 7
    RC = 2.0 * math.sqrt(Cp_avg7 / (Cp_avg7 + 25.0 ** 7))
    d_theta = 30.0 * math.exp(-((hp_avg - 275.0) / 25.0) ** 2)
    RT = -math.sin(math.radians(2.0 * d_theta)) * RC

    dE = math.sqrt(
        (dLp / SL) ** 2 +
        (dCp / SC) ** 2 +
        (dHp / SH) ** 2 +
        RT * (dCp / SC) * (dHp / SH)
    )
    return dE


# ---------------------------------------------------------------------------
# ILD — Inter-List Diversity (§8 Group A)
# ---------------------------------------------------------------------------

def _mean_pairwise(vecs: np.ndarray, metric: str = 'cosine_dist') -> float:
    """Mean pairwise distance/similarity for a matrix of row vectors.

    metric:
      'cosine_dist' — 1 - cosine_similarity (pre-normalised input)
      'euclidean'   — Euclidean distance
    """
    k = len(vecs)
    if k < 2:
        return 0.0

    total = 0.0
    count = 0
    for i in range(k):
        for j in range(i + 1, k):
            if metric == 'cosine_dist':
                sim = float(np.dot(vecs[i], vecs[j]))
                sim = max(-1.0, min(1.0, sim))
                total += 1.0 - sim
            else:
                total += float(np.linalg.norm(vecs[i] - vecs[j]))
            count += 1

    return total / count if count > 0 else 0.0


def ild_lyrics(recs: Sequence[int], catalog: Any) -> float:
    """Mean pairwise cosine distance in PhoBERT embedding space."""
    if catalog.embeddings_normalized is None or len(recs) < 2:
        return 0.0
    vecs = catalog.embeddings_normalized[np.array(recs)]
    return _mean_pairwise(vecs, 'cosine_dist')


def ild_audio(recs: Sequence[int], catalog: Any) -> float:
    """Mean pairwise cosine distance in audio feature space."""
    if len(recs) < 2:
        return 0.0
    raw = catalog.audio_matrix[np.array(recs)]
    # L2-normalise rows for cosine distance
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = raw / norms
    return _mean_pairwise(vecs, 'cosine_dist')


def ild_va(recs: Sequence[int], catalog: Any) -> float:
    """Mean pairwise Euclidean distance in V-A 2-dim space."""
    if len(recs) < 2:
        return 0.0
    vecs = catalog.song_va[np.array(recs)]
    return _mean_pairwise(vecs, 'euclidean')


def ild_color(recs: Sequence[int], catalog: Any) -> float:
    """Mean pairwise CIEDE2000 in CIE L*a*b* color space."""
    if len(recs) < 2:
        return 0.0
    labs = [_hex_to_lab(catalog.color_hex[i]) for i in recs]
    labs = [l for l in labs if l is not None]
    if len(labs) < 2:
        return 0.0

    total = 0.0
    count = 0
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            total += _ciede2000(labs[i], labs[j])
            count += 1
    return total / count if count > 0 else 0.0


# ---------------------------------------------------------------------------
# Coverage + Artist Gini (global, over all queries)
# ---------------------------------------------------------------------------

def catalog_coverage(all_recs: Sequence[Sequence[int]], n_catalog: int) -> float:
    """Fraction of catalog exposed: |unique recs| / n_catalog."""
    unique = set()
    for recs in all_recs:
        unique.update(recs)
    return len(unique) / n_catalog if n_catalog > 0 else 0.0


def artist_gini(all_recs: Sequence[Sequence[int]], catalog: Any) -> float:
    """Gini coefficient of artist exposure across all recommendations.

    Higher Gini = more concentrated on a few artists (less equitable).
    Lower Gini (→ 0) = each artist appears equally often.
    """
    if catalog.artist_col is None:
        return 0.0

    counts: Dict[str, int] = Counter()
    for recs in all_recs:
        for idx in recs:
            artist = str(catalog.df[catalog.artist_col].iloc[idx])
            counts[artist] += 1

    if not counts:
        return 0.0

    x = np.array(sorted(counts.values()), dtype=float)
    n = len(x)
    total = float(x.sum())
    if total == 0:
        return 0.0

    # Relative mean absolute difference formula: G = sum_{i,j} |xi-xj| / (2*n*total)
    abs_diffs = np.abs(x[:, None] - x[None, :])
    G = float(abs_diffs.sum()) / (2.0 * n * total)
    return G


# ---------------------------------------------------------------------------
# Coherence metrics (§8)
# ---------------------------------------------------------------------------

def mood_coherence(recs: Sequence[int], catalog: Any) -> float:
    """1 − mean_pairwise_VA_dist / √2. Range [0,1]; higher = more coherent."""
    if len(recs) < 2:
        return 1.0
    vecs = catalog.song_va[np.array(recs)]
    mean_dist = _mean_pairwise(vecs, 'euclidean')
    return max(0.0, 1.0 - mean_dist / math.sqrt(2.0))


def tempo_coherence(recs: Sequence[int], catalog: Any) -> float:
    """1 − CV(BPM) within top-K. CV = std/mean. Clipped to [0, 1]."""
    if len(recs) < 2:
        return 1.0
    tempos = catalog.tempo[np.array(recs)]
    mean_t = float(np.mean(tempos))
    if mean_t <= 0:
        return 1.0
    cv = float(np.std(tempos, ddof=0)) / mean_t
    return max(0.0, 1.0 - cv)


def color_coherence(recs: Sequence[int], catalog: Any) -> float:
    """1 − mean_pairwise_CIEDE2000 / 100. Range [0,1]; higher = more coherent."""
    mean_de = ild_color(recs, catalog)
    return max(0.0, 1.0 - mean_de / 100.0)


# ---------------------------------------------------------------------------
# Calibration error (§8, Steck 2018)
# ---------------------------------------------------------------------------

def calibration_error(recs: Sequence[int], seed_idx: int, catalog: Any) -> float:
    """KL(p_seed_emotion ‖ q_recs_emotion) with Laplace smoothing α=0.01.

    p_seed = emotion vector of the seed song.
    q_recs = mean emotion vector over the recommendation list.
    Both vectors are over n_emotions classes (typically ~13 from color mapper).
    """
    if len(recs) == 0:
        return 0.0

    alpha = 0.01
    p_raw = catalog.song_emotion_vec[seed_idx].copy()
    q_raw = catalog.song_emotion_vec[np.array(recs)].mean(axis=0)

    # Laplace smooth + renormalise
    def smooth(v: np.ndarray) -> np.ndarray:
        v = v + alpha
        return v / v.sum()

    p = smooth(p_raw)
    q = smooth(q_raw)

    # KL(P||Q) = sum P * log(P/Q)
    kl = float(np.sum(p * np.log(p / q)))
    return max(0.0, kl)


# ---------------------------------------------------------------------------
# Similar-song symmetry (Jaccard)
# ---------------------------------------------------------------------------

def similar_song_symmetry(
    recommend_fn,
    seeds: Sequence[int],
    top_k: int,
) -> float:
    """Mean Jaccard overlap: B∈rec(A) ⇒ A∈rec(B).

    For each seed A, draw a random B from rec(A), compute
    Jaccard(rec(A), rec(B)). Return the mean over all seeds.
    """
    if not seeds:
        return 0.0

    rng = np.random.default_rng(42)
    jaccards: List[float] = []

    for a in seeds:
        recs_a = set(recommend_fn(a, top_k))
        if not recs_a:
            continue
        # Pick a random neighbour B
        b = int(rng.choice(list(recs_a)))
        recs_b = set(recommend_fn(b, top_k))
        if not recs_b:
            continue
        inter = len(recs_a & recs_b)
        union = len(recs_a | recs_b)
        jaccards.append(inter / union if union > 0 else 0.0)

    return float(np.mean(jaccards)) if jaccards else 0.0


# ---------------------------------------------------------------------------
# Content-serendipity proxy
# ---------------------------------------------------------------------------

def serendipity_proxy(recs: Sequence[int], seed_idx: int, catalog: Any) -> float:
    """mean(1 − cosine_sim(rec_i, seed)) in PhoBERT embedding space.

    Falls back to V-A Euclidean if no embeddings available.
    """
    if len(recs) == 0:
        return 0.0

    if catalog.embeddings_normalized is not None:
        seed_vec = catalog.embeddings_normalized[seed_idx]
        rec_vecs = catalog.embeddings_normalized[np.array(recs)]
        sims = rec_vecs @ seed_vec
        sims = np.clip(sims, -1.0, 1.0)
        return float(np.mean(1.0 - sims))
    else:
        # V-A fallback: mean Euclidean distance to seed (no normalisation needed)
        seed_va = catalog.song_va[seed_idx]
        rec_va = catalog.song_va[np.array(recs)]
        dists = np.linalg.norm(rec_va - seed_va, axis=1)
        return float(np.mean(dists))


def same_artist_at_k(recs: Sequence[int], seed_idx: int, catalog: Any) -> float:
    """GT-3 — fraction of top-K recs that share the SEED's artist.

    Similar-song bias metric: high = the recommender mostly returns the same
    artist (the artist-bias symptom F6 fixed). Distinct from artist_gini (global
    exposure equity) — this is "same-as-this-seed". Lower is generally healthier
    for content similarity, though a stylistically consistent artist legitimately
    yields some same-artist neighbours (see §6.3.1).
    """
    if catalog.artist_col is None or len(recs) == 0:
        return 0.0
    col = catalog.df[catalog.artist_col]
    seed_artist = str(col.iloc[seed_idx])
    if not seed_artist or seed_artist.lower() in ('', 'nan', 'unknown'):
        return 0.0
    same = sum(1 for idx in recs if str(col.iloc[idx]) == seed_artist)
    return float(same) / float(len(recs))


# ---------------------------------------------------------------------------
# Convenience: compute all per-query metrics at once
# ---------------------------------------------------------------------------

def compute_all(
    recs: Sequence[int],
    seed_idx: int,
    catalog: Any,
) -> Dict[str, float]:
    """Return a dict of all per-query property metrics."""
    return {
        'ild_lyrics': ild_lyrics(recs, catalog),
        'ild_audio': ild_audio(recs, catalog),
        'ild_va': ild_va(recs, catalog),
        'ild_color': ild_color(recs, catalog),
        'mood_coherence': mood_coherence(recs, catalog),
        'tempo_coherence': tempo_coherence(recs, catalog),
        'color_coherence': color_coherence(recs, catalog),
        'calibration_error': calibration_error(recs, seed_idx, catalog),
        'serendipity_proxy': serendipity_proxy(recs, seed_idx, catalog),
        'same_artist_at_k': same_artist_at_k(recs, seed_idx, catalog),  # GT-3
    }
