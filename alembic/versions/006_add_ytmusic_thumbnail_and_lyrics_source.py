"""Add ytmusic_thumbnail_url and lyrics_source to dim_song

Revision ID: 006
Revises: a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '006'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('dim_song', sa.Column('ytmusic_thumbnail_url', sa.Text(), comment='High-res thumbnail from YTMusic'))
    op.add_column('dim_song', sa.Column('lyrics_source', sa.String(16), comment='ytmusic | lrclib'))


def downgrade() -> None:
    op.drop_column('dim_song', 'lyrics_source')
    op.drop_column('dim_song', 'ytmusic_thumbnail_url')
