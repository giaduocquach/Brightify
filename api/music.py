"""Music browse, search, and audio streaming API routes."""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
import random

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Music"])

# These will be set by app.py during initialization
_recommender = None
_music_path = None
_artist_images_path = None
_artist_data = {}  # artist_id → {name, image_url, genres, ...}
_mp3_cache = set()       # cached set of existing mp3 filenames
_albumart_cache = set()  # cached set of existing album art filenames
_artistimg_cache = set() # cached set of existing artist image filenames


def init(recommender, music_path: Path, artist_images_path: Path = None):
    global _recommender, _music_path, _artist_images_path, _artist_data
    global _mp3_cache, _albumart_cache, _artistimg_cache
    _recommender = recommender
    _music_path = music_path
    _artist_images_path = artist_images_path

    # Pre-cache file existence to avoid per-request stat() calls
    if _music_path and _music_path.exists():
        _mp3_cache = {f.stem for f in _music_path.glob("*.mp3")}
    album_art_dir = Path(__file__).parent.parent / "album_art"
    if album_art_dir.exists():
        _albumart_cache = {f.stem for f in album_art_dir.glob("*.jpg")}
    if _artist_images_path and _artist_images_path.exists():
        _artistimg_cache = {f.stem for f in _artist_images_path.glob("*.jpg")}

    # Load artist images data
    artist_json = Path(__file__).parent.parent / "data" / "artist_images.json"
    if artist_json.exists():
        try:
            import json
            with open(artist_json, "r", encoding="utf-8") as f:
                _artist_data = json.load(f)
            logger.info("Loaded %d artist profiles", len(_artist_data))
        except Exception as e:
            logger.warning("Could not load artist_images.json: %s", e)

    # Fallback: load artist thumbnail URLs from phase1_artists.csv
    if not _artist_data:
        artist_csv = Path(__file__).parent.parent / "checkpoints" / "phase1_artists.csv"
        if artist_csv.exists():
            try:
                import csv
                with open(artist_csv, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        aid = (row.get("artist_id") or "").strip()
                        thumb = (row.get("thumbnail_url") or "").strip()
                        if aid and thumb:
                            _artist_data[aid] = {"image_url": thumb}
                logger.info("Loaded %d artist thumbnails from CSV", len(_artist_data))
            except Exception as e:
                logger.warning("Could not load phase1_artists.csv: %s", e)


def _serialize(value):
    if isinstance(value, (np.integer, np.floating)):
        return float(value)
    if pd.isna(value):
        return None
    return value


def _song_to_dict(row, idx):
    """Convert a dataframe row to a clean song dict"""
    track_id = str(row.get('track_id', ''))
    has_audio = track_id in _mp3_cache if track_id else False
    has_art = track_id in _albumart_cache

    # Artist image lookup
    artist_ids_str = str(row.get('artist_ids', ''))
    primary_artist_id = artist_ids_str.split(',')[0].strip() if artist_ids_str else ''
    has_artist_img = primary_artist_id in _artistimg_cache if primary_artist_id else False
    artist_img_url = f"/api/artist-image/{primary_artist_id}" if has_artist_img else None

    # Fallback to thumbnail_url from CSV data when no local .jpg
    thumbnail_url = str(row.get('thumbnail_url', '')) if pd.notna(row.get('thumbnail_url')) else None

    # Artist image fallback from artist data
    if not has_artist_img and primary_artist_id:
        adata = _artist_data.get(primary_artist_id, {})
        if adata.get('image_url'):
            has_artist_img = True
            artist_img_url = adata['image_url']  # direct CDN URL

    # Determine album art URL: prefer local file, fallback to thumbnail_url
    if has_art:
        album_art_url = f"/api/album-art/{track_id}"
    elif thumbnail_url:
        has_art = True
        album_art_url = thumbnail_url
    else:
        album_art_url = None

    return {
        'song_index': int(idx),
        'track_id': track_id,
        'track_name': str(row.get('track_name', 'Unknown')),
        'artist': str(row.get('primary_artist', row.get('artists', row.get('artist_name', 'Unknown')))),
        'artist_id': primary_artist_id,
        'album_name': str(row.get('album_name', '')),
        'color_hex': str(row.get('color_hex', '#6366f1')),
        'valence': _serialize(row.get('valence', 0.5)),
        'energy': _serialize(row.get('energy', 0.5)),
        'arousal': _serialize(row.get('arousal')),
        'danceability': _serialize(row.get('danceability', 0.5)),
        'tempo': _serialize(row.get('tempo', 120)),
        'timbre_bright': _serialize(row.get('timbre_bright')),
        'mood_quadrant': str(row.get('mood_quadrant', '')),
        'fused_emotion': str(row.get('fused_emotion', '')),
        'has_audio': has_audio,
        'audio_url': f"/api/audio/stream/{track_id}" if has_audio else None,
        'has_album_art': has_art,
        'album_art_url': album_art_url,
        'thumbnail_url': thumbnail_url,
        'has_artist_image': has_artist_img,
        'artist_image_url': artist_img_url,
    }


# ============================================================================
# Browse / Discovery
# ============================================================================

@router.get("/songs")
async def browse_songs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="name", regex="^(name|artist|energy|valence|danceability|random)$"),
    mood: Optional[str] = None,
    artist: Optional[str] = None,
    search: Optional[str] = None,
):
    """Browse songs with pagination, sorting, and filtering"""
    df = _recommender.df

    # Filter by mood
    if mood and 'mood_quadrant' in df.columns:
        df = df[df['mood_quadrant'].str.contains(mood, case=False, na=False, regex=False)]

    # Filter by artist
    artist_col = None
    for col in ['primary_artist', 'artist_name', 'artist']:
        if col in df.columns:
            artist_col = col
            break
    if artist and artist_col:
        df = df[df[artist_col].str.contains(artist, case=False, na=False)]

    # Search by name/artist
    if search and search.strip():
        q = search.strip().lower()
        mask = df['track_name'].str.lower().str.contains(q, na=False, regex=False)
        if artist_col:
            mask = mask | df[artist_col].str.lower().str.contains(q, na=False, regex=False)
        df = df[mask]

    total = len(df)

    # Sort
    if sort == 'name':
        df = df.sort_values('track_name')
    elif sort == 'artist' and artist_col:
        df = df.sort_values(artist_col)
    elif sort in ('energy', 'valence', 'danceability') and sort in df.columns:
        df = df.sort_values(sort, ascending=False)
    elif sort == 'random':
        df = df.sample(frac=1, random_state=random.randint(0, 99999))

    # Paginate
    start = (page - 1) * limit
    end = start + limit
    page_df = df.iloc[start:end]

    songs = [_song_to_dict(row, idx) for idx, row in page_df.iterrows()]

    return {
        "success": True,
        "songs": songs,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


@router.get("/songs/featured")
async def featured_songs(count: int = Query(default=12, ge=1, le=50)):
    """Get featured/trending songs (highest energy + danceability)"""
    df = _recommender.df.copy()

    if 'energy' in df.columns and 'danceability' in df.columns:
        df['_score'] = df['energy'] * 0.5 + df['danceability'] * 0.3 + df['valence'].fillna(0.5) * 0.2
        df = df.sort_values('_score', ascending=False)
    
    # Pick from top pool with some randomness
    pool = df.head(count * 3)
    selected = pool.sample(n=min(count, len(pool)))
    
    songs = [_song_to_dict(row, idx) for idx, row in selected.iterrows()]
    return {"success": True, "songs": songs}


@router.get("/songs/new-releases")
async def new_releases(count: int = Query(default=12, ge=1, le=50)):
    """Get newest songs (last entries in dataset)"""
    df = _recommender.df
    recent = df.tail(count * 2).sample(n=min(count, len(df)))
    songs = [_song_to_dict(row, idx) for idx, row in recent.iterrows()]
    return {"success": True, "songs": songs}


@router.get("/songs/by-mood/{mood}")
async def songs_by_mood(mood: str, count: int = Query(default=20, ge=1, le=50)):
    """Get songs filtered by mood quadrant"""
    df = _recommender.df
    
    mood_map = {
        'happy': 'Q1', 'excited': 'Q1',
        'angry': 'Q2', 'tense': 'Q2', 'energetic': 'Q2',
        'sad': 'Q3', 'melancholic': 'Q3',
        'calm': 'Q4', 'peaceful': 'Q4', 'relaxed': 'Q4',
    }
    
    quadrant = mood_map.get(mood.lower(), mood.upper())
    
    if 'mood_quadrant' in df.columns:
        filtered = df[df['mood_quadrant'] == quadrant]
        if len(filtered) == 0:
            filtered = df[df['mood_quadrant'].str.contains(quadrant, case=False, na=False)]
    else:
        filtered = df
    
    if len(filtered) > count:
        filtered = filtered.sample(n=count)
    
    songs = [_song_to_dict(row, idx) for idx, row in filtered.iterrows()]
    return {"success": True, "songs": songs, "mood": mood, "quadrant": quadrant}


@router.get("/songs/time-of-day")
async def time_of_day_songs(period: str = Query(...), count: int = Query(default=14, ge=1, le=50)):
    """Get songs suited for a time of day based on audio features.
    
    Periods: early_morning (5-8h), morning (8-11h), midday (11-13h),
    afternoon (13-17h), evening (17-21h), night (21-5h)
    """
    df = _recommender.df.copy()

    profiles = {
        'early_morning': {
            'energy': (0.1, 0.45), 'valence': (0.25, 0.6), 'acousticness': (0.4, 1.0),
            'danceability': (0.2, 0.55), 'tempo': (60, 110),
        },
        'morning': {
            'energy': (0.45, 0.85), 'valence': (0.5, 1.0), 'acousticness': (0.1, 0.6),
            'danceability': (0.45, 0.9), 'tempo': (90, 140),
        },
        'midday': {
            'energy': (0.25, 0.55), 'valence': (0.35, 0.7), 'acousticness': (0.3, 0.8),
            'danceability': (0.3, 0.65), 'tempo': (75, 120),
        },
        'afternoon': {
            'energy': (0.5, 0.95), 'valence': (0.4, 0.9), 'acousticness': (0.0, 0.5),
            'danceability': (0.5, 0.95), 'tempo': (100, 160),
        },
        'evening': {
            'energy': (0.2, 0.55), 'valence': (0.3, 0.7), 'acousticness': (0.25, 0.75),
            'danceability': (0.3, 0.6), 'tempo': (70, 115),
        },
        'night': {
            'energy': (0.05, 0.4), 'valence': (0.1, 0.5), 'acousticness': (0.35, 1.0),
            'danceability': (0.15, 0.5), 'tempo': (55, 105),
        },
    }

    profile = profiles.get(period)
    if not profile:
        raise HTTPException(status_code=400, detail=f"Invalid period: {period}")

    df['_score'] = 0.0
    for feature, (lo, hi) in profile.items():
        if feature == 'tempo':
            col = df[feature].fillna(120)
            normalized = (col - 40) / 160
            lo_n, hi_n = (lo - 40) / 160, (hi - 40) / 160
        else:
            normalized = df[feature].fillna(0.5)
            lo_n, hi_n = lo, hi

        mid = (lo_n + hi_n) / 2
        spread = (hi_n - lo_n) / 2
        distance = ((normalized - mid) / max(spread, 0.01)).abs()
        df['_score'] += np.exp(-0.5 * distance ** 2)

    df = df.sort_values('_score', ascending=False)
    pool = df.head(count * 4)
    selected = pool.sample(n=min(count, len(pool)))

    songs = [_song_to_dict(row, idx) for idx, row in selected.iterrows()]
    return {"success": True, "songs": songs, "period": period}


@router.get("/songs/random")
async def random_songs(count: int = Query(default=10, ge=1, le=50)):
    """Get random songs for discovery"""
    df = _recommender.df
    selected = df.sample(n=min(count, len(df)))
    songs = [_song_to_dict(row, idx) for idx, row in selected.iterrows()]
    return {"success": True, "songs": songs}


@router.get("/songs/search")
async def search_songs(q: str = Query(..., min_length=1), limit: int = Query(default=20, ge=1, le=50)):
    """Search songs by name, artist, or lyrics keywords"""
    df = _recommender.df
    query = q.strip().lower()

    # Search in track_name
    mask = df['track_name'].str.lower().str.contains(query, na=False)

    # Search in artist
    for col in ['primary_artist', 'artist_name', 'artist']:
        if col in df.columns:
            mask = mask | df[col].str.lower().str.contains(query, na=False)
            break

    # Search in album
    if 'album_name' in df.columns:
        mask = mask | df['album_name'].str.lower().str.contains(query, na=False)

    results = df[mask].head(limit)
    songs = [_song_to_dict(row, idx) for idx, row in results.iterrows()]

    return {"success": True, "songs": songs, "query": q, "total": len(songs)}


# ============================================================================
# Artists
# ============================================================================

@router.get("/artists")
async def list_artists(limit: int = Query(default=50, ge=1, le=9999)):
    """List unique artists with song counts and images"""
    df = _recommender.df
    
    artist_col = None
    for col in ['primary_artist', 'artist_name', 'artist']:
        if col in df.columns:
            artist_col = col
            break
    
    if not artist_col:
        return {"success": True, "artists": []}

    counts = df[artist_col].value_counts().head(limit)
    artists = []
    for name, count in counts.items():
        artist_songs = df[df[artist_col] == name]
        sample = artist_songs.iloc[0]
        track_id = str(sample.get('track_id', ''))
        thumbnail_url = str(sample.get('thumbnail_url', '')) if pd.notna(sample.get('thumbnail_url')) else None

        # Album art: prefer local file, fallback to thumbnail_url
        if track_id in _albumart_cache:
            has_art = True
            art_url = f"/api/album-art/{track_id}"
        elif thumbnail_url:
            has_art = True
            art_url = thumbnail_url
        else:
            has_art = False
            art_url = None

        # Get artist image from artist_images directory
        artist_ids_str = str(sample.get('artist_ids', ''))
        primary_artist_id = artist_ids_str.split(',')[0].strip() if artist_ids_str else ''
        has_artist_img = primary_artist_id in _artistimg_cache if primary_artist_id else False
        artist_img_url = f"/api/artist-image/{primary_artist_id}" if has_artist_img else None
        artist_info = _artist_data.get(primary_artist_id, {})

        # Fallback: use CDN URL from artist data if no local .jpg
        if not has_artist_img and primary_artist_id and artist_info.get('image_url'):
            has_artist_img = True
            artist_img_url = artist_info['image_url']

        artists.append({
            'name': str(name),
            'artist_id': primary_artist_id,
            'song_count': int(count),
            'sample_track_id': track_id,
            'has_art': has_art,
            'art_url': art_url,
            'has_artist_image': has_artist_img,
            'artist_image_url': artist_img_url,
            'genres': artist_info.get('genres', []),
            'followers': artist_info.get('followers', 0),
            'popularity': artist_info.get('popularity', 0),
        })

    return {"success": True, "artists": artists}


@router.get("/artists/{artist_name}/songs")
async def artist_songs(artist_name: str):
    """Get all songs by a specific artist"""
    df = _recommender.df

    artist_col = None
    for col in ['primary_artist', 'artist_name', 'artist']:
        if col in df.columns:
            artist_col = col
            break

    if not artist_col:
        raise HTTPException(status_code=404, detail="Artist data not available")

    filtered = df[df[artist_col].str.lower() == artist_name.lower()]
    if len(filtered) == 0:
        filtered = df[df[artist_col].str.lower().str.contains(artist_name.lower(), na=False, regex=False)]

    songs = [_song_to_dict(row, idx) for idx, row in filtered.iterrows()]
    return {"success": True, "artist": artist_name, "songs": songs, "total": len(songs)}


# ============================================================================
# Genres / Moods
# ============================================================================

@router.get("/genres")
async def list_genres():
    """List available mood/genre categories with counts"""
    df = _recommender.df
    
    genres = []
    
    if 'mood_quadrant' in df.columns:
        quadrant_names = {
            'Q1': {'name': 'Happy & Excited', 'icon': '😊', 'gradient': ['#f97316', '#eab308']},
            'Q2': {'name': 'Energetic & Tense', 'icon': '⚡', 'gradient': ['#ef4444', '#f97316']},
            'Q3': {'name': 'Sad & Melancholic', 'icon': '🌧️', 'gradient': ['#6366f1', '#8b5cf6']},
            'Q4': {'name': 'Calm & Peaceful', 'icon': '🌿', 'gradient': ['#10b981', '#06b6d4']},
        }
        
        for quadrant, info in quadrant_names.items():
            count = int(df['mood_quadrant'].str.startswith(quadrant, na=False).sum())
            if count > 0:
                genres.append({
                    'id': quadrant,
                    'name': info['name'],
                    'icon': info['icon'],
                    'gradient': info['gradient'],
                    'count': count,
                })
    
    if 'fused_emotion' in df.columns:
        emotion_icons = {
            'happy': '😄', 'sad': '😢', 'love': '❤️', 'angry': '😠',
            'peaceful': '☮️', 'excited': '🎉', 'melancholic': '🌙',
            'longing': '💭', 'hope': '🌅',
        }
        emotions = df['fused_emotion'].value_counts()
        for emotion, count in emotions.items():
            if str(emotion) != 'nan' and count > 10:
                genres.append({
                    'id': f'emotion_{emotion}',
                    'name': str(emotion).title(),
                    'icon': emotion_icons.get(str(emotion).lower(), '🎵'),
                    'count': int(count),
                    'type': 'emotion',
                })

    return {"success": True, "genres": genres}


# ============================================================================
# Song Details & Audio
# ============================================================================

@router.get("/song/{song_id}")
async def get_song_details(song_id: str):
    """Get detailed info about a specific song. Accepts track_id (string) or integer index."""
    try:
        df = _recommender.df
        
        # Try as track_id first (string identifier)
        if not song_id.isdigit():
            if 'track_id' in df.columns:
                matches = df.index[df['track_id'] == song_id].tolist()
                if matches:
                    idx = int(matches[0])
                    row = df.iloc[idx]
                else:
                    raise HTTPException(status_code=404, detail="Song not found")
            else:
                raise HTTPException(status_code=404, detail="Song not found")
        else:
            # Legacy: integer index support
            idx = int(song_id)
            if idx < 0 or idx >= len(df):
                raise HTTPException(status_code=404, detail="Song not found")
            row = df.iloc[idx]
        song = _song_to_dict(row, idx)

        # Add extra details
        for col in ['acousticness', 'instrumentalness', 'speechiness', 'liveness',
                     'loudness', 'key', 'mode', 'sentiment_compound']:
            if col in df.columns:
                song[col] = _serialize(row.get(col))

        # Lyrics — prefer plain_lyrics, fallback to lyrics_cleaned
        for lcol in ['plain_lyrics', 'lyrics_cleaned']:
            if lcol in df.columns:
                val = row.get(lcol)
                if pd.notna(val) and str(val).strip():
                    song['lyrics'] = str(val)
                    break

        return {"success": True, "song": song}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/song/{song_id}/similar")
async def get_similar_songs(song_id: str, count: int = Query(default=10, ge=1, le=30)):
    """Get songs similar to a given song using multi-faceted AI similarity"""
    try:
        df = _recommender.df
        # Resolve track_id to index
        if not song_id.isdigit():
            if 'track_id' in df.columns:
                matches = df.index[df['track_id'] == song_id].tolist()
                if not matches:
                    raise HTTPException(status_code=404, detail="Song not found")
                resolved_idx = int(matches[0])
            else:
                raise HTTPException(status_code=404, detail="Song not found")
        else:
            resolved_idx = int(song_id)
        
        results = _recommender.recommend_by_song(resolved_idx, top_k=count)
        df_results = results
        songs = []
        for idx, row in df_results.iterrows():
            s = _song_to_dict(row, row.get('original_index', idx))
            s['similarity_score'] = round(float(row.get('similarity_score', 0)), 4)
            songs.append(s)

        # Source song info for context
        source_info = _recommender.get_song_info(resolved_idx)
        source_name = source_info.get('track_name', '') if source_info else ''

        return {
            "success": True,
            "songs": songs,
            "source_song_id": song_id,
            "source_song_name": source_name,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/track/info/{song_index}")
async def get_track_info(song_index: str):
    """Get track info with local audio availability. Accepts track_id or integer index."""
    try:
        df = _recommender.df
        # Resolve to index
        if not song_index.isdigit():
            if 'track_id' in df.columns:
                matches = df.index[df['track_id'] == song_index].tolist()
                if not matches:
                    raise HTTPException(status_code=404, detail="Song not found")
                idx = int(matches[0])
            else:
                raise HTTPException(status_code=404, detail="Song not found")
        else:
            idx = int(song_index)
            if idx < 0 or idx >= len(df):
                raise HTTPException(status_code=404, detail="Song not found")

        track = df.iloc[idx]
        track_id = str(track.get('track_id', ''))
        file_path = _music_path / f"{track_id}.mp3"
        has_local = file_path.exists()

        return {
            "success": True,
            "song_index": song_index,
            "track_name": str(track.get('track_name', 'Unknown')),
            "artist": str(track.get('primary_artist', 'Unknown')),
            "track_id": track_id,
            "has_local_audio": has_local,
            "audio_url": f"/api/audio/stream/{track_id}" if has_local else None,
            "color_hex": str(track.get('color_hex', '#6366f1')),
            "mood": str(track.get('mood_quadrant', 'Unknown')),
            "valence": float(track.get('valence', 0.5)),
            "energy": float(track.get('energy', 0.5)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audio/stream/{track_id}")
async def stream_audio(track_id: str):
    """Stream a local MP3 file"""
    if not all(c.isalnum() or c in '-_' for c in track_id):
        raise HTTPException(status_code=400, detail="Invalid track ID")

    file_path = _music_path / f"{track_id}.mp3"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"},
    )


@router.get("/audio/status/{track_id}")
async def get_audio_status(track_id: str):
    """Check if audio file exists for a track"""
    file_path = _music_path / f"{track_id}.mp3"
    exists = file_path.exists()
    return {
        "track_id": track_id,
        "available": exists,
        "file_size": file_path.stat().st_size if exists else 0,
    }


@router.get("/audio/batch-status")
async def get_batch_audio_status(track_ids: str = Query(..., description="Comma-separated track IDs")):
    """Batch check audio availability"""
    ids = [tid.strip() for tid in track_ids.split(",") if tid.strip()]
    result = {}
    for tid in ids[:100]:
        fp = _music_path / f"{tid}.mp3"
        result[tid] = fp.exists()
    return {"status": result, "available_count": sum(result.values()), "total": len(result)}


@router.get("/audio/stats")
async def get_audio_stats():
    """Get local music library statistics"""
    mp3_files = list(_music_path.glob("*.mp3"))
    total_size = sum(f.stat().st_size for f in mp3_files)
    return {
        "total_files": len(mp3_files),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }


@router.get("/album-art/{track_id}")
async def get_album_art(track_id: str):
    """Serve album art image"""
    if not all(c.isalnum() or c in '-_' for c in track_id):
        raise HTTPException(status_code=400, detail="Invalid track ID")

    art_path = Path(__file__).parent.parent / "album_art" / f"{track_id}.jpg"
    if not art_path.exists():
        raise HTTPException(status_code=404, detail="Album art not found")

    return FileResponse(path=str(art_path), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/artist-image/{artist_id}")
async def get_artist_image(artist_id: str):
    """Serve artist profile image"""
    if not all(c.isalnum() or c in '-_' for c in artist_id):
        raise HTTPException(status_code=400, detail="Invalid artist ID")

    if not _artist_images_path:
        raise HTTPException(status_code=404, detail="Artist images not configured")

    img_path = _artist_images_path / f"{artist_id}.jpg"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Artist image not found")

    return FileResponse(path=str(img_path), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/artist/{artist_id}/info")
async def get_artist_info(artist_id: str):
    """Get artist profile info including image, genres, followers"""
    info = _artist_data.get(artist_id, {})
    if not info:
        raise HTTPException(status_code=404, detail="Artist not found")

    has_img = False
    if _artist_images_path:
        has_img = (_artist_images_path / f"{artist_id}.jpg").exists()

    return {
        "success": True,
        "artist_id": artist_id,
        "name": info.get("name", "Unknown"),
        "has_image": has_img,
        "image_url": f"/api/artist-image/{artist_id}" if has_img else None,
        "genres": info.get("genres", []),
        "followers": info.get("followers", 0),
        "popularity": info.get("popularity", 0),
    }
