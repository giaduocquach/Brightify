"""AI recommendation API routes (color)."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any

import config
from api.utils import dataframe_to_dict
from api.cache import cache_get, cache_set, make_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommend", tags=["AI Recommendations"])

_recommender = None


def init(recommender):
    global _recommender
    _recommender = recommender


# ============================================================================
# Request/Response Models
# ============================================================================

class ColorRecommendationRequest(BaseModel):
    colors: List[str] = Field(..., description="List of hex colors (e.g., ['#FF5733'])")
    top_k: int = Field(default=10, ge=1, le=50)
    # No `weights`: recommend-by-color is pure V-A (rank-space RBF) — there are no
    # multi-signal weights to set (F2/F3 ablation removed lyric/emotion signals).
    diversity_penalty: float = Field(default=0.15, ge=0.0, le=1.0)
    # Endless-radio: track_ids already played this session, excluded from the next
    # batch so the queue extends with fresh songs instead of looping. Capped to keep
    # the request bounded (older plays are fine to resurface — satiation has reset).
    exclude_ids: List[str] = Field(default_factory=list, max_items=120)

    @validator('colors')
    def validate_colors(cls, v):
        validated = []
        for color in v:
            c = color if color.startswith('#') else '#' + color
            if len(c) != 7 or not all(ch in '0123456789abcdefABCDEF' for ch in c[1:]):
                raise ValueError(f"Invalid hex color: {color}")
            validated.append(c)
        return validated


class RecommendationResponse(BaseModel):
    success: bool
    query: Dict[str, Any]
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
    # Skip the cache for endless-radio extension calls: each carries a different,
    # growing exclude set, so caching would just fill with single-use entries.
    use_cache = not request.exclude_ids
    cache_key = make_key(
        "reco:color",
        colors=sorted(request.colors),
        top_k=request.top_k,
        diversity_penalty=request.diversity_penalty,
    )
    if use_cache:
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

    try:
        results = _recommender.recommend_by_colors(
            request.colors, top_k=request.top_k,
            diversity_penalty=request.diversity_penalty,
            exclude_ids=request.exclude_ids,
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
                   "signal": "valence-arousal (rank-space RBF)",
                   "diversity_penalty": request.diversity_penalty,
                   "bridge": bridge, "journey": journey},
            results=_dataframe_to_dict(results),
            count=len(results),
        )
        if use_cache:
            await cache_set(cache_key, payload.model_dump(), ttl=600)   # 10 min
        return payload
    except Exception as e:
        logger.exception("Color recommendation failed")
        raise HTTPException(status_code=500, detail="Color recommendation failed")


