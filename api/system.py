"""System API routes (health, stats, config, backtest evaluation)."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import hmac

import config
from api.utils import sanitize_for_json

# Admin access via API key — supports Docker secrets via config._read_secret_or_env
_ADMIN_KEY = config.BRIGHTIFY_ADMIN_KEY


def require_admin(request: Request):
    """Require admin API key via X-Admin-Key header."""
    if not _ADMIN_KEY:
        return  # No key configured = open access (dev mode)
    key = request.headers.get("X-Admin-Key", "")
    if not hmac.compare_digest(key, _ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Admin API key required")

router = APIRouter(tags=["System"])

_recommender = None
_image_analyzer = None


def init(recommender, image_analyzer_ref):
    global _recommender, _image_analyzer
    _recommender = recommender
    _image_analyzer = image_analyzer_ref


class HealthResponse(BaseModel):
    status: str
    version: str = "7.1.0"
    recommender_loaded: bool = False
    song_count: int = 0
    has_embeddings: bool = False
    db_connected: bool = False
    api_docs: str = "/docs"


# ============================================================================
# System endpoints
# ============================================================================

@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    recommender_ok = _recommender is not None and _recommender.df is not None
    song_count = len(_recommender.df) if recommender_ok else 0
    has_embeddings = (recommender_ok and _recommender.embeddings is not None
                      and len(_recommender.embeddings) > 0)

    db_ok = False
    try:
        from db.engine import SessionLocal
        from sqlalchemy import text
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    status = "healthy" if (recommender_ok and db_ok) else "degraded"
    return HealthResponse(
        status=status,
        recommender_loaded=recommender_ok,
        song_count=song_count,
        has_embeddings=has_embeddings,
        db_connected=db_ok,
    )


@router.get("/api/statistics")
async def get_statistics():
    try:
        stats = _recommender.get_statistics()
        return {
            "total_songs": stats['total_songs'],
            "audio_features_count": stats['audio_features'],
            "has_embeddings": stats['has_embeddings'],
            "embedding_dimension": stats.get('embedding_dimension'),
            "has_colors": stats['has_colors'],
            "model_info": {
                "phobert": config.PHOBERT_MODEL,
                "color_mapping": "Palmer et al. 2013 + Russell Model",
                "color_distance": config.COLOR_DISTANCE_METHOD,
                "fusion_method": "Task-specific weighted fusion",
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/moods")
async def get_available_moods():
    return {
        "success": True,
        "moods": list(config.MOOD_KEYWORDS.keys()),
        "quadrants": {n: i['name'] for n, i in config.MOOD_QUADRANTS.items()},
    }


@router.get("/api/config")
async def get_configuration():
    return {
        "success": True,
        "config": {
            "weights": {
                "color_query": config.WEIGHTS_COLOR_QUERY,
                "mood_query": config.WEIGHTS_MOOD_QUERY,
                "song_query": config.WEIGHTS_SONG_QUERY,
                "lyrics_query": config.WEIGHTS_LYRICS_QUERY,
            },
            "default_top_k": config.DEFAULT_TOP_K,
            "diversity_penalty": config.DIVERSITY_PENALTY,
            "min_similarity_threshold": config.MIN_SIMILARITY_THRESHOLD,
            "color_distance_method": config.COLOR_DISTANCE_METHOD,
        }
    }


@router.get("/api/image/status")
async def image_service_status():
    return {
        "available": _image_analyzer is not None,
        "model": "CLIP ViT-B/32" if _image_analyzer else None,
        "device": _image_analyzer.device if _image_analyzer else None,
    }


# ============================================================================
# Backtest endpoints
# ============================================================================
# Legacy backtest (tools/backtest.py) decommissioned — see §5 of
# docs/PLAN_BACKTEST_METRICS.md. Run/test-weights routes will be re-wired to
# tools.backtest_v2 in Phase 3. dataset-stats is kept below.


@router.get("/api/backtest/dataset-stats")
async def get_dataset_stats(request: Request):
    require_admin(request)
    try:
        df = _recommender.df
        stats = {'total_songs': len(df), 'columns': list(df.columns)}

        if 'mood_quadrant' in df.columns:
            stats['mood_distribution'] = df['mood_quadrant'].value_counts().to_dict()
        if 'fused_emotion' in df.columns:
            stats['emotion_distribution'] = df['fused_emotion'].value_counts().to_dict()

        audio_stats = {}
        for f in ['valence', 'energy', 'danceability', 'acousticness', 'tempo']:
            if f in df.columns:
                audio_stats[f] = {
                    'mean': round(float(df[f].mean()), 4), 'std': round(float(df[f].std()), 4),
                    'min': round(float(df[f].min()), 4), 'max': round(float(df[f].max()), 4),
                }
        stats['audio_features'] = audio_stats

        if 'color_hex' in df.columns:
            stats['unique_colors'] = int(df['color_hex'].nunique())
            stats['top_colors'] = df['color_hex'].value_counts().head(10).to_dict()
        if 'sentiment_category' in df.columns:
            stats['sentiment_distribution'] = df['sentiment_category'].value_counts().to_dict()

        stats['has_embeddings'] = _recommender.embeddings is not None
        if _recommender.embeddings is not None:
            stats['embedding_shape'] = list(_recommender.embeddings.shape)

        return JSONResponse(content=sanitize_for_json({"success": True, "stats": stats}))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Dataset stats failed")
