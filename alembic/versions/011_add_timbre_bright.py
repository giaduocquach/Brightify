"""Add timbre_bright column to songs table

Revision ID: 011
Revises: 010
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('songs', sa.Column('timbre_bright', sa.Float(), nullable=True,
                  comment='Timbre brightness from Essentia EffNet (0=dark, 1=bright)'))


def downgrade():
    op.drop_column('songs', 'timbre_bright')
