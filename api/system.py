"""System API routes (health, stats, config, backtest evaluation)."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import hmac
import os
import numpy as np
import pandas as pd
import time as _time

import config
from api.utils import dataframe_to_dict

# Admin access via API key in env (no user auth needed)
_ADMIN_KEY = os.environ.get("BRIGHTIFY_ADMIN_KEY", "")


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
_evaluator = None


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


class BacktestRequest(BaseModel):
    top_k: int = Field(default=10, ge=5, le=50)
    metrics: Optional[List[str]] = None


class WeightTestRequest(BaseModel):
    weights: List[float] = Field(..., min_length=4, max_length=4)
    colors: List[str]
    top_k: int = Field(default=10, ge=1, le=50)


_dataframe_to_dict = dataframe_to_dict


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

def _get_evaluator():
    global _evaluator
    if _evaluator is None:
        from tools.backtest import RecommendationEvaluator
        _evaluator = RecommendationEvaluator(_recommender)
    return _evaluator


@router.post("/api/backtest/run")
async def run_backtest(request: BacktestRequest, req: Request = None):
    require_admin(req)
    try:
        from tools.backtest import sanitize_for_json
        evaluator = _get_evaluator()
        top_k = request.top_k
        requested = request.metrics

        report = {
            'timestamp': pd.Timestamp.now().isoformat(),
            'dataset_size': evaluator.n_songs,
            'top_k': top_k,
            'metrics': {},
        }

        metric_map = {
            'precision': ('precision_at_k', lambda: evaluator.precision_at_k_by_quadrant(top_k=top_k)),
            'ndcg': ('ndcg', lambda: evaluator.ndcg_at_k(top_k=top_k)),
            'coherence': ('emotional_coherence', lambda: evaluator.emotional_coherence(top_k=top_k)),
            'diversity': ('intra_list_diversity', lambda: evaluator.intra_list_diversity(top_k=top_k)),
            'coverage': ('catalog_coverage', lambda: evaluator.catalog_coverage(top_k=top_k)),
            'alignment': ('color_emotion_alignment', lambda: evaluator.color_emotion_alignment()),
            'consistency': ('similar_song_consistency', lambda: evaluator.similar_song_consistency()),
            'weights': ('weight_grid_search', lambda: evaluator.weight_grid_search(top_k=top_k)),
            'mood_accuracy': ('mood_keyword_accuracy', lambda: evaluator.mood_keyword_accuracy(top_k=top_k)),
            'timing': ('response_time', lambda: evaluator.response_time_benchmark()),
        }

        start = _time.time()
        if requested:
            for m in requested:
                if m in metric_map:
                    key, fn = metric_map[m]
                    report['metrics'][key] = fn()
        else:
            for m, (key, fn) in metric_map.items():
                report['metrics'][key] = fn()

        report['evaluation_time_seconds'] = round(_time.time() - start, 2)
        report['overall_score'] = evaluator._compute_overall_score(report['metrics'])

        return JSONResponse(content={"success": True, "report": sanitize_for_json(report)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Backtest execution failed")


@router.post("/api/backtest/test-weights")
async def test_custom_weights(request: WeightTestRequest, req: Request = None):
    require_admin(req)
    try:
        evaluator = _get_evaluator()
        colors = ['#' + c if not c.startswith('#') else c for c in request.colors]

        custom_recs = evaluator._recommend_with_custom_weights(colors, request.weights, top_k=request.top_k)
        default_recs = _recommender.recommend_by_colors(colors, top_k=request.top_k)

        def recs_summary(recs):
            if len(recs) == 0:
                return {'count': 0, 'songs': [], 'avg_score': 0}
            songs = _dataframe_to_dict(recs)
            avg = np.mean([s.get('similarity_score', 0) for s in songs])
            return {'count': len(songs), 'songs': songs, 'avg_score': round(float(avg), 4)}

        custom_names = set(custom_recs['track_name'].tolist()) if len(custom_recs) > 0 else set()
        default_names = set(default_recs['track_name'].tolist()) if len(default_recs) > 0 else set()
        overlap = len(custom_names & default_names)
        total = len(custom_names | default_names) or 1

        from tools.backtest import sanitize_for_json
        return JSONResponse(content=sanitize_for_json({
            "success": True,
            "custom_weights": request.weights,
            "default_weights": [0.25, 0.35, 0.20, 0.20],
            "custom_results": recs_summary(custom_recs),
            "default_results": recs_summary(default_recs),
            "overlap": {"count": overlap, "jaccard_similarity": round(overlap / total, 4)},
        }))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Weight test failed")


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

        from tools.backtest import sanitize_for_json
        return JSONResponse(content=sanitize_for_json({"success": True, "stats": stats}))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Dataset stats failed")
