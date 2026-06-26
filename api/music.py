"""Music browse, search, and audio streaming API routes."""

import logging
import unicodedata

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
import random

import config as cfg

from api.cache import cache_get, cache_set, make_key
from api import serialization as _ser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Music"])

# These will be set by app.py during initialization
_recommender = None
_music_path = None
_artist_images_path = None
_artist_data = {}  # artist_id → {name, image_url, genres, ...}
_mp3_cache = set()       # cached set of existing mp3 filenames
_artistimg_cache = set() # cached set of existing artist image filenames
# album-art existence cache lives in api.serialization (single source) — see _ser.*
# Diacritics-stripped, lowercased search columns (positional to _recommender.df),
# so toneless Vietnamese queries ("son tung", "anh nho em") still match. Built in init().
_search_index = None  # {'name','artist','album','lyrics','lyrics_col'} or None


def _strip_diacritics(text: str) -> str:
    """Lowercase + remove Vietnamese tone/diacritic marks (đ→d) for accent-insensitive match."""
    text = text.replace('đ', 'd').replace('Đ', 'D')
    decomposed = unicodedata.normalize('NFD', text)
    return ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn').lower()


def _build_search_index(df: pd.DataFrame) -> None:
    """Precompute normalized name/artist/album/lyrics columns once at startup."""
    global _search_index
    artist_col = _ser.api_artist_column(df)
    lyrics_col = next((c for c in ['lyrics_cleaned', 'plain_lyrics'] if c in df.columns), None)
    name_norm = df['track_name'].fillna('').astype(str).map(_strip_diacritics)
    artist_norm = df[artist_col].fillna('').astype(str).map(_strip_diacritics) if artist_col else None
    # Fuzzy fallback indexes (typo recovery). Unique artist → row positions: matching a
    # short query against the deduped artist list (a few hundred) is far more precise than
    # against 5138 long strings.
    artist_unique: list = []
    artist_to_rows: dict = {}
    if artist_norm is not None:
        for i, a in enumerate(artist_norm.tolist()):
            if a:
                artist_to_rows.setdefault(a, []).append(i)
        artist_unique = list(artist_to_rows.keys())
    idx = {
        'name': name_norm,
        'artist': artist_norm,
        'album': df['album_name'].fillna('').astype(str).map(_strip_diacritics) if 'album_name' in df.columns else None,
        'lyrics': df[lyrics_col].fillna('').astype(str).map(_strip_diacritics) if lyrics_col else None,
        'lyrics_col': lyrics_col,
        'name_list': name_norm.tolist(),
        'artist_unique': artist_unique,
        'artist_to_rows': artist_to_rows,
    }
    _search_index = idx
    logger.info("Search index built (diacritics-insensitive): name+%s+%s+%s",
                'artist' if idx['artist'] is not None else '-',
                'album' if idx['album'] is not None else '-',
                lyrics_col or 'no-lyrics')


def init(recommender, music_path: Path, artist_images_path: Path = None):
    global _recommender, _music_path, _artist_images_path, _artist_data
    global _mp3_cache, _artistimg_cache
    _recommender = recommender
    _music_path = music_path
    _artist_images_path = artist_images_path
    _build_search_index(recommender.df)

    # Build the set of track_ids that have audio. This drives has_audio (and the
    # status endpoints), which the frontend uses to enable play buttons.
    # CDN mode: local music_files/ is absent, so read the manifest synced to S3.
    # Local mode: glob the music_files/ directory.
    if cfg.AUDIO_CDN_BASE:
        manifest = Path(cfg.AUDIO_MANIFEST_FILE)
        if manifest.exists():
            import json
            with open(manifest, encoding="utf-8") as fh:
                _mp3_cache = set(json.load(fh))
            logger.info("Audio CDN mode: %d track ids from manifest %s", len(_mp3_cache), manifest)
        elif _music_path and _music_path.exists():
            _mp3_cache = {f.stem for f in _music_path.glob("*.mp3")}
            logger.warning("AUDIO_CDN_BASE set but no manifest — fell back to local glob (%d)", len(_mp3_cache))
        else:
            _mp3_cache = set()
            logger.warning("AUDIO_CDN_BASE set but no manifest and no local music_files — has_audio will be False")
    elif _music_path and _music_path.exists():
        _mp3_cache = {f.stem for f in _music_path.glob("*.mp3")}
    album_art_dir = cfg.ALBUM_ART_DIR
    if album_art_dir.exists():
        _ser.set_albumart_cache({f.stem for f in album_art_dir.glob("*.jpg")})
    if _artist_images_path and _artist_images_path.exists():
        _artistimg_cache = {f.stem for f in _artist_images_path.glob("*.jpg")}

    # Load artist images data
    artist_json = Path(cfg.ARTIST_IMAGES_DATA_FILE)
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
        artist_csv = Path(cfg.PHASE1_ARTISTS_FILE)
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
        f = float(value)
        # NaN/inf are not JSON-compliant → emit null. Without this, songs missing an audio
        # feature (timbre_bright/acousticness/…) make the whole endpoint 500 (e.g. /api/song,
        # which the lyrics panel calls → "no lyrics" for ~that song).
        return f if np.isfinite(f) else None
    if pd.isna(value):
        return None
    return value


def _song_to_dict(row, idx):
    """Convert a dataframe row to a clean song dict"""
    track_id = str(row.get('track_id', ''))
    has_audio = track_id in _mp3_cache if track_id else False

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

    # Album art URL: local file → thumbnail fallback → none (shared resolver).
    has_art, album_art_url = _ser.resolve_album_art_url(track_id, thumbnail_url)

    # Smart crossfade needs: tempo, energy, key, mode, mood_quadrant, duration_s,
    # loudness_lufs (Phase 2), fade_out_cue_s/fade_in_cue_s/downbeat_times_json (Phase 3).
    # Compute duration_s from various known column names (CSV uses track_duration_ms,
    # DB model uses duration_ms, MP3 fallback is mp3_duration_s).
    duration_s = None
    for ms_col in ('duration_ms', 'track_duration_ms'):
        val = row.get(ms_col)
        if pd.notna(val) and val:
            duration_s = float(val) / 1000.0
            break
    if duration_s is None and pd.notna(row.get('mp3_duration_s')):
        duration_s = float(row.get('mp3_duration_s'))

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
        'key': _serialize(row.get('key')),
        'mode': _serialize(row.get('mode')),
        'loudness': _serialize(row.get('loudness')),
        'loudness_lufs': _serialize(row.get('loudness_lufs')),
        'duration_s': _serialize(duration_s),
        'fade_out_cue_s': _serialize(row.get('fade_out_cue_s')),
        'fade_in_cue_s': _serialize(row.get('fade_in_cue_s')),
        'downbeat_times_json': row.get('downbeat_times_json') if pd.notna(row.get('downbeat_times_json')) else None,
        'vocal_start_s': _serialize(row.get('vocal_start_s')),
        'vocal_end_s': _serialize(row.get('vocal_end_s')),
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
    artist_col = _ser.api_artist_column(df)
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
    cache_key = make_key("browse:featured", count=count)
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    df = _recommender.df.copy()
    if 'energy' in df.columns and 'danceability' in df.columns:
        df['_score'] = df['energy'] * 0.5 + df['danceability'] * 0.3 + df['valence'].fillna(0.5) * 0.2
        df = df.sort_values('_score', ascending=False)
    pool = df.head(count * 3)
    selected = pool.sample(n=min(count, len(pool)))
    songs = [_song_to_dict(row, idx) for idx, row in selected.iterrows()]
    result = {"success": True, "songs": songs}
    await cache_set(cache_key, result, ttl=300)   # 5 min
    return result


@router.get("/songs/new-releases")
async def new_releases(count: int = Query(default=12, ge=1, le=50)):
    """Get newest songs (last entries in dataset)"""
    cache_key = make_key("browse:new_releases", count=count)
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    df = _recommender.df
    recent = df.tail(count * 2).sample(n=min(count, len(df)))
    songs = [_song_to_dict(row, idx) for idx, row in recent.iterrows()]
    result = {"success": True, "songs": songs}
    await cache_set(cache_key, result, ttl=300)   # 5 min
    return result


@router.get("/songs/random")
async def random_songs(count: int = Query(default=10, ge=1, le=50)):
    """Get random songs for discovery"""
    df = _recommender.df
    selected = df.sample(n=min(count, len(df)))
    songs = [_song_to_dict(row, idx) for idx, row in selected.iterrows()]
    return {"success": True, "songs": songs}


def _extract_lyric_snippet(lyrics: str, qnorm: str, window: int = 90) -> Optional[str]:
    """Snippet of lyrics centered on the (accent-insensitive) match.

    lyrics_cleaned is often a single line (no \\n), so a line-split snippet would
    just return the song's opening. Instead, locate the match in the normalized
    text and slice the same span from the original — _strip_diacritics is
    length-preserving for Latin/Vietnamese, so indices align (guarded + fallback).
    """
    norm = _strip_diacritics(lyrics)
    pos = norm.find(qnorm)
    if pos < 0:
        return None
    if len(norm) == len(lyrics):
        start = max(0, pos - 25)
        end = min(len(lyrics), pos + len(qnorm) + window)
        snippet = lyrics[start:end].strip()
        return f"{'…' if start > 0 else ''}{snippet}{'…' if end < len(lyrics) else ''}"
    # Rare non-1:1 normalization → fall back to first matching line.
    for line in lyrics.split('\n'):
        stripped = line.strip()
        if len(stripped) >= 5 and qnorm in _strip_diacritics(stripped):
            return stripped[:window + 30]
    return None


@router.get("/search")
async def smart_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Intent-aware smart search ordered in priority blocks (not blended).

    Detects what the query is and orders the blocks accordingly:
      • artist name   → artist · title · lyrics · gần nghĩa
      • title/lyrics  → title · lyrics · artist · gần nghĩa
      • nothing literal → typo-recovery (if any) · gần nghĩa first
    Literal tiers are diacritics-insensitive; semantics (e5) is accent/paraphrase
    robust and only leads when nothing matched literally.
    """
    import numpy as np
    from core.search_encoder import get_search_encoder

    df = _recommender.df
    query = q.strip()
    qnorm = _strip_diacritics(query)
    n = len(df)
    sidx = _search_index or {}

    encoder = get_search_encoder()
    semantic_available = encoder.is_ready

    # Cache: key includes semantic readiness so text-only results computed during
    # the encoder warmup don't freeze for the whole TTL once e5 finishes loading.
    cache_key = make_key("search", q=query.lower(), limit=limit, sem=semantic_available)
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    def _mask(series):
        return series.str.contains(qnorm, na=False, regex=False).values \
            if series is not None else np.zeros(n, dtype=bool)

    # ── Literal matches, by field (accent-insensitive) ────────────────────
    name_s, artist_s, album_s = sidx.get('name'), sidx.get('artist'), sidx.get('album')
    m_artist = _mask(artist_s)
    m_title = _mask(name_s) | _mask(album_s)   # album folded into title (mostly singles)
    m_lyrics = _mask(sidx.get('lyrics'))
    lyrics_col = sidx.get('lyrics_col')
    literal_any = bool(m_artist.any() or m_title.any() or m_lyrics.any())

    # Exact-equality boost + popularity → relevant, well-known songs lead each block.
    eq_name = (name_s.values == qnorm) if name_s is not None else np.zeros(n, dtype=bool)
    eq_artist = (artist_s.values == qnorm) if artist_s is not None else np.zeros(n, dtype=bool)
    pop = (pd.to_numeric(df['view_count'], errors='coerce').fillna(0).values
           if 'view_count' in df.columns else np.zeros(n))

    def _ordered(positions, eq=None):
        return sorted(positions, key=lambda i: (0 if (eq is not None and eq[i]) else 1, -float(pop[i])))

    # ── Intent: is the query (essentially) an artist name? ────────────────
    artist_intent = False
    for a in (sidx.get('artist_unique') or []):
        if not a:
            continue
        if qnorm == a or (qnorm in a and len(qnorm) >= 0.6 * len(a)) or (a in qnorm and len(a) >= 4):
            artist_intent = True
            break

    # ── Semantic (gần nghĩa) — cosine over e5 embeddings ──────────────────
    t3_list: list[int] = []
    if semantic_available:
        query_vec = encoder.encode_query(query)
        if query_vec is not None:
            t3_list = [idx for idx, _ in _recommender.semantic_search(query_vec, top_k=50)]

    # ── Typo recovery — only when nothing matched literally ───────────────
    fuzzy_artist_rows: list[int] = []
    fuzzy_title_rows: list[int] = []
    if not literal_any and len(qnorm) >= 4:
        try:
            from rapidfuzz import fuzz, process
            au = sidx.get('artist_unique')
            if au:
                hit = process.extractOne(qnorm, au, scorer=fuzz.partial_ratio, score_cutoff=88)
                if hit:
                    fuzzy_artist_rows = _ordered(sidx['artist_to_rows'].get(hit[0], []))[:limit]
            nl = sidx.get('name_list')
            if nl:
                seen_f = set(fuzzy_artist_rows)
                for _, _, i in process.extract(qnorm, nl, scorer=fuzz.token_sort_ratio,
                                               limit=limit, score_cutoff=82):
                    if i not in seen_f:
                        fuzzy_title_rows.append(i)
        except ImportError:
            pass  # rapidfuzz absent → exact + semantic only

    # ── Assemble in priority blocks ───────────────────────────────────────
    blocks = {
        'artist': _ordered(np.where(m_artist)[0].tolist(), eq_artist),
        'title': _ordered(np.where(m_title)[0].tolist(), eq_name),
        'lyrics': _ordered(np.where(m_lyrics)[0].tolist()),
        'semantic': t3_list,                 # cosine order
        'fuzzy_artist': fuzzy_artist_rows,
        'fuzzy_title': fuzzy_title_rows,
    }
    if literal_any:
        order = (['artist', 'title', 'lyrics', 'semantic'] if artist_intent
                 else ['title', 'lyrics', 'artist', 'semantic'])
    else:
        # Typo recovery is misspelled artist/title intent → it leads; else pure gần nghĩa.
        order = ['fuzzy_artist', 'fuzzy_title', 'semantic']

    MATCH_TYPE = {'artist': 'artist', 'title': 'name', 'lyrics': 'lyrics',
                  'semantic': 'vibe', 'fuzzy_artist': 'artist', 'fuzzy_title': 'name'}

    results, seen = [], set()
    for cat in order:
        for idx in blocks[cat]:
            if idx in seen:
                continue
            seen.add(idx)
            song = _song_to_dict(df.iloc[idx], idx)
            song['match_type'] = MATCH_TYPE[cat]
            song['lyric_snippet'] = (
                _extract_lyric_snippet(str(df.iloc[idx][lyrics_col]), qnorm)
                if cat == 'lyrics' and lyrics_col else None
            )
            results.append(song)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    response = {"success": True, "results": results, "query": q, "total": len(results),
                "semantic_available": semantic_available}
    await cache_set(cache_key, response, ttl=180)
    return response


# ============================================================================
# Artists
# ============================================================================

@router.get("/artists")
async def list_artists(limit: int = Query(default=50, ge=1, le=9999)):
    """List unique artists with song counts and images"""
    df = _recommender.df
    
    artist_col = _ser.api_artist_column(df)
    
    if not artist_col:
        return {"success": True, "artists": []}

    counts = df[artist_col].value_counts().head(limit)
    artists = []
    for name, count in counts.items():
        artist_songs = df[df[artist_col] == name]
        sample = artist_songs.iloc[0]
        track_id = str(sample.get('track_id', ''))
        thumbnail_url = str(sample.get('thumbnail_url', '')) if pd.notna(sample.get('thumbnail_url')) else None

        # Album art: prefer local file, fallback to thumbnail_url (shared resolver).
        has_art, art_url = _ser.resolve_album_art_url(track_id, thumbnail_url)

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

    artist_col = _ser.api_artist_column(df)

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
    cache_key = "brightify:browse:genres"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

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

    result = {"success": True, "genres": genres}
    await cache_set(cache_key, result, ttl=3600)   # 1 hour — genres are static
    return result


# ============================================================================
# Song Details & Audio
# ============================================================================

@router.get("/song/{song_id}")
async def get_song_details(song_id: str):
    """Get detailed info about a specific song. Accepts track_id (string) or integer index."""
    try:
        df = _recommender.df
        
        idx = _ser.resolve_track_id_to_index(song_id, df)
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
async def get_similar_songs(
    song_id: str,
    count: int = Query(default=10, ge=1, le=30),
    exclude: str = Query(default="", description="CSV of already-played track_ids to skip (endless radio)"),
):
    """Get songs similar to a given song using multi-faceted AI similarity"""
    try:
        exclude_ids = [t for t in exclude.split(",") if t][:120]
        df = _recommender.df
        # Resolve track_id to index (bounds_check=False: an out-of-range integer falls
        # through to the recommender → 500, preserving the original behavior).
        resolved_idx = _ser.resolve_track_id_to_index(song_id, df, bounds_check=False)
        
        results = _recommender.recommend_by_song(resolved_idx, top_k=count, exclude_ids=exclude_ids)
        df_results = results
        # Per-rec "why this song" (display only) — mirrors recommend_by_color's why chip.
        from core import explain as _explain
        seed_row = _recommender.df.iloc[resolved_idx]
        whys = _explain.build_song_why(
            df_results,
            seed_emotion=seed_row.get('fused_emotion'),
            seed_va=_recommender.song_va[resolved_idx],
            seed_tempo=seed_row.get('tempo'),
            emo_vi=_recommender._EMO_VI,
        ) if not df_results.empty else []
        songs = []
        for i, (idx, row) in enumerate(df_results.iterrows()):
            s = _song_to_dict(row, row.get('original_index', idx))
            s['similarity_score'] = round(float(row.get('similarity_score', 0)), 4)
            if i < len(whys):
                s['why'] = whys[i]
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


@router.get("/audio/stream/{track_id}")
async def stream_audio(track_id: str):
    """Stream an MP3.

    If AUDIO_CDN_BASE is configured, redirect to the CDN (CloudFront → S3) so
    range/seek and egress are handled by the CDN. Otherwise serve from local disk
    (dev/local). track_id is validated to alnum/-/_ so the redirect URL is safe.
    """
    if not all(c.isalnum() or c in '-_' for c in track_id):
        raise HTTPException(status_code=400, detail="Invalid track ID")

    if cfg.AUDIO_CDN_BASE:
        return RedirectResponse(url=f"{cfg.AUDIO_CDN_BASE}/{track_id}.mp3", status_code=302)

    file_path = _music_path / f"{track_id}.mp3"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        # CORS so the Web Audio crossfade (el.crossOrigin='anonymous' + MediaElementSource)
        # can analyse/visualise this stream when served from disk (dev / non-CDN). In prod the
        # CDN branch above handles CORS via CloudFront. '*' is valid here (public, no credentials).
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD",
        },
    )


@router.get("/audio/status/{track_id}")
async def get_audio_status(track_id: str):
    """Check if audio is available for a track (local file or CDN manifest)."""
    available = track_id in _mp3_cache
    # file_size only meaningful in local mode (0 when served from the CDN)
    file_size = 0
    if available and not cfg.AUDIO_CDN_BASE and _music_path:
        fp = _music_path / f"{track_id}.mp3"
        if fp.exists():
            file_size = fp.stat().st_size
    return {"track_id": track_id, "available": available, "file_size": file_size}


@router.get("/audio/batch-status")
async def get_batch_audio_status(track_ids: str = Query(..., description="Comma-separated track IDs")):
    """Batch check audio availability (local file or CDN manifest)."""
    ids = [tid.strip() for tid in track_ids.split(",") if tid.strip()]
    result = {tid: (tid in _mp3_cache) for tid in ids[:100]}
    return {"status": result, "available_count": sum(result.values()), "total": len(result)}


@router.get("/album-art/{track_id}")
async def get_album_art(track_id: str):
    """Serve album art image"""
    if not all(c.isalnum() or c in '-_' for c in track_id):
        raise HTTPException(status_code=400, detail="Invalid track ID")

    art_path = cfg.ALBUM_ART_DIR / f"{track_id}.jpg"
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
