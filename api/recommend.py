"""AI recommendation API routes (color, mood, lyrics, image)."""

import logging

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
import numpy as np
import pandas as pd
from PIL import Image
from io import BytesIO

import config
from api.utils import dataframe_to_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommend", tags=["AI Recommendations"])

_recommender = None
_image_analyzer = None
_init_image_fn = None


def _enrich_album_art(song: dict):
    """Add album art URL to a song dict, with thumbnail_url fallback."""
    tid = song.get('track_id', '')
    if tid:
        from pathlib import Path
        art_path = Path(__file__).parent.parent / 'album_art' / f'{tid}.jpg'
        if art_path.exists():
            song['has_album_art'] = True
            song['album_art_url'] = f'/api/album-art/{tid}'
        else:
            thumb = song.get('thumbnail_url')
            if thumb and not pd.isna(thumb):
                song['has_album_art'] = True
                song['album_art_url'] = str(thumb)
            else:
                song['has_album_art'] = False
                song['album_art_url'] = None
    else:
        song['has_album_art'] = False
        song['album_art_url'] = None


def init(recommender, image_analyzer, init_image_fn):
    global _recommender, _image_analyzer, _init_image_fn
    _recommender = recommender
    _image_analyzer = image_analyzer
    _init_image_fn = init_image_fn


def set_image_analyzer(analyzer):
    global _image_analyzer
    _image_analyzer = analyzer


# ============================================================================
# Request/Response Models
# ============================================================================

class ColorRecommendationRequest(BaseModel):
    colors: List[str] = Field(..., description="List of hex colors (e.g., ['#FF5733'])")
    top_k: int = Field(default=10, ge=1, le=50)
    weights: Optional[List[float]] = None
    diversity_penalty: float = Field(default=0.15, ge=0.0, le=1.0)

    @validator('colors')
    def validate_colors(cls, v):
        validated = []
        for color in v:
            c = color if color.startswith('#') else '#' + color
            if len(c) != 7 or not all(ch in '0123456789abcdefABCDEF' for ch in c[1:]):
                raise ValueError(f"Invalid hex color: {color}")
            validated.append(c)
        return validated


class LyricsSearchRequest(BaseModel):
    keywords: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    weights: Optional[List[float]] = None
    diversity_penalty: float = Field(default=0.15, ge=0.0, le=1.0)


class RecommendationResponse(BaseModel):
    success: bool
    query: Dict[str, Any]
    results: List[Dict[str, Any]]
    count: int
    message: Optional[str] = None


class ImageRecommendationResponse(BaseModel):
    success: bool
    image_analysis: Dict[str, Any]
    results: List[Dict[str, Any]]
    count: int
    message: Optional[str] = None


_dataframe_to_dict = dataframe_to_dict


# ============================================================================
# Recommendation Endpoints
# ============================================================================

@router.post("/color", response_model=RecommendationResponse)
async def recommend_by_color(request: ColorRecommendationRequest):
    """Recommend songs by color(s) using CIEDE2000 perceptual color distance"""
    try:
        results = _recommender.recommend_by_colors(
            request.colors, top_k=request.top_k,
            weights=request.weights,
            diversity_penalty=request.diversity_penalty,
        )
        return RecommendationResponse(
            success=True,
            query={"colors": request.colors, "top_k": request.top_k,
                   "weights": request.weights or config.WEIGHTS_COLOR_QUERY,
                   "diversity_penalty": request.diversity_penalty},
            results=_dataframe_to_dict(results),
            count=len(results),
        )
    except Exception as e:
        logger.exception("Color recommendation failed")
        raise HTTPException(status_code=500, detail="Color recommendation failed")


@router.post("/lyrics", response_model=RecommendationResponse)
async def search_by_lyrics(request: LyricsSearchRequest):
    """Search songs by Vietnamese lyrics keywords via PhoBERT"""
    try:
        results = _recommender.recommend_by_lyrics_keywords(
            request.keywords, top_k=request.top_k,
            weights=request.weights,
            diversity_penalty=request.diversity_penalty,
        )
        return RecommendationResponse(
            success=True,
            query={"keywords": request.keywords, "top_k": request.top_k},
            results=_dataframe_to_dict(results),
            count=len(results),
        )
    except Exception as e:
        logger.exception("Lyrics search failed")
        raise HTTPException(status_code=500, detail="Lyrics search failed")


@router.post("/image", response_model=ImageRecommendationResponse)
async def recommend_by_image(
    file: UploadFile = File(...),
    top_k: int = Form(default=10, ge=1, le=50),
    diversity_penalty: float = Form(default=0.15, ge=0.0, le=1.0),
):
    """Recommend songs based on uploaded image using CLIP + color analysis"""
    global _image_analyzer

    allowed = {'image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff'}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported: {file.content_type}")

    # Check Content-Length header first to reject oversized uploads early
    MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB
    if file.size is not None and file.size > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # Read in chunks to prevent memory exhaustion from malicious uploads
    chunks = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)  # 64KB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")
        chunks.append(chunk)
    contents = b''.join(chunks)

    if _image_analyzer is None:
        try:
            _init_image_fn()
            from api.recommend import _image_analyzer as _ia
        except Exception:
            raise HTTPException(status_code=503, detail="Image analysis unavailable")

    if _image_analyzer is None:
        raise HTTPException(status_code=503, detail="Image model failed to load")

    try:
        Image.MAX_IMAGE_PIXELS = 25_000_000  # 25MP limit against decompression bomb
        image = Image.open(BytesIO(contents))
        analysis = _image_analyzer.analyze_image(image)
        results = _recommender.recommend_by_image(
            image_analysis=analysis, top_k=top_k, diversity_penalty=diversity_penalty,
        )

        summary = {
            'dominant_colors': analysis['dominant_colors'],
            'color_weights': [round(w, 3) for w in analysis['color_weights']],
            'mood_label': analysis['mood_label'],
            'mood_description': analysis['mood_description'],
            'valence': round(analysis['valence'], 3),
            'arousal': round(analysis['arousal'], 3),
            'brightness': round(analysis['brightness'], 3),
            'saturation': round(analysis['saturation'], 3),
            'warmth': round(analysis['warmth'], 3),
            'contrast': round(analysis['contrast'], 3),
            'top_emotions': dict(sorted(analysis['emotion_scores'].items(), key=lambda x: -x[1])[:5]),
            'top_scenes': dict(sorted(analysis['scene_scores'].items(), key=lambda x: -x[1])[:3]),
            # Enhanced analysis fields
            'content_type': analysis.get('content_type', 'unknown'),
            'has_person': analysis.get('has_person', False),
            'person_confidence': round(analysis.get('person_confidence', 0), 3),
            'expression': analysis.get('expression'),
            'lighting': analysis.get('lighting'),
            'color_variety': round(analysis.get('color_variety', 0), 3),
        }

        return ImageRecommendationResponse(
            success=True,
            image_analysis=summary,
            results=_dataframe_to_dict(results),
            count=len(results),
            message=analysis['mood_description'],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Image analysis failed")
        raise HTTPException(status_code=500, detail="Image analysis failed")


# ============================================================================
# Emotion Journey Endpoint
# ============================================================================

class EmotionJourneyRequest(BaseModel):
    start_valence: float = Field(..., ge=0.0, le=1.0)
    start_arousal: float = Field(..., ge=0.0, le=1.0)
    end_valence: float = Field(..., ge=0.0, le=1.0)
    end_arousal: float = Field(..., ge=0.0, le=1.0)
    steps: int = Field(default=10, ge=6, le=15)


@router.post("/emotion-journey")
async def emotion_journey(request: EmotionJourneyRequest):
    """Generate an Iso-Principle emotion journey playlist from start → end mood."""
    try:
        result = _recommender.generate_emotion_journey(
            start_valence=request.start_valence,
            start_arousal=request.start_arousal,
            end_valence=request.end_valence,
            end_arousal=request.end_arousal,
            steps=request.steps,
        )

        # Enrich songs with album art URLs
        for song in result['songs']:
            _enrich_album_art(song)

        return JSONResponse(content={
            'success': True,
            'songs': result['songs'],
            'waypoints': result['waypoints'],
            'journey_info': result['journey_info'],
            'count': len(result['songs']),
        })
    except Exception as e:
        logger.exception("Emotion journey generation failed")
        raise HTTPException(status_code=500, detail="Emotion journey generation failed")


# ============================================================================

# ============================================================================
# Smart Context Engine Endpoint
# ============================================================================

class ContextMixRequest(BaseModel):
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    activity: Optional[str] = None
    season: Optional[str] = None
    weather: Optional[str] = None
    user_history: Optional[List[Dict[str, Any]]] = None
    user_liked: Optional[List[Dict[str, Any]]] = None
    count: int = Field(default=15, ge=5, le=30)

    @validator('activity')
    def validate_activity(cls, v):
        if v is not None:
            allowed = ['workout', 'study', 'relax', 'commute', 'party',
                        'sleep', 'focus', 'cooking', 'morning_routine']
            if v not in allowed:
                raise ValueError(f'Activity must be one of: {", ".join(allowed)}')
        return v

    @validator('season')
    def validate_season(cls, v):
        if v is not None and v not in ('spring', 'summer', 'autumn', 'winter'):
            raise ValueError('Season must be spring, summer, autumn, or winter')
        return v

    @validator('weather')
    def validate_weather(cls, v):
        if v is not None and v not in ('sunny', 'cloudy', 'rainy', 'stormy', 'snowy'):
            raise ValueError('Weather must be sunny, cloudy, rainy, stormy, or snowy')
        return v


@router.post("/context-mix")
async def context_mix(request: ContextMixRequest):
    """Generate context-aware recommendations using circadian rhythm,
    activity context, weather/season, and user taste profile."""
    try:
        result = _recommender.smart_context_recommend(
            hour=request.hour,
            day_of_week=request.day_of_week,
            activity=request.activity,
            season=request.season,
            weather=request.weather,
            user_history=request.user_history,
            user_liked=request.user_liked,
            count=request.count,
        )

        for song in result.get('songs', []):
            _enrich_album_art(song)

        return JSONResponse(content={
            'success': True,
            'songs': result.get('songs', []),
            'context': result.get('context', {}),
            'count': len(result.get('songs', [])),
        })
    except Exception as e:
        logger.exception("Context mix recommendation failed")
        raise HTTPException(status_code=500, detail="Context mix recommendation failed")


# ============================================================================
# Musical DNA Endpoint
# ============================================================================

class MusicalDNARequest(BaseModel):
    user_liked: Optional[List[Dict[str, Any]]] = None
    user_history: Optional[List[Dict[str, Any]]] = None


@router.post("/musical-dna")
async def musical_dna(request: MusicalDNARequest):
    """Compute user's Musical DNA / Taste Profile from listening data."""
    try:
        if not request.user_liked and not request.user_history:
            raise HTTPException(
                status_code=400,
                detail="At least user_liked or user_history is required"
            )

        result = _recommender.compute_musical_dna(
            user_liked=request.user_liked,
            user_history=request.user_history,
        )

        if result is None:
            raise HTTPException(
                status_code=400,
                detail="Not enough data to compute Musical DNA (need at least 3 unique songs)"
            )

        # Enrich recommendation songs with album art
        for song in result.get('recommendations', []):
            _enrich_album_art(song)

        return JSONResponse(content={
            'success': True,
            **result,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Musical DNA computation failed")
        raise HTTPException(status_code=500, detail="Musical DNA computation failed")
