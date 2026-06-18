"""
Brightify — AI-Powered Vietnamese Music Streaming Platform
"""

import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

import logging_config  # noqa: F401 — sets up loguru + stdlib intercept
from loguru import logger
import config as cfg

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from core.recommendation_engine import get_recommender

from api import music as music_routes
from api import recommend as recommend_routes
from api import system as system_routes
from api import cache as cache_module
from api.rate_limit import RateLimitMiddleware, set_redis as _rl_set_redis

# Static files & media directories
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)

# Built React SPA (Vite output). When present, it is served at "/".
spa_path = Path(__file__).parent / "static_spa"

music_path = cfg.MUSIC_DIR
album_art_path = cfg.ALBUM_ART_DIR
artist_images_path = cfg.ARTIST_IMAGES_DIR

recommender = None


def _verify_alignment(rec):
    """Guardrail: the engine indexes embeddings POSITIONALLY (df.iloc[i] ↔ matrix[i]).
    After init + the crossfade hydration merge, check the row counts still match so a future
    merge/delete that reorders or drops rows is caught at startup — not as silently wrong
    color/similar recommendations. Non-fatal (log only): never block serving on a false positive."""
    if rec is None or getattr(rec, "df", None) is None:
        return
    try:
        import numpy as _np
        n = len(rec.df)
        issues = []
        if getattr(rec, "n_songs", n) != n:
            issues.append(f"n_songs={rec.n_songs}!=len(df)={n}")
        for attr in ("mert_matrix", "embeddings", "song_va"):
            m = getattr(rec, attr, None)
            if isinstance(m, _np.ndarray) and m.shape[0] != n:
                issues.append(f"{attr}.shape[0]={m.shape[0]}!=len(df)={n}")
        if issues:
            logger.error(f"[alignment] EMBEDDING↔DF MISALIGNED — recommendations may be WRONG: {issues}")
        else:
            logger.info(f"[alignment] OK — df/embeddings aligned at {n} songs")
    except Exception as e:
        logger.warning(f"[alignment] check skipped: {e}")


def init_recommender():
    global recommender
    if recommender is None:
        recommender = get_recommender()
        _hydrate_crossfade_columns(recommender)
        _verify_alignment(recommender)


def _hydrate_crossfade_columns(rec):
    """Merge Smart Crossfade DB columns (loudness_lufs + cue points + downbeats)
    into the recommender's in-memory dataframe. The dataframe is sourced from CSV
    which doesn't include these later-added columns, so we lazy-join from DB.

    Idempotent and best-effort — if DB unavailable, falls back silently and
    planCrossfade graceful defaults kick in.
    """
    if rec is None or rec.df is None:
        return
    # duration_ms is reconciled to the real file length in the DB (ffprobe); the CSV's
    # track_duration_ms is stale. Pull it so planCrossfade gets the true duration — a wrong
    # duration breaks the outroLen → blend/sequential decision even when vocal_end_s is present.
    crossfade_cols = ('loudness_lufs', 'fade_out_cue_s', 'fade_in_cue_s', 'downbeat_times_json',
                      'vocal_start_s', 'vocal_end_s', 'duration_ms')
    try:
        from db.engine import engine
        from sqlalchemy import text
        import pandas as _pd
        with engine.connect() as conn:
            db_df = _pd.read_sql(
                text("""
                    SELECT track_id, loudness_lufs, fade_out_cue_s, fade_in_cue_s, downbeat_times_json,
                           vocal_start_s, vocal_end_s, duration_ms
                    FROM songs
                """),
                conn,
            )
        if db_df.empty or 'track_id' not in rec.df.columns:
            return
        # Drop any existing values for these columns in df, then merge from DB
        for col in crossfade_cols:
            if col in rec.df.columns:
                rec.df = rec.df.drop(columns=[col])
        rec.df = rec.df.merge(db_df, on='track_id', how='left')
        n_lufs = int(rec.df['loudness_lufs'].notna().sum())
        n_cue = int(rec.df['fade_out_cue_s'].notna().sum())
        logger.info(f"[crossfade] Hydrated DB columns: LUFS={n_lufs}, cue_points={n_cue}")
    except Exception as e:
        logger.warning(f"[crossfade] DB hydration failed (using CSV defaults): {e}")



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Brightify v7.2 — Starting up...")
    logger.info(
        "Serving paths: data={} music={} album_art={} artist_images={}",
        cfg.DATA_DIR,
        music_path,
        album_art_path,
        artist_images_path,
    )

    # ── Redis (optional — graceful fallback when unavailable) ──────────────
    _redis_client = None
    _redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis.asyncio as _redis_asyncio
        _redis_client = _redis_asyncio.from_url(_redis_url, decode_responses=True)
        await _redis_client.ping()
        cache_module.set_redis(_redis_client)
        _rl_set_redis(_redis_client)
        logger.info(f"Redis connected: {_redis_url}")
    except Exception as _e:
        logger.warning(
            f"Redis unavailable ({_e.__class__.__name__}: {_e}) — "
            "cache disabled, using in-memory rate limiter"
        )
        _redis_client = None

    # ── Core modules ───────────────────────────────────────────────────────
    init_recommender()
    music_routes.init(recommender, music_path, artist_images_path)
    recommend_routes.init(recommender)
    system_routes.init(recommender)
    logger.info("All systems ready")

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────
    if _redis_client is not None:
        await _redis_client.aclose()
        logger.info("Redis connection closed")


app = FastAPI(
    title="Brightify API",
    description="AI-powered Vietnamese music streaming with color, image, mood, and lyrics recommendations.",
    version="7.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
_cors_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Serve the built SPA's hashed assets (Vite emits them under /assets).
_spa_assets = spa_path / "assets"
if _spa_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_spa_assets)), name="spa-assets")

app.include_router(music_routes.router)
app.include_router(recommend_routes.router)
app.include_router(system_routes.router)


def _spa_index() -> Path | None:
    """Built SPA index if available, else the legacy static index."""
    spa_index = spa_path / "index.html"
    if spa_index.exists():
        return spa_index
    legacy = static_path / "index.html"
    return legacy if legacy.exists() else None


@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = _spa_index()
    if index_path:
        return FileResponse(index_path)
    return HTMLResponse("<h1>Brightify</h1><p>Frontend not found.</p>")


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    path = request.url.path
    if not path.startswith(("/api/", "/static/", "/assets/")):
        index_path = _spa_index()
        if index_path:
            return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"success": False, "error": "Not found"})


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(status_code=500, content={"success": False, "error": "Internal server error"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True, log_level="warning")
