"""Add thumbnail_url column to dim_song for single YTMusic thumbnail

Revision ID: 008
Revises: 007
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dim_song', sa.Column('thumbnail_url', sa.Text(), nullable=True,
                  comment='YTMusic thumbnail URL (lh3.googleusercontent.com)'))


def downgrade():
    op.drop_column('dim_song', 'thumbnail_url')
