"""Drop unused legacy DB schema not used by the current runtime.

Revision ID: 016
Revises: 015
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa


revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


SONG_COLUMNS_TO_DROP = [
    "isrc",
    "track_number",
    "disc_number",
    "preview_url",
    "available_markets_count",
    "mp3_path",
    "mp3_source",
    "mp3_duration_s",
    "mp3_quality",
    "youtube_music_id",
    "youtube_id",
    "ytmusic_video_id",
    "audio_feature_source",
    "valence_estimated",
    "ytmusic_thumbnail_url",
    "lyrics_source",
    "genre_tags",
    "audio_fingerprint",
    "thumbnail_url",
]


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _song_columns(inspector) -> set[str]:
    if not _table_exists(inspector, "songs"):
        return set()
    return {col["name"] for col in inspector.get_columns("songs")}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "songs"):
        columns = _song_columns(inspector)
        for column_name in SONG_COLUMNS_TO_DROP:
            if column_name in columns:
                op.drop_column("songs", column_name)

    for table_name in ("recommendations", "search_logs", "artist_genres", "genres"):
        if _table_exists(inspector, table_name):
            op.drop_table(table_name)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "genres"):
        op.create_table(
            "genres",
            sa.Column("genre_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=128), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_genres_name", "genres", ["name"], unique=False)

    if not _table_exists(inspector, "artist_genres"):
        op.create_table(
            "artist_genres",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("artist_id", sa.String(length=64), sa.ForeignKey("artists.artist_id"), nullable=False),
            sa.Column("genre_id", sa.Integer(), sa.ForeignKey("genres.genre_id"), nullable=False),
        )
        op.create_unique_constraint("uq_artist_genre", "artist_genres", ["artist_id", "genre_id"])
        op.create_index("ix_artist_genres_artist_id", "artist_genres", ["artist_id"], unique=False)
        op.create_index("ix_artist_genres_genre_id", "artist_genres", ["genre_id"], unique=False)

    if not _table_exists(inspector, "recommendations"):
        op.create_table(
            "recommendations",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("track_id", sa.String(length=64), sa.ForeignKey("songs.track_id"), nullable=False),
            sa.Column("rec_type", sa.String(length=32), nullable=False),
            sa.Column("similarity_score", sa.Float()),
            sa.Column("rank_position", sa.SmallInteger()),
            sa.Column("query_params", sa.JSON()),
            sa.Column("was_played", sa.Boolean(), default=False),
            sa.Column("was_liked", sa.Boolean(), default=False),
            sa.Column("recommended_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_recommendations_track_id", "recommendations", ["track_id"], unique=False)
        op.create_index("ix_recommendations_recommended_at", "recommendations", ["recommended_at"], unique=False)

    if not _table_exists(inspector, "search_logs"):
        op.create_table(
            "search_logs",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("query", sa.String(length=512), nullable=False),
            sa.Column("result_count", sa.Integer()),
            sa.Column("searched_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_search_logs_searched_at", "search_logs", ["searched_at"], unique=False)

    columns = _song_columns(sa.inspect(bind))
    song_column_defs = {
        "isrc": sa.Column("isrc", sa.String(length=16)),
        "track_number": sa.Column("track_number", sa.SmallInteger()),
        "disc_number": sa.Column("disc_number", sa.SmallInteger()),
        "preview_url": sa.Column("preview_url", sa.Text()),
        "available_markets_count": sa.Column("available_markets_count", sa.SmallInteger()),
        "mp3_path": sa.Column("mp3_path", sa.Text()),
        "mp3_source": sa.Column("mp3_source", sa.String(length=32)),
        "mp3_duration_s": sa.Column("mp3_duration_s", sa.Integer()),
        "mp3_quality": sa.Column("mp3_quality", sa.String(length=16)),
        "youtube_music_id": sa.Column("youtube_music_id", sa.String(length=32)),
        "youtube_id": sa.Column("youtube_id", sa.String(length=32)),
        "ytmusic_video_id": sa.Column("ytmusic_video_id", sa.String(length=64)),
        "audio_feature_source": sa.Column("audio_feature_source", sa.String(length=32)),
        "valence_estimated": sa.Column("valence_estimated", sa.Float()),
        "ytmusic_thumbnail_url": sa.Column("ytmusic_thumbnail_url", sa.Text()),
        "lyrics_source": sa.Column("lyrics_source", sa.String(length=32)),
        "genre_tags": sa.Column("genre_tags", sa.JSON()),
        "audio_fingerprint": sa.Column("audio_fingerprint", sa.Text()),
        "thumbnail_url": sa.Column("thumbnail_url", sa.Text()),
    }
    for column_name, column in song_column_defs.items():
        if column_name not in columns:
            op.add_column("songs", column)
