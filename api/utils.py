"""Shared API serialization utilities."""

import math
from pathlib import Path
from typing import List, Dict, Any

import numpy as np
import pandas as pd


def sanitize_for_json(obj):
    """Convert numpy/pandas types to JSON-serializable Python types."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist())
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, pd.Series):
        return sanitize_for_json(obj.to_dict())
    if isinstance(obj, pd.DataFrame):
        return sanitize_for_json(obj.to_dict(orient='records'))
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj

# Cache album art existence to avoid per-request stat() calls
_albumart_cache = None

def _get_albumart_cache():
    global _albumart_cache
    if _albumart_cache is None:
        art_dir = Path(__file__).parent.parent / 'album_art'
        if art_dir.exists():
            _albumart_cache = {f.stem for f in art_dir.glob('*.jpg')}
        else:
            _albumart_cache = set()
    return _albumart_cache


def dataframe_to_dict(df: pd.DataFrame, enrich_album_art: bool = True) -> List[Dict[str, Any]]:
    """Convert a recommendation DataFrame to a list of JSON-safe dicts."""
    if df is None or len(df) == 0:
        return []
    df = df.copy()
    if 'original_index' in df.columns:
        df['song_index'] = df['original_index'].tolist()
    else:
        df['song_index'] = df.index.tolist()
    for col in ['track_url', 'preview_url']:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)
    result = df.to_dict(orient='records')
    for item in result:
        for key, value in list(item.items()):
            if isinstance(value, (np.integer, np.floating)):
                item[key] = float(value)
            elif pd.isna(value):
                item[key] = None
        if enrich_album_art:
            if 'artist' not in item:
                item['artist'] = (
                    item.get('primary_artist')
                    or item.get('artists')
                    or item.get('artist_name')
                    or 'Unknown'
                )
            tid = item.get('track_id', '')
            if tid and 'album_art_url' not in item:
                cache = _get_albumart_cache()
                if tid in cache:
                    item['has_album_art'] = True
                    item['album_art_url'] = f'/api/album-art/{tid}'
                else:
                    # Fallback to thumbnail_url from data
                    thumb = item.get('thumbnail_url')
                    if thumb and not pd.isna(thumb):
                        item['has_album_art'] = True
                        item['album_art_url'] = str(thumb)
                    else:
                        item['has_album_art'] = False
                        item['album_art_url'] = None
    return result
