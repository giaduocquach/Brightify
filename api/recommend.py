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
from api.cache import cache_get, cache_set, make_key

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
    novelty: float = Field(default=0.5, ge=0.0, le=1.0,
                           description="E8 dig-deeper dial: 0.5 neutral, >0.5 deep cuts, <0.5 familiar")

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
    cache_key = make_key(
        "reco:color",
        colors=sorted(request.colors),
        top_k=request.top_k,
        weights=request.weights,
        diversity_penalty=request.diversity_penalty,
        novelty=request.novelty,
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        results = _recommender.recommend_by_colors(
            request.colors, top_k=request.top_k,
            weights=request.weights,
            diversity_penalty=request.diversity_penalty,
            novelty=request.novelty,
        )
        # V12: colour→emotion bridge for the UI chip (the feature's core value made
        # visible — Palmer/PLOS: emotion mediates the colour↔music link).
        bridge = _recommender.color_emotion_bridge(request.colors)
        # V23: 2 colours = mood JOURNEY (ordered A→B, Iso-Principle). Metadata for UI
        # to render "Từ [mood A] → [mood B]" + gradient + arrow.
        journey = None
        if len(request.colors) == 2 and getattr(config, "COLOR_JOURNEY_ENABLED", False) \
                and len(bridge) == 2:
            journey = {
                "ordered": True,
                "from": {"hex": bridge[0].get("hex"), "mood": bridge[0].get("emotion_vi")},
                "to":   {"hex": bridge[1].get("hex"), "mood": bridge[1].get("emotion_vi")},
            }
        payload = RecommendationResponse(
            success=True,
            query={"colors": request.colors, "top_k": request.top_k,
                   "weights": request.weights or config.WEIGHTS_COLOR_QUERY,
                   "diversity_penalty": request.diversity_penalty,
                   "bridge": bridge, "journey": journey},
            results=_dataframe_to_dict(results),
            count=len(results),
        )
        await cache_set(cache_key, payload.model_dump(), ttl=600)   # 10 min
        return payload
    except Exception as e:
        logger.exception("Color recommendation failed")
        raise HTTPException(status_code=500, detail="Color recommendation failed")


@router.post("/lyrics", response_model=RecommendationResponse)
async def search_by_lyrics(request: LyricsSearchRequest):
    """Search songs by Vietnamese lyrics keywords via PhoBERT"""
    cache_key = make_key(
        "reco:lyrics",
        keywords=request.keywords.lower().strip(),
        top_k=request.top_k,
        weights=request.weights,
        diversity_penalty=request.diversity_penalty,
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        results = _recommender.recommend_by_lyrics_keywords(
            request.keywords, top_k=request.top_k,
            weights=request.weights,
            diversity_penalty=request.diversity_penalty,
        )
        payload = RecommendationResponse(
            success=True,
            query={"keywords": request.keywords, "top_k": request.top_k},
            results=_dataframe_to_dict(results),
            count=len(results),
        )
        await cache_set(cache_key, payload.model_dump(), ttl=600)   # 10 min
        return payload
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
# ============================================================================
