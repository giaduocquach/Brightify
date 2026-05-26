# Brightify — Copilot Instructions

## Project Overview
Brightify is a Vietnamese AI-powered music streaming platform that uses multimodal signals (audio features, lyrics NLP, color psychology, image analysis) to recommend songs. It serves ~4,300+ Vietnamese songs with a FastAPI backend and vanilla JS frontend.

## Tech Stack
- **Backend**: FastAPI 0.108+, Python 3.10+, Uvicorn
- **Database**: PostgreSQL 17, SQLAlchemy 2.0 (sync), Alembic migrations, pgvector (768-dim), pg_trgm
- **AI/ML**: PhoBERT (vinai/phobert-base), CLIP (openai/clip-vit-base-patch32), Essentia-TF, scikit-learn
- **NLP**: Vietnamese Emotion Lexicon (730+ words, 13 categories), pyvi ViTokenizer
- **Frontend**: Vanilla HTML/CSS/JS SPA, Web Audio API, Canvas visualizer
- **Data Pipeline**: ytmusicapi + yt-dlp (YouTube), Essentia-TF audio features

## Architecture
```
app.py                → FastAPI entry point (lifespan, CORS, rate limiting)
config.py             → Centralized configuration (weights, paths, features)
api/
  music.py            → Browse/search/stream endpoints (26 routes)
  recommend.py        → AI recommendation endpoints (6 routes)
  system.py           → Health, stats, admin backtest (9 routes)
  rate_limit.py       → Sliding-window rate limiter middleware
  utils.py            → Shared helpers (dataframe_to_dict)
core/
  recommendation_engine.py → MusicRecommender: 7-signal multimodal fusion
  emotion_analysis.py      → PhoBERT + Vietnamese lexicon + V-A mapping
  advanced_color_mapping.py → CIEDE2000 color-emotion mapping (Jonauskaite 2020)
  image_analysis.py        → CLIP zero-shot scene/emotion classification
db/
  models.py           → SQLAlchemy ORM (star schema: Song, Artist, Album, etc.)
  engine.py           → PostgreSQL connection pool
  seed.py             → ETL pipeline: CSV → PostgreSQL + pgvector indexes
tools/
  pipeline.py         → 7-phase orchestrator (collect → filter → download → lyrics → features → process → seed)
  collect_data.py     → Phase 1: YouTube Music artist/track discovery
  filter_data.py      → Phase 2: Vietnamese-only deduplication
  download_music.py   → Phase 3: MP3 download via yt-dlp
  extract_audio_features.py → Phase 5: Essentia-TF + librosa DSP
  process_data.py     → Phase 6: PhoBERT embeddings + feature engineering
static/
  index.html, css/, js/ → Vanilla SPA frontend
```

## Key Conventions
- All API routes under `/api/` prefix
- Vietnamese text: use pyvi.ViTokenizer for word segmentation before PhoBERT
- Color: hex strings (#RRGGBB), CIEDE2000 perceptual distance via colormath
- Emotions: 13 categories mapped to Russell's Circumplex (valence × arousal)
- Mood quadrants: Q1 (happy/energetic), Q2 (angry/intense), Q3 (sad/calm), Q4 (peaceful/relaxed)
- Config values in config.py — avoid hardcoding weights/thresholds in business logic
- Singleton pattern via `get_*()` factory functions in core/ modules
- Database uses PostgreSQL-specific features (pgvector, GIN trigram indexes, HNSW)

## Data Pipeline
- 7-phase strict-gate pipeline: each phase validates output before proceeding
- YouTube Music (ytmusicapi) for track discovery and metadata
- yt-dlp for MP3 download with 5-tier search strategy
- Essentia-TF for audio features (tempo, key, energy, danceability, mood tags)
- PhoBERT for 768-dim lyrics embeddings
- Checkpoints stored in `checkpoints/` for resumable runs

## Running
```bash
# Activate virtual environment
source .venv/bin/activate

# Start dev server
uvicorn app:app --reload --port 8000

# Run data pipeline
python -m tools.pipeline

# Database migration
alembic upgrade head

# Seed database from processed CSV
python -m db.seed
```

## Important Notes
- Spotify integration is deprecated (spotipy removed from requirements). collect_data.py handles this gracefully via HAS_SPOTIPY flag.
- Audio files in `music_files/`, album art in `album_art/`, artist images in `artist_images/`
- ML models cached in `models_cache/` (Essentia-TF EffNet)
- PhoBERT and CLIP models auto-download from HuggingFace on first use
- The system is designed for Vietnamese music: emotion lexicon, transliteration, diacritics handling all tuned for Vietnamese language

## Claude Code Integration
- `CLAUDE.md` at project root — main project instructions (imports this file)
- `.claude/rules/` — path-scoped rules:
  - `ai-ml.md` — AI/ML module conventions (core/, config.py)
  - `api.md` — API development rules (api/, app.py)
  - `database.md` — PostgreSQL/SQLAlchemy rules (db/, alembic/)
  - `pipeline.md` — Data pipeline rules (tools/)
- `.claude/skills/` — available skills:
  - `run-pipeline` — Run data pipeline phases
  - `add-essentia-model` — Integrate new Essentia-TF models
  - `vietnamese-nlp` — Vietnamese NLP conventions (auto-loaded)
  - `add-api-endpoint` — Create new API routes
  - `add-migration` — Alembic database migrations
  - `debug-recommendation` — Troubleshoot recommendation engine

## Research References
- See `docs/SCIENTIFIC_RESEARCH_UPGRADE_REPORT.md` for validated research papers and upgrade opportunities
- See `docs/TECH_EVALUATION_REPORT.md` for technology evaluation (scored 8.2/10)
