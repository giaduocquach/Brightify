"""Add vocal regions to songs (Smart Crossfade Tier 3 — vocal-aware mixing).

Revision ID: 019
Revises: 018
Create Date: 2026-06-14

- vocal_start_s: first vocal onset (s) — end of instrumental intro
- vocal_end_s: last vocal offset (s) — start of instrumental outro

Computed offline by tools/extract_vocal_regions.py via Demucs vocal-stem
separation + RMS-envelope thresholding. Nullable so existing rows backfill
incrementally and pure-instrumental tracks stay NULL (graceful fallback).
"""

from alembic import op
import sqlalchemy as sa

revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("songs")}
    if "vocal_start_s" not in columns:
        op.add_column(
            'songs',
            sa.Column('vocal_start_s', sa.Float(), nullable=True,
                      comment='First vocal onset (s) — end of instrumental intro')
        )
    if "vocal_end_s" not in columns:
        op.add_column(
            'songs',
            sa.Column('vocal_end_s', sa.Float(), nullable=True,
                      comment='Last vocal offset (s) — start of instrumental outro')
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("songs")}
    if "vocal_end_s" in columns:
        op.drop_column('songs', 'vocal_end_s')
    if "vocal_start_s" in columns:
        op.drop_column('songs', 'vocal_start_s')
