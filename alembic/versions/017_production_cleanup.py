"""Production cleanup: drop dead columns, backfill + enforce NOT NULL on critical
columns, add has_mp3 partial index.

Dead columns dropped:
  color_hue, color_saturation, color_lightness   — HSL intermediates; only color_hex used
  mood_tags, instrument_tags                     — degenerate Essentia tags (weight=0)
  voice_gender, voice_gender_confidence          — never read by engine or API
  lrclib_id                                      — historical reference, never queried
  mood_score, dance_score, acoustic_score        — intermediate scalars, only mood_quadrant used
  combined_positivity                            — derived from valence+sentiment, never queried
  energy_level, tempo_category                   — string categories, never queried
  has_audio_features                             — redundant flag (seed rejects songs without features)

NOT NULL enforced (with backfill):
  color_hex      — backfill '#6366f1' (indigo neutral) if NULL
  arousal        — backfill from energy column if NULL (same 0-1 scale, reasonable proxy)
  mood_quadrant  — re-derive from valence + coalesced arousal if NULL or 'Unknown'

New index:
  ix_song_has_mp3 (partial) — speeds up has_mp3=TRUE filtering for streaming endpoint

Revision ID: 017
Revises: 016
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


_DEAD_COLUMNS = [
    "color_hue",
    "color_saturation",
    "color_lightness",
    "mood_tags",
    "instrument_tags",
    "voice_gender",
    "voice_gender_confidence",
    "lrclib_id",
    "mood_score",
    "dance_score",
    "acoustic_score",
    "combined_positivity",
    "energy_level",
    "tempo_category",
    "has_audio_features",
]


def _existing_columns(bind, table: str = "songs") -> set:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind)

    # ── 1. Backfill critical columns before adding NOT NULL ──────────────────

    # color_hex: neutral indigo for any row that somehow slipped through without one
    if "color_hex" in cols:
        op.execute("UPDATE songs SET color_hex = '#6366f1' WHERE color_hex IS NULL")

    # arousal: fall back to energy (same 0-1 scale) when DEAM extraction was skipped
    if "arousal" in cols and "energy" in cols:
        op.execute(
            "UPDATE songs SET arousal = COALESCE(energy, 0.5) WHERE arousal IS NULL"
        )

    # mood_quadrant: re-derive from valence × coalesced_arousal; 'Unknown' is also fixed
    if "mood_quadrant" in cols:
        coalesced_a = "COALESCE(arousal, energy, 0.5)"
        op.execute(
            f"""
            UPDATE songs
            SET mood_quadrant = CASE
                WHEN valence >= 0.5 AND {coalesced_a} >= 0.5 THEN 'Q1: Happy/Excited'
                WHEN valence <  0.5 AND {coalesced_a} >= 0.5 THEN 'Q2: Angry/Tense'
                WHEN valence <  0.5 AND {coalesced_a} <  0.5 THEN 'Q3: Sad/Depressed'
                ELSE 'Q4: Calm/Peaceful'
            END
            WHERE mood_quadrant IS NULL OR mood_quadrant = 'Unknown'
            """
        )

    # ── 2. Enforce NOT NULL on critical columns ──────────────────────────────

    if "color_hex" in cols:
        op.alter_column("songs", "color_hex", nullable=False)
    if "arousal" in cols:
        op.alter_column("songs", "arousal", nullable=False)
    if "mood_quadrant" in cols:
        op.alter_column("songs", "mood_quadrant", nullable=False)

    # ── 3. Drop dead columns ─────────────────────────────────────────────────

    for col in _DEAD_COLUMNS:
        if col in cols:
            op.drop_column("songs", col)

    # ── 4. Partial index: songs that have a local MP3 file ───────────────────

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_song_has_mp3 "
        "ON songs (has_mp3) WHERE has_mp3 = TRUE"
    )

    # ── 5. song_embeddings: drop Pillar-B/MERT experiment columns (all NULL) ─
    # videberta_embedding added in 012 (Pillar B — disabled, never populated)
    # mert_embedding added in 013 (superseded by numpy files, never populated)
    emb_cols = _existing_columns(bind, "song_embeddings")
    for col in ("videberta_embedding", "mert_embedding"):
        if col in emb_cols:
            # Drop the associated HNSW index first (CASCADE not always reliable)
            ix_map = {
                "videberta_embedding": "ix_song_embeddings_videberta_hnsw",
                "mert_embedding": "ix_song_embeddings_mert_hnsw",
            }
            op.execute(f"DROP INDEX IF EXISTS {ix_map[col]}")
            op.drop_column("song_embeddings", col)


def downgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind)

    # Remove partial index
    op.execute("DROP INDEX IF EXISTS ix_song_has_mp3")

    # Restore NOT NULL to nullable (data loss in edge cases is acceptable)
    for col_name in ("mood_quadrant", "arousal", "color_hex"):
        if col_name in cols:
            op.alter_column("songs", col_name, nullable=True)

    # Re-add dead columns as nullable (data is gone — downgrade is schema-only)
    restore = {
        "color_hue":              sa.Column("color_hue", sa.Float()),
        "color_saturation":       sa.Column("color_saturation", sa.Float()),
        "color_lightness":        sa.Column("color_lightness", sa.Float()),
        "mood_tags":              sa.Column("mood_tags", sa.JSON()),
        "instrument_tags":        sa.Column("instrument_tags", sa.JSON()),
        "voice_gender":           sa.Column("voice_gender", sa.String(16)),
        "voice_gender_confidence":sa.Column("voice_gender_confidence", sa.Float()),
        "lrclib_id":              sa.Column("lrclib_id", sa.BigInteger()),
        "mood_score":             sa.Column("mood_score", sa.Float()),
        "dance_score":            sa.Column("dance_score", sa.Float()),
        "acoustic_score":         sa.Column("acoustic_score", sa.Float()),
        "combined_positivity":    sa.Column("combined_positivity", sa.Float()),
        "energy_level":           sa.Column("energy_level", sa.String(16)),
        "tempo_category":         sa.Column("tempo_category", sa.String(16)),
        "has_audio_features":     sa.Column("has_audio_features", sa.Boolean()),
    }
    cols_after = _existing_columns(bind)
    for col_name, col_def in restore.items():
        if col_name not in cols_after:
            op.add_column("songs", col_def)

    # Restore song_embeddings orphaned columns (data was all NULL anyway)
    emb_cols_after = _existing_columns(bind, "song_embeddings")
    if "videberta_embedding" not in emb_cols_after:
        op.add_column("song_embeddings", sa.Column("videberta_embedding", Vector(768)))
    if "mert_embedding" not in emb_cols_after:
        op.add_column("song_embeddings", sa.Column("mert_embedding", Vector(768)))
