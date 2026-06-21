"""Colour → Valence-Arousal matching helpers + emotion label constants.

Pure numeric transforms extracted from MusicRecommender (behaviour-preserving):
the recommender owns the catalog state and assigns the results to self.* — these
functions just do the deterministic math. No engine/config import (one-directional).
"""
import numpy as np


# 8 CLAP emotion labels → Russell mood quadrant string (format the API expects:
# "QN: Name", consumed via startswith('QN') in /api/moods and contains() in filter)
EMO_QUADRANT = {
    'happy': 'Q1: Happy/Excited', 'excited': 'Q1: Happy/Excited',
    'angry': 'Q2: Angry/Tense', 'tense': 'Q2: Angry/Tense',
    'sad': 'Q3: Sad/Melancholic', 'melancholic': 'Q3: Sad/Melancholic',
    'calm': 'Q4: Calm/Peaceful', 'peaceful': 'Q4: Calm/Peaceful',
}

# 8 emotion labels → Vietnamese display word (used in "why" explanations + bridge).
EMO_VI = {
    'happy': 'Vui vẻ', 'excited': 'Phấn khích', 'peaceful': 'Bình yên',
    'calm': 'Thư thái', 'melancholic': 'U sầu', 'sad': 'Buồn',
    'tense': 'Căng thẳng', 'angry': 'Giận dữ',
}


def build_rank_match_space(song_va, n_songs):
    """V31 rank-match space: catalog empirical-CDF ranks of per-song V-A, plus the
    sorted raw V-A arrays (for target_quantile). Returns (song_va_match, va_sorted_v, va_sorted_a)."""
    from scipy.stats import rankdata
    denom = max(n_songs - 1, 1)
    rv = (rankdata(song_va[:, 0]) - 1) / denom
    ra = (rankdata(song_va[:, 1]) - 1) / denom
    song_va_match = np.column_stack([rv, ra]).astype(float)
    va_sorted_v = np.sort(song_va[:, 0])
    va_sorted_a = np.sort(song_va[:, 1])
    return song_va_match, va_sorted_v, va_sorted_a


def catalog_va_percentiles(song_va):
    """C1 legacy linear calibration anchors (5th/95th pct of catalog V and A)."""
    return {
        'v5':  float(np.percentile(song_va[:, 0], 5)),
        'v95': float(np.percentile(song_va[:, 0], 95)),
        'a5':  float(np.percentile(song_va[:, 1], 5)),
        'a95': float(np.percentile(song_va[:, 1], 95)),
    }


def target_quantile(cva, va_sorted_v, va_sorted_a):
    """V36: map a colour's raw V-A to its percentile within the catalog's own mood
    distribution (empirical CDF), spreading the 12 colours across the full [0,1] range."""
    nv = len(va_sorted_v)
    qv = float(np.searchsorted(va_sorted_v, cva[0]) / nv)
    qa = float(np.searchsorted(va_sorted_a, cva[1]) / nv)
    return np.clip(np.array([qv, qa]), 0.0, 1.0)
