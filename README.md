# Brightify — Vietnamese Music Recommendation System

> AI-powered Vietnamese music streaming platform combining audio analysis, lyrics NLP, and color psychology into a multimodal recommendation engine.

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

Plus multimodal query inputs: **color** (CIEDE2000, Jonauskaite 2020), **mood**, **search**, **song-to-song**.

## Architecture

```
Frontend SPA (React 19 + Vite — react-three-fiber 3D + classic 2D skins, Web Audio)
        ↓ REST API
FastAPI 0.108+ (lifespan, CORS, rate limiting)
        ↓
Core AI/ML layer
  ├─ recommendation_engine.py — multimodal fusion (color + similar-song)
  ├─ emotion_analysis.py — Vietnamese emotion lexicon + V-A
  └─ advanced_color_mapping.py — CIEDE2000 + 13 emotion-color profiles
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
| Color | CIEDE2000 (colormath) |
| Frontend | React 19 + Vite SPA (react-three-fiber 3D + classic 2D skins), Web Audio API |
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
│   └── advanced_color_mapping.py
├── db/                       # Database layer
│   ├── models.py             # SQLAlchemy ORM (star schema, 10 tables)
│   ├── engine.py
│   └── seed.py
├── alembic/                  # Database migrations
├── tools/                    # 7-phase data pipeline
├── frontend/                 # React 19 + Vite SPA (builds → static_spa/)
├── static_spa/               # Built SPA served by FastAPI
├── test/                     # Tests
└── docs/                     # Reports (historical plans under docs/archive/)
    ├── PROJECT_OVERVIEW.md
    ├── SCIENTIFIC_AUDIT_AND_PLAN_V32.md
    └── PLAN_DOCKERIZATION.md
```

## Documentation

- **[docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)** — High-level architecture overview
- **[docs/SCIENTIFIC_AUDIT_AND_PLAN_V32.md](docs/SCIENTIFIC_AUDIT_AND_PLAN_V32.md)** — Comprehensive system audit + upgrade plan
- **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** — Endpoint documentation
- **[docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md)** — DB schema + ERD
- **[docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md)** — Pipeline phases
- **[docs/PIPELINE_DIAGRAMS.md](docs/PIPELINE_DIAGRAMS.md)** — Serving-state diagrams (V36–V39)
- **[docs/PLAN_PRODUCTION_DATA_ARCHITECTURE_V24.md](docs/PLAN_PRODUCTION_DATA_ARCHITECTURE_V24.md)** — Production data layout, DB scope, keep/drop plan
- **[docs/RESEARCH_FOUNDATIONS.md](docs/RESEARCH_FOUNDATIONS.md)** — Academic references (20+ papers)
- **[docs/COLOR_FEATURE_SCIENTIFIC_BASIS_V39.md](docs/COLOR_FEATURE_SCIENTIFIC_BASIS_V39.md)** — Recommend-by-color scientific basis (current)
- **[docs/MARKET_ANALYSIS_REPORT.md](docs/MARKET_ANALYSIS_REPORT.md)** — Competitor analysis
- **[docs/PLAN_DOCKERIZATION.md](docs/PLAN_DOCKERIZATION.md)** — Docker deployment (master data layout)
- _Historical planning/research docs are archived under `docs/archive/`._

## Research foundations

Brightify is built on validated academic research:

| Domain | Paper / Reference |
|---|---|
| Emotion psychology | Russell 1980 (Circumplex), Thayer 1989, Ekman 1992 |
| Vietnamese NLP | Nguyen & Tuan Nguyen 2020 (PhoBERT), Huynh et al. 2019 (UIT-VSMEC) |
| Music IR | Berenzweig 2004 (Timbral), Hu & Downie 2010 (Lyrics > Audio for mood), Laurier 2009 (multimodal fusion) |
| Color psychology | Palmer et al. 2013, Jonauskaite et al. 2020 (cross-cultural, 4,598 participants, 12 countries) |
| Audio ML | Alonso-Jiménez et al. 2023 (DEAM V-A regression), MTG Essentia models |
| Music therapy | Altshuler 1948 (Iso-Principle), Heiderscheit & Madson 2015 |

Full citations in [docs/RESEARCH_FOUNDATIONS.md](docs/RESEARCH_FOUNDATIONS.md).

## Status

- **Current version**: v7.1 (codebase) / v7.2 (after PhoBERT v2 + DEAM upgrade)
- **Catalog size**: ~4,300+ Vietnamese songs
- **In progress**: xem [docs/SCIENTIFIC_AUDIT_AND_PLAN_V32.md](docs/SCIENTIFIC_AUDIT_AND_PLAN_V32.md)

## License

TBD — Academic / research use.

## Acknowledgments

- VinAI Research (PhoBERT, BARTpho)
- MTG-UPF (Essentia, MTG-Jamendo dataset)
- LRCLIB (lyrics database)
- ytmusicapi & yt-dlp contributors

---

**Built for the Vietnamese music community.** 🎵
