# Brightify — Vietnamese Music Recommendation System

> AI-powered Vietnamese music streaming platform combining audio analysis, lyrics NLP, and color psychology into a multimodal recommendation engine.

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.108+-green.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-blue.svg)](https://www.postgresql.org)
[![pgvector](https://img.shields.io/badge/pgvector-0.4+-orange.svg)](https://github.com/pgvector/pgvector)

---

## Overview

**Brightify** serves **5,138 Vietnamese songs** through a content-based engine with **two core features**, both unified on a shared **Valence–Arousal (V-A)** emotion space (Russell's circumplex):

- **Recommend by colour** — a colour maps to a V-A point (Oklab → ICEAS valence + Whiteford arousal); the engine retrieves songs near that mood (anisotropic Gaussian RBF in quantile space) and tightens acoustic coherence on MuQ. Two colours → an iso-principle mood journey.
- **Similar song** — fusion `0.76·MuQ audio + 0.16·V-A + 0.08·lyrics (e5-large)`, with cover-song dedup and artist diversification (endless "radio").

Each song gets one offline-computed `(valence, arousal)`: **valence** from lyrics (reliability-weighted **EWE** of NRC-VAD-VN, ViSoBERT, XLM-R/EmoBank + a small MuQ term), **arousal** from audio (MuQ + tempo + loudness, DEAM-grounded). All models are **frozen + linear probes — no fine-tuning, and no LLM/model inference at serving** (labels are a precomputed lookup). Query inputs: **colour**, **song-to-song**, **search**, **browse**.

## Architecture

```
Frontend SPA (React 19 + Vite — react-three-fiber 3D + classic 2D skins, Web Audio)
        ↓ REST API
FastAPI 0.108+ (lifespan, CORS, rate limiting)
        ↓
Core AI/ML layer
  ├─ recommendation_engine.py — colour + similar-song over precomputed features
  ├─ ranking/ — retrieval, artist diversity (MMR), acoustic coherence, iso-principle journey
  ├─ emotion_analysis.py / color_va.py — V-A labels + colour→V-A mapping
  └─ advanced_color_mapping.py — Oklab + ICEAS (valence) + Whiteford (arousal)
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
| Lyrics / NLP | multilingual-e5-large (similarity); ViSoBERT + XLM-R + NRC-VAD-VN (valence signals) |
| Audio ML | MuQ self-supervised embeddings (backbone), librosa (tempo), DEAM/PMEmo (probe training) |
| Color | Oklab perceptual space + ICEAS norms + Whiteford arousal |
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
├── api/                      # HTTP API layer (~25 routes)
│   ├── music.py              # Browse/search/stream/similar-song
│   ├── recommend.py          # Colour recommendation (+ why/bridge)
│   ├── system.py             # Health, stats, backtest
│   └── rate_limit.py         # Sliding-window rate limiter
├── core/                     # AI/ML core modules
│   ├── recommendation_engine.py   # colour + similar-song
│   ├── ranking/                    # retrieval, diversity, coherence, journey
│   ├── emotion_analysis.py / color_va.py
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
| Emotion psychology | Russell 1980 (Circumplex), Thayer 1989 |
| Audio representation | Zhu et al. 2025 (MuQ self-supervised), Aljanaki et al. 2017 (DEAM), Zhang et al. 2018 (PMEmo) |
| Lyrics / VN NLP | Wang et al. 2024 (multilingual-e5), Nguyen et al. 2023 (ViSoBERT), Mohammad 2018 (NRC-VAD), Buechel & Hahn 2017 (EmoBank) |
| Colour ↔ emotion | Jonauskaite et al. 2020 (ICEAS, 4,598 participants), Whiteford et al. 2018 (colour↔music), Ottosson 2020 (Oklab) |
| Recsys evaluation | Ferrari Dacrema 2019 (strong baselines), Steck 2018 (calibrated recommendation) |
| Music therapy | Altshuler 1948 (Iso-Principle) |

Full citations in [docs/RESEARCH_FOUNDATIONS.md](docs/RESEARCH_FOUNDATIONS.md).

## Status

- **Catalog**: 5,138 Vietnamese songs (audio + lyrics + precomputed features)
- **Audio backbone**: MuQ · **Lyrics**: multilingual-e5-large · **Emotion labels**: v6i (frozen, reproducible via `tools/build_labels_repro.py`)
- **Core features**: recommend-by-colour (Valence–Arousal) + similar-song; two UI skins (3D immersive + classic 2D)
- **Thesis (ĐATN)**: see `SOICT_DATN_Application_VIE_Template/` — report + verifiable offline evaluation

## License

Đồ án tốt nghiệp — mã nguồn phục vụ **mục đích học thuật / nghiên cứu**, *all rights reserved*: vui lòng xin phép trước khi tái sử dụng. Dữ liệu **nhạc và lời bài hát thuộc bản quyền của bên thứ ba**, không kèm trong repo (đã loại trừ qua `.gitignore`) và không được phân phối lại; các mô hình và tập dữ liệu ngoài (MuQ, multilingual-e5-large, ViSoBERT, XLM-R, NRC-VAD, DEAM, PMEmo, EmoBank…) giữ nguyên giấy phép gốc của chúng.

## Acknowledgments

- OpenMuQ (MuQ audio model), intfloat (multilingual-e5), uitnlp (ViSoBERT)
- DEAM, PMEmo, EmoBank, NRC-VAD, VnEmoLex (datasets / lexicons)
- MTG-UPF (Essentia, MTG-Jamendo), LRCLIB (lyrics)
- ytmusicapi & yt-dlp contributors

---

**Built for the Vietnamese music community.** 🎵
