"""Rename all tables: remove DW prefixes (dim_, fact_, bridge_) → plain OLTP names.

Also drops the deprecated fact_play_history table (merged into play_events).

Rename map:
  dim_artist         → artists
  dim_album          → albums
  dim_genre          → genres
  dim_mood           → moods
  dim_user           → users
  dim_song           → songs
  bridge_song_artist → song_artists
  bridge_artist_genre→ artist_genres
  song_embedding     → song_embeddings
  fact_listen        → play_events
  fact_like          → likes
  fact_follow        → follows
  fact_recommendation→ recommendations
  playlist           → playlists
  fact_playlist_song → playlist_songs
  fact_search        → search_logs
  fact_play_history  → (dropped — merged into play_events)

Revision ID: 009
Revises: 008
"""
from alembic import op


# revision identifiers
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None

# (old_name, new_name)
RENAMES = [
    ("dim_artist", "artists"),
    ("dim_album", "albums"),
    ("dim_genre", "genres"),
    ("dim_mood", "moods"),
    ("dim_user", "users"),
    ("dim_song", "songs"),
    ("bridge_song_artist", "song_artists"),
    ("bridge_artist_genre", "artist_genres"),
    ("song_embedding", "song_embeddings"),
    ("fact_listen", "play_events"),
    ("fact_like", "likes"),
    ("fact_follow", "follows"),
    ("fact_recommendation", "recommendations"),
    ("playlist", "playlists"),
    ("fact_playlist_song", "playlist_songs"),
    ("fact_search", "search_logs"),
]


def upgrade():
    # Drop deprecated fact_play_history table (merged into play_events/fact_listen)
    op.drop_table("fact_play_history")

    # Rename all tables — PostgreSQL ALTER TABLE ... RENAME TO is instant (metadata-only)
    for old, new in RENAMES:
        op.rename_table(old, new)


def downgrade():
    # Reverse renames
    for old, new in reversed(RENAMES):
        op.rename_table(new, old)

    # Re-create fact_play_history
    import sqlalchemy as sa
    op.create_table(
        "fact_play_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("dim_user.user_id"), nullable=False),
        sa.Column("song_id", sa.String(64), sa.ForeignKey("dim_song.track_id"), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("source", sa.String(32)),
    )
    op.create_index("idx_play_history", "fact_play_history", ["user_id", "played_at"])
    op.create_index(op.f("ix_fact_play_history_song_id"), "fact_play_history", ["song_id"])
    op.create_index(op.f("ix_fact_play_history_user_id"), "fact_play_history", ["user_id"])
