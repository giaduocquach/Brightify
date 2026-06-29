"""Add muq_embedding Vector(1024) to song_embeddings — dominant similar-song signal.

Revision ID: 021
Revises: 020
Create Date: 2026-06-29

MuQ (Zhu et al. 2025, arXiv 2501.01108) — 1024-dim self-supervised music
embeddings, the audio backbone that dominates similar-song fusion (weight 0.76,
``data/muq_embeddings.npy``). Stored in pgvector with an HNSW cosine index so
the similar-song candidate stage can run as an ANN query in the database
(two-stage retrieve-then-rerank), in addition to the in-memory hot path.
"""

from alembic import op

revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE song_embeddings ADD COLUMN IF NOT EXISTS muq_embedding vector(1024)")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_song_embeddings_muq_hnsw
        ON song_embeddings
        USING hnsw (muq_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_song_embeddings_muq_hnsw")
    op.execute("ALTER TABLE song_embeddings DROP COLUMN IF EXISTS muq_embedding")
