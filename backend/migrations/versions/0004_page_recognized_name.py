"""pages.recognized_name

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pages', sa.Column('recognized_name', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('pages', 'recognized_name')
