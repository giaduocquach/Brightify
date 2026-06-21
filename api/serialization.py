"""Shared song-serialization helpers — single source for logic previously duplicated
across api/music.py and api/utils.py (album-art resolution, track_id→index, artist column).

Imports only config / pandas / fastapi — never api.music or api.utils, so the import
graph stays a DAG (utils → serialization, music → serialization). No cycle."""
from typing import Optional, Tuple

import pandas as pd
from fastapi import HTTPException

import config as cfg


# ── Album-art existence cache (one source of truth) ──────────────────────────
# Avoids per-request stat() calls. api.music.init() populates it eagerly at startup;
# the lazy getter globs on first use if init() never ran (e.g. an engine-only test path).
_albumart_cache: Optional[set] = None


def set_albumart_cache(names) -> None:
    """Eager population at app startup."""
    global _albumart_cache
    _albumart_cache = set(names)


def get_albumart_cache() -> set:
    """Lazy glob fallback if the eager init never ran."""
    global _albumart_cache
    if _albumart_cache is None:
        art_dir = cfg.ALBUM_ART_DIR
        _albumart_cache = {f.stem for f in art_dir.glob('*.jpg')} if art_dir.exists() else set()
    return _albumart_cache


def resolve_album_art_url(track_id: str, thumbnail_url) -> Tuple[bool, Optional[str]]:
    """(has_art, url): local .jpg → /api/album-art/{id}; else thumbnail_url; else (False, None).
    Neutral tuple — each caller assigns its own key names."""
    if track_id and track_id in get_albumart_cache():
        return True, f"/api/album-art/{track_id}"
    if thumbnail_url is not None and thumbnail_url != '' and not pd.isna(thumbnail_url):
        return True, str(thumbnail_url)
    return False, None


def resolve_track_id_to_index(song_id: str, df, bounds_check: bool = True) -> int:
    """Resolve a track_id string (or legacy integer-index string) to a positional df index.
    Raises HTTPException(404) when not found.

    bounds_check: range-check the integer path. get_similar_songs passes False to
    preserve its original behavior (an out-of-range int falls through to the recommender,
    which raises → 500) — do NOT change that to a 404."""
    if not song_id.isdigit():
        if 'track_id' not in df.columns:
            raise HTTPException(status_code=404, detail="Song not found")
        matches = df.index[df['track_id'] == song_id].tolist()
        if not matches:
            raise HTTPException(status_code=404, detail="Song not found")
        return int(matches[0])
    idx = int(song_id)
    if bounds_check and (idx < 0 or idx >= len(df)):
        raise HTTPException(status_code=404, detail="Song not found")
    return idx


# API artist-column preference order. SEPARATE from core.recommendation_engine's
# detect_artist_column (which uses a different list) — do NOT merge: a different
# first-match column would change which artist string is displayed/diversified.
_ARTIST_COLS = ['primary_artist', 'artist_name', 'artist']


def api_artist_column(df) -> Optional[str]:
    """First present artist column (API preference order), or None."""
    return next((c for c in _ARTIST_COLS if c in df.columns), None)
