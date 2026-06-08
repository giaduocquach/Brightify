"""Add videberta_embedding column to song_embeddings table (Pillar B).

Revision ID: 012
Revises: 011

Optional column — the app reads embeddings from .npy files; this column
is for future DB-native vector search once Pillar B embeddings are stable.
"""

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("song_embeddings")}
    if "videberta_embedding" not in columns:
        op.add_column(
            'song_embeddings',
            sa.Column(
                'videberta_embedding',
                pgvector.sqlalchemy.vector.VECTOR(dim=768),
                nullable=True,
                comment='ViDeBERTa/ViSoBERT 768-dim lyrics embedding (Pillar B)',
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_song_embeddings_videberta_hnsw "
        "ON song_embeddings USING hnsw (videberta_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_song_embeddings_videberta_hnsw")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("song_embeddings")}
    if "videberta_embedding" in columns:
        op.drop_column('song_embeddings', 'videberta_embedding')
