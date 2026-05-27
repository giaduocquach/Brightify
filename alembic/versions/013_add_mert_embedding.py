"""Add mert_embedding Vector(768) to song_embeddings table.

Revision ID: 013
Revises: 012
Create Date: 2026-05-27

MERT-v1-95M (Li et al. 2023, arXiv 2306.00107) — 768-dim audio embeddings.
HNSW index for fast ANN search (same as phobert / videberta columns).
"""

from alembic import op
import sqlalchemy as sa

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE song_embeddings
        ADD COLUMN IF NOT EXISTS mert_embedding vector(768)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_song_embeddings_mert_hnsw
        ON song_embeddings
        USING hnsw (mert_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_song_embeddings_mert_hnsw")
    op.execute("ALTER TABLE song_embeddings DROP COLUMN IF EXISTS mert_embedding")
