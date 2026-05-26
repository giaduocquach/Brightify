"""Drop user-related tables and columns.

Tables dropped:
  - users
  - play_events
  - likes
  - follows
  - playlists
  - playlist_songs

Columns dropped:
  - recommendations.user_id
  - search_logs.user_id

Revision ID: 010
Revises: 009
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    # Drop columns that reference users (must drop FK constraints first)
    # These columns may not exist if the DB was created fresh after models were updated
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Drop user_id from recommendations if it exists
    rec_cols = [c["name"] for c in inspector.get_columns("recommendations")]
    if "user_id" in rec_cols:
        # Drop FK constraint first
        rec_fks = inspector.get_foreign_keys("recommendations")
        for fk in rec_fks:
            if "user_id" in fk["constrained_columns"]:
                op.drop_constraint(fk["name"], "recommendations", type_="foreignkey")
        op.drop_column("recommendations", "user_id")

    # Drop user_id from search_logs if it exists
    sl_cols = [c["name"] for c in inspector.get_columns("search_logs")]
    if "user_id" in sl_cols:
        sl_fks = inspector.get_foreign_keys("search_logs")
        for fk in sl_fks:
            if "user_id" in fk["constrained_columns"]:
                op.drop_constraint(fk["name"], "search_logs", type_="foreignkey")
        op.drop_column("search_logs", "user_id")

    # Drop user-related tables (order matters due to FK dependencies)
    tables_to_drop = [
        "playlist_songs",
        "playlists",
        "follows",
        "likes",
        "play_events",
        "users",
    ]
    existing_tables = inspector.get_table_names()
    for table in tables_to_drop:
        if table in existing_tables:
            op.drop_table(table)


def downgrade():
    # Recreate user-related tables
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(30), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(50)),
        sa.Column("avatar_emoji", sa.String(8), server_default="🎵"),
        sa.Column("bio", sa.String(200)),
        sa.Column("is_admin", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "play_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("track_id", sa.String(64), sa.ForeignKey("songs.track_id"), nullable=False),
        sa.Column("source", sa.String(32)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("completed", sa.Boolean, server_default="false"),
        sa.Column("played_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "likes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("track_id", sa.String(64), sa.ForeignKey("songs.track_id"), nullable=False),
        sa.Column("liked_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "follows",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("artist_name", sa.String(255), nullable=False),
        sa.Column("followed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "playlists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("song_ids", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "playlist_songs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("playlist_id", sa.String(36), sa.ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_id", sa.String(64), sa.ForeignKey("songs.track_id"), nullable=False),
        sa.Column("position", sa.SmallInteger),
        sa.Column("added_at", sa.DateTime(timezone=True)),
    )

    # Re-add user_id columns
    op.add_column("recommendations", sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id")))
    op.add_column("search_logs", sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id")))
