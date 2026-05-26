"""Add ML-predicted tags, voice gender, arousal, and fingerprint columns to dim_song

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dim_song', sa.Column('arousal', sa.Float(), nullable=True,
                  comment='Arousal from DEAM model (0-1)'))
    op.add_column('dim_song', sa.Column('mood_tags', sa.JSON(), nullable=True,
                  comment='MTG-Jamendo mood/theme predictions {label: score}'))
    op.add_column('dim_song', sa.Column('genre_tags', sa.JSON(), nullable=True,
                  comment='Genre Discogs400 predictions {label: score}'))
    op.add_column('dim_song', sa.Column('instrument_tags', sa.JSON(), nullable=True,
                  comment='MTG-Jamendo instrument predictions {label: score}'))
    op.add_column('dim_song', sa.Column('voice_gender', sa.String(16), nullable=True,
                  comment='male | female from gender classifier'))
    op.add_column('dim_song', sa.Column('voice_gender_confidence', sa.Float(), nullable=True,
                  comment='Gender classifier confidence'))
    op.add_column('dim_song', sa.Column('audio_fingerprint', sa.Text(), nullable=True,
                  comment='Chromaprint fingerprint hash'))


def downgrade():
    op.drop_column('dim_song', 'audio_fingerprint')
    op.drop_column('dim_song', 'voice_gender_confidence')
    op.drop_column('dim_song', 'voice_gender')
    op.drop_column('dim_song', 'instrument_tags')
    op.drop_column('dim_song', 'genre_tags')
    op.drop_column('dim_song', 'mood_tags')
    op.drop_column('dim_song', 'arousal')
