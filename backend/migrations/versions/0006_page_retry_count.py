"""pages.retry_count

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-21 18:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pages', sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('pages', 'retry_count')
