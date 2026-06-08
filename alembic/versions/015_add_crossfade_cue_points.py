"""Add crossfade cue points + downbeat grid to songs (Smart Crossfade Phase 3).

Revision ID: 015
Revises: 014
Create Date: 2026-05-29

- fade_out_cue_s: seconds into trackA where outro starts (Foote novelty boundary)
- fade_in_cue_s: seconds into trackB to skip intro silence
- downbeat_times_json: JSON array of downbeat timestamps (only for danceable tracks)

Computed offline by tools/extract_cue_points.py via librosa.segment.agglomerative
+ librosa.beat.beat_track. Nullable so existing rows backfill incrementally.
"""

from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("songs")}
    if "fade_out_cue_s" not in columns:
        op.add_column(
            'songs',
            sa.Column('fade_out_cue_s', sa.Float(), nullable=True,
                      comment='Outro start (s) — last structural boundary before silence')
        )
    if "fade_in_cue_s" not in columns:
        op.add_column(
            'songs',
            sa.Column('fade_in_cue_s', sa.Float(), nullable=True,
                      comment='Intro end (s) — first structural boundary after silence')
        )
    if "downbeat_times_json" not in columns:
        op.add_column(
            'songs',
            sa.Column('downbeat_times_json', sa.Text(), nullable=True,
                      comment='JSON array of downbeat timestamps (for beat-aligned mixing)')
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("songs")}
    if "downbeat_times_json" in columns:
        op.drop_column('songs', 'downbeat_times_json')
    if "fade_in_cue_s" in columns:
        op.drop_column('songs', 'fade_in_cue_s')
    if "fade_out_cue_s" in columns:
        op.drop_column('songs', 'fade_out_cue_s')
