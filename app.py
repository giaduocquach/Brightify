"""
Brightify — AI-Powered Vietnamese Music Streaming Platform
"""

import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from core.recommendation_engine import get_recommender
from core.image_analysis import get_image_analyzer

from api import music as music_routes
from api import recommend as recommend_routes
from api import system as system_routes
from api.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)

# Static files & media directories
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)

music_path = Path(__file__).parent / "music_files"
music_path.mkdir(exist_ok=True)
album_art_path = Path(__file__).parent / "album_art"
album_art_path.mkdir(exist_ok=True)
artist_images_path = Path(__file__).parent / "artist_images"
artist_images_path.mkdir(exist_ok=True)

recommender = None
image_analyzer = None


def init_recommender():
    global recommender
    if recommender is None:
        recommender = get_recommender()


def init_image_analyzer():
    global image_analyzer
    if image_analyzer is None:
        try:
            image_analyzer = get_image_analyzer()
            recommend_routes.set_image_analyzer(image_analyzer)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Brightify v7.0 — Starting up...")
    init_recommender()
    init_image_analyzer()
    music_routes.init(recommender, music_path, artist_images_path)
    recommend_routes.init(recommender, image_analyzer, init_image_analyzer)
    system_routes.init(recommender, image_analyzer)
    logger.info("All systems ready")
    yield


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

app.include_router(music_routes.router)
app.include_router(recommend_routes.router)
app.include_router(system_routes.router)


@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = static_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Brightify</h1><p>Frontend not found.</p>")


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if not request.url.path.startswith("/api/") and not request.url.path.startswith("/static/"):
        index_path = static_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"success": False, "error": "Not found"})


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(status_code=500, content={"success": False, "error": "Internal server error"})


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True, log_level="warning")
