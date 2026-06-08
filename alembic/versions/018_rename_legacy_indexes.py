"""Rename legacy ix_dim_* indexes to ix_<table>_<column>.

Migration 009 renamed all tables (dim_song → songs, dim_artist → artists,
dim_album → albums) but SQLAlchemy's auto-generated index names kept the old
prefix. This migration renames the 8 affected indexes for consistency.

Uses ALTER INDEX … RENAME TO — instant, no table lock, no data movement.

Revision ID: 018
Revises: 017
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


# (old_name, new_name) pairs — only renamed if old name exists
_RENAMES = [
    ("ix_dim_song_track_name",          "ix_song_track_name"),
    ("ix_dim_song_album_id",            "ix_song_album_id"),
    ("ix_dim_song_primary_artist_id",   "ix_song_primary_artist_id"),
    ("ix_dim_song_popularity",          "ix_song_popularity"),
    ("ix_dim_song_has_lyrics",          "ix_song_has_lyrics"),
    ("ix_dim_artist_name",              "ix_artist_name"),
    ("ix_dim_album_name",               "ix_album_name"),
    ("ix_dim_album_release_year",       "ix_album_release_year"),
]


def _existing_indexes(bind) -> set:
    return {row[0] for row in bind.execute(
        sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    )}


def upgrade():
    bind = op.get_bind()
    existing = _existing_indexes(bind)
    for old, new in _RENAMES:
        if old in existing and new not in existing:
            op.execute(f'ALTER INDEX "{old}" RENAME TO "{new}"')


def downgrade():
    bind = op.get_bind()
    existing = _existing_indexes(bind)
    for old, new in _RENAMES:
        if new in existing and old not in existing:
            op.execute(f'ALTER INDEX "{new}" RENAME TO "{old}"')
