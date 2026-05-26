---
name: add-migration
description: Create and run an Alembic database migration for PostgreSQL schema changes. Use when adding columns, tables, or indexes.
disable-model-invocation: true
---

# Database Migration

## Create Migration

```bash
cd /Users/admin/Projects/Brightify
source .venv/bin/activate
alembic revision -m "$ARGUMENTS"
```

## Naming Convention
Files are numbered sequentially: `001_`, `002_`, etc. Check existing files in `alembic/versions/` and use the next number.

## Migration Template
```python
"""$ARGUMENTS"""
from alembic import op
import sqlalchemy as sa

revision = '<auto>'
down_revision = '<previous>'

def upgrade():
    # Add columns, tables, indexes
    op.add_column('dim_songs', sa.Column('new_feature', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('dim_songs', 'new_feature')
```

## PostgreSQL-Specific Features
- pgvector: `sa.Column('embedding', Vector(768))` (import from pgvector.sqlalchemy)
- GIN trigram: `op.create_index('ix_gin_name', 'dim_songs', ['name'], postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'})`
- HNSW vector: index created in `db/seed.py` after data load

## Run Migration
```bash
alembic upgrade head    # Apply all pending
alembic downgrade -1    # Rollback last
alembic history         # Show migration history
```

## Update ORM
After creating migration, update the SQLAlchemy model in `db/models.py` to match.
