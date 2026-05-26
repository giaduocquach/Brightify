---
paths:
  - "db/**/*.py"
  - "alembic/**/*.py"
---

# Database Rules

## PostgreSQL-Specific
- pgvector for 768-dim embeddings with HNSW indexing
- pg_trgm GIN indexes for fuzzy Vietnamese text search
- Star schema: Song (fact) → Artist, Album (dimensions)

## SQLAlchemy
- Sync engine (not async) — SQLAlchemy 2.0 style
- Pool: pool_size=10, max_overflow=20, pool_pre_ping=True
- All models in `db/models.py`

## Migrations
- Alembic for schema migrations in `alembic/versions/`
- Sequential numbering: 001_, 002_, etc.
- Always test migration up and down

## Data Pipeline Integration
- `db/seed.py` handles CSV→PostgreSQL ETL
- Embeddings stored as pgvector `Vector(768)` columns
- Vietnamese text columns need GIN trigram indexes for search
