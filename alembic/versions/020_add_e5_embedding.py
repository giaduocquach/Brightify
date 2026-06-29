"""Add e5_embedding Vector(1024) to song_embeddings — active lyrics embedding.

Revision ID: 020
Revises: 019
Create Date: 2026-06-28

multilingual-e5-large (Wang et al. 2024, arXiv 2402.05672) — 1024-dim lyrics
embeddings, the embedding actually used at serving (``data/lyrics_e5large.npy``).
Stored alongside the legacy 768-dim ``embedding`` column; HNSW cosine index for
pgvector-backed similar-song candidate retrieval.
"""

from alembic import op

revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE song_embeddings ADD COLUMN IF NOT EXISTS e5_embedding vector(1024)")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_song_embeddings_e5_hnsw
        ON song_embeddings
        USING hnsw (e5_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_song_embeddings_e5_hnsw")
    op.execute("ALTER TABLE song_embeddings DROP COLUMN IF EXISTS e5_embedding")
