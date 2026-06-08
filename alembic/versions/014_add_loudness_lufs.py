"""Add loudness_lufs (ITU-R BS.1770 integrated LUFS) to songs.

Revision ID: 014
Revises: 013
Create Date: 2026-05-29

Used by Smart Crossfade Phase 2 to pre-normalize playback volume to -14 LUFS
(Spotify standard). Computed offline by tools/extract_audio_features.py via
pyloudnorm. Nullable so existing rows backfill incrementally.
"""

from alembic import op
import sqlalchemy as sa

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("songs")}
    if "loudness_lufs" not in columns:
        op.add_column(
            'songs',
            sa.Column('loudness_lufs', sa.Float(), nullable=True,
                      comment='Integrated loudness in LUFS (ITU-R BS.1770)')
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("songs")}
    if "loudness_lufs" in columns:
        op.drop_column('songs', 'loudness_lufs')
