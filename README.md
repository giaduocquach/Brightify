# Brightify — Vietnamese Music Recommendation System

> AI-powered Vietnamese music streaming platform combining audio analysis, lyrics NLP, color psychology, and image understanding into a multimodal recommendation engine.

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.108+-green.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-blue.svg)](https://www.postgresql.org)
[![pgvector](https://img.shields.io/badge/pgvector-0.4+-orange.svg)](https://github.com/pgvector/pgvector)

---

## Overview

**Brightify** serves ~4,300+ Vietnamese songs through a content-based recommendation engine that fuses **7 multimodal signals**:

1. **Timbral** — Essentia EffNet-Discogs spectral features
2. **Rhythmic** — Tempo, danceability, liveness
3. **Tonal** — Valence, key, mode
4. **Lyrics semantic** — PhoBERT v2 (768-dim Vietnamese embeddings)
5. **V-A proximity** — Russell's Circumplex Model (valence × arousal)
6. **Emotion profile** — Vietnamese Emotion Lexicon (730+ words, 13 categories)
7. **Mood matching** — Q1-Q4 quadrant alignment

Plus multimodal query inputs: **color** (CIEDE2000, Jonauskaite 2020), **image** (CLIP ViT-B/32 zero-shot), **mood**, **lyrics keywords**, **song-to-song**.

## Architecture

```
Frontend SPA (Vanilla JS + Canvas + Web Audio)
        ↓ REST API
FastAPI 0.108+ (lifespan, CORS, rate limiting)
        ↓
Core AI/ML layer
  ├─ recommendation_engine.py — 7-signal multimodal fusion
  ├─ emotion_analysis.py — PhoBERT + Vietnamese lexicon
  ├─ advanced_color_mapping.py — CIEDE2000 + 13 emotion-color profiles
  └─ image_analysis.py — CLIP zero-shot (10 emotions, 18 scenes)
        ↓
File-based serving release (`data/*.csv/*.npy/*.json` + `music_files/*.mp3`)
        ↓
PostgreSQL 17 + pgvector (crossfade side-data, seed mirror, health)
        ↓
Data pipeline (7-phase strict-gate, resumable)
  collect → filter → download → lyrics → extract → process → seed
```

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.108+, Uvicorn, Python 3.10+ |
| Database | PostgreSQL 17, SQLAlchemy 2.0, Alembic, pgvector 0.4+, pg_trgm |
| NLP (Vietnamese) | PhoBERT v2 (vinai/phobert-base-v2), pyvi ViTokenizer |
| Audio ML | Essentia-TensorFlow (EffNet-Discogs, DEAM, MSD-MusiCNN, TempoCNN), librosa |
| Vision | CLIP ViT-B/32 (openai/clip-vit-base-patch32) |
| Color | CIEDE2000 (colormath) |
| Frontend | Vanilla HTML/CSS/JS SPA, Web Audio API, Canvas visualizer |
| Pipeline | ytmusicapi, yt-dlp, FFmpeg |

## Quick start

### Prerequisites

- Python 3.10+
- PostgreSQL 17 với extension `pgvector` và `pg_trgm`
- FFmpeg (cho yt-dlp pipeline)
- ~25 GB disk space (10-20 GB MP3 + models + DB)

### Local development

```bash
# 1. Clone
git clone https://github.com/<your-username>/vietnamese-music-recsys.git
cd vietnamese-music-recsys

# 2. Setup Python env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Setup environment
cp .env.example .env
# Edit .env: DATABASE_URL, BRIGHTIFY_ADMIN_KEY, ...

# 4. Init database
alembic upgrade head
python -m db.seed       # Seed từ data/vietnamese_music_processed_full.csv

# 5. Start dev server
uvicorn app:app --reload --port 8000
```

Truy cập `http://localhost:8000` cho frontend, `http://localhost:8000/docs` cho Swagger API.

### Docker (recommended) — sau khi hoàn thành Plan 3

```bash
make init       # Tạo var/ structure + secrets
make dev        # docker compose up với hot reload
```

Xem [docs/PLAN_DOCKERIZATION.md](docs/PLAN_DOCKERIZATION.md) cho chi tiết.

## Project structure

```
brightify/
├── app.py                    # FastAPI entry point
├── config.py                  # Centralized config (weights, thresholds)
├── api/                      # HTTP API layer (41 endpoints)
│   ├── music.py              # Browse/search/stream (26 routes)
│   ├── recommend.py          # AI recommendations (6 routes)
│   ├── system.py             # Health, stats, backtest (9 routes)
│   └── rate_limit.py         # Sliding-window rate limiter
├── core/                     # AI/ML core modules
│   ├── recommendation_engine.py
│   ├── emotion_analysis.py
│   ├── advanced_color_mapping.py
│   └── image_analysis.py
├── db/                       # Database layer
│   ├── models.py             # SQLAlchemy ORM (star schema, 10 tables)
│   ├── engine.py
│   └── seed.py
├── alembic/                  # Database migrations (011 migrations)
├── tools/                    # 7-phase data pipeline
├── static/                   # Frontend SPA
├── test/                     # Tests (~5,700 lines)
└── docs/                     # 18+ comprehensive reports
    ├── PROJECT_OVERVIEW.md
    ├── DETAILED_PROJECT_ANALYSIS.md
    ├── PLAN_SYSTEM_UPGRADE.md
    ├── PLAN_BACKTEST_METRICS.md
    └── PLAN_DOCKERIZATION.md
```

## Documentation

- **[docs/DETAILED_PROJECT_ANALYSIS.md](docs/DETAILED_PROJECT_ANALYSIS.md)** — Comprehensive system analysis (14 sections, 1800+ lines)
- **[docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)** — High-level architecture overview
- **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** — Endpoint documentation
- **[docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md)** — DB schema + ERD
- **[docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md)** — Pipeline phases
- **[docs/PLAN_PRODUCTION_DATA_ARCHITECTURE_V24.md](docs/PLAN_PRODUCTION_DATA_ARCHITECTURE_V24.md)** — Production data layout, DB scope, keep/drop plan
- **[docs/RESEARCH_FOUNDATIONS.md](docs/RESEARCH_FOUNDATIONS.md)** — Academic references (20+ papers)
- **[docs/AI_FEATURE_EVALUATION.md](docs/AI_FEATURE_EVALUATION.md)** — AI engine evaluation
- **[docs/MARKET_ANALYSIS_REPORT.md](docs/MARKET_ANALYSIS_REPORT.md)** — Competitor analysis
- **[docs/PLAN_SYSTEM_UPGRADE.md](docs/PLAN_SYSTEM_UPGRADE.md)** — v8.0 upgrade plan (MERT, ViDeBERTa, hybrid retrieval, ...)
- **[docs/PLAN_BACKTEST_METRICS.md](docs/PLAN_BACKTEST_METRICS.md)** — Backtest framework + evaluation metrics
- **[docs/PLAN_DOCKERIZATION.md](docs/PLAN_DOCKERIZATION.md)** — Docker deployment (master data layout)

## Research foundations

Brightify is built on validated academic research:

| Domain | Paper / Reference |
|---|---|
| Emotion psychology | Russell 1980 (Circumplex), Thayer 1989, Ekman 1992 |
| Vietnamese NLP | Nguyen & Tuan Nguyen 2020 (PhoBERT), Huynh et al. 2019 (UIT-VSMEC) |
| Music IR | Berenzweig 2004 (Timbral), Hu & Downie 2010 (Lyrics > Audio for mood), Laurier 2009 (multimodal fusion) |
| Color psychology | Palmer et al. 2013, Jonauskaite et al. 2020 (cross-cultural, 4,598 participants, 12 countries) |
| Vision | Radford et al. 2021 (CLIP) |
| Audio ML | Alonso-Jiménez et al. 2023 (DEAM V-A regression), MTG Essentia models |
| Music therapy | Altshuler 1948 (Iso-Principle), Heiderscheit & Madson 2015 |

Full citations in [docs/RESEARCH_FOUNDATIONS.md](docs/RESEARCH_FOUNDATIONS.md).

## Status

- **Current version**: v7.1 (codebase) / v7.2 (after PhoBERT v2 + DEAM upgrade)
- **Catalog size**: ~4,300+ Vietnamese songs
- **In progress**: v8.0 upgrade plan (xem [PLAN_SYSTEM_UPGRADE.md](docs/PLAN_SYSTEM_UPGRADE.md))

## License

TBD — Academic / research use.

## Acknowledgments

- VinAI Research (PhoBERT, BARTpho)
- MTG-UPF (Essentia, MTG-Jamendo dataset)
- OpenAI (CLIP)
- LAION (CLAP)
- LRCLIB (lyrics database)
- ytmusicapi & yt-dlp contributors

---

**Built for the Vietnamese music community.** 🎵
