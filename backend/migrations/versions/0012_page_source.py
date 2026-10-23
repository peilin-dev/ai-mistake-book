"""page source

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-23 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pages', sa.Column('source', sa.String(length=8), server_default='phone', nullable=False))


def downgrade() -> None:
    op.drop_column('pages', 'source')
