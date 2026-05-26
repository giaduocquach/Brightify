# Brightify — AI Music Streaming Platform

@.github/copilot-instructions.md

## Build & Run

```bash
source .venv/bin/activate
uvicorn app:app --reload --port 8000
```

## Test

```bash
python -m pytest test/
```

## Database

```bash
alembic upgrade head    # Run migrations
python -m db.seed       # Seed from CSV
```

## Data Pipeline

```bash
python -m tools.pipeline    # Full 7-phase pipeline
```

## Key Rules

- All config values in `config.py` — never hardcode weights/thresholds in business logic
- Vietnamese text must be word-segmented with pyvi ViTokenizer before PhoBERT tokenization
- Color values are hex strings (#RRGGBB), use CIEDE2000 for perceptual distance
- Emotions use 13 categories mapped to Russell's Circumplex (valence × arousal)
- Mood quadrants: Q1 (happy/energetic), Q2 (angry/intense), Q3 (sad/calm), Q4 (peaceful/relaxed)
- API routes always under `/api/` prefix
- Use `get_*()` singleton factory functions for core module instances
- Database uses PostgreSQL-specific features: pgvector, GIN trigram, HNSW indexes
- PhoBERT embeddings are 768-dimensional — all vector operations must match this dimension
- Admin key comparison must use `hmac.compare_digest()` (timing-safe)
- PIL image processing must set `MAX_IMAGE_PIXELS` for decompression bomb protection
