"""2-colour mood-journey waypoint sampling (Iso-Principle, V23/V39).
Extracted verbatim from MusicRecommender (behaviour-preserving). The recommender
passes its precomputed arrays + config scalars in. Determinism note: selection uses
np.argmax (NOT stable argsort) — preserved exactly as the original."""
import os
import numpy as np
from loguru import logger


def waypoint_sample(p1, p2, top_k, diversity_penalty, *,
                    match_va, mert_centered, bpm, artists, n_songs, exclude_idx,
                    sigma_v, sigma_a, smooth, bpm_tau, smooth_gamma):
    """Divide the V-A path P1→P2 into `top_k` sigmoid-spaced waypoints and greedily
    pick the best unselected song for each (forces intermediate songs → smooth arc).

    `match_va`: (n_songs, 2) rank-match V-A. `mert_centered`: (n_songs, D) or None.
    `bpm`: per-song clean BPM (NaN where missing) or None. `artists`: full array or None.
    """
    p1 = np.asarray(p1, float); p2 = np.asarray(p2, float)
    n = n_songs
    _sv = sigma_v
    _sa = sigma_a

    excluded = np.zeros(n, dtype=bool)
    if exclude_idx:  # endless-radio: never re-pick an already-played song
        excluded[exclude_idx] = True
    artist_counts: dict = {}
    selected: list = []

    # Ease-in-ease-out waypoints (sigmoid schedule), Iso-Principle (Starcke 2024 / Saari 2016).
    try:
        from scipy.special import expit as _expit
        ts_raw = _expit(np.linspace(-3.0, 3.0, top_k))
        ts = (ts_raw - ts_raw[0]) / (ts_raw[-1] - ts_raw[0])
    except ImportError:
        ts = np.linspace(0.0, 1.0, top_k)   # fallback
    waypoints = p1[None, :] + ts[:, None] * (p2 - p1)[None, :]  # (K, 2)

    M = mert_centered if smooth else None
    for wp in waypoints:
        dv = match_va[:, 0] - wp[0]
        da = match_va[:, 1] - wp[1]
        scores = np.exp(-0.5 * ((dv / _sv) ** 2 + (da / _sa) ** 2))

        scores[excluded] = -1.0

        # Mild diversity penalty (cap repeat-artist contribution at 3)
        if diversity_penalty > 0 and artists is not None:
            for i in np.where(scores > 0)[0]:
                cnt = artist_counts.get(artists[i], 0)
                if cnt:
                    scores[i] *= max(0.0, 1.0 - diversity_penalty * min(cnt, 3))

        # V39: continuity bonus — acoustic closeness to previous pick (timbre + tempo flow).
        if smooth and selected:
            prev = selected[-1]
            cont = np.zeros(n, dtype=float)
            if M is not None:
                cont += 0.5 * np.clip(M @ M[prev], -1, 1)        # centred-MERT timbre sim
            if bpm is not None and not np.isnan(bpm[prev]):
                cont += 0.5 * np.exp(-np.abs(bpm - bpm[prev]) / bpm_tau)
            pos = scores > 0
            scores[pos] = scores[pos] + smooth_gamma * cont[pos]

        best = int(np.argmax(scores))
        if scores[best] <= 0:
            continue
        selected.append(best)
        excluded[best] = True
        if artists is not None:
            art = artists[best]
            artist_counts[art] = artist_counts.get(art, 0) + 1

    return selected


def load_bpm_array(df, n_songs, path):
    """Per-song clean BPM aligned to catalog order (NaN where missing). V39."""
    import json as _json
    arr = np.full(n_songs, np.nan, dtype=float)
    if os.path.exists(path):
        try:
            d = _json.load(open(path))
            tids = df['track_id'].astype(str).values
            for i, t in enumerate(tids):
                v = d.get(t)
                if v:
                    arr[i] = float(v)
        except Exception as e:
            logger.warning(f"[journey] BPM load failed: {e}")
    return arr
