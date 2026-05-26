"""add audio_feature_source, valence_estimated, ytmusic_video_id to dim_song

Revision ID: a1b2c3d4e5f6
Revises: 9c9733a7709f
Create Date: 2025-03-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9c9733a7709f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dim_song', sa.Column('ytmusic_video_id', sa.String(32),
                  comment='YTMusic video ID from ytmusicapi'))
    op.add_column('dim_song', sa.Column('audio_feature_source', sa.Text(),
                  comment='spotify | essentia | librosa | estimated'))
    op.add_column('dim_song', sa.Column('valence_estimated', sa.Boolean(),
                  server_default=sa.text('false'),
                  comment='True if valence was estimated, not measured'))


def downgrade() -> None:
    op.drop_column('dim_song', 'valence_estimated')
    op.drop_column('dim_song', 'audio_feature_source')
    op.drop_column('dim_song', 'ytmusic_video_id')
