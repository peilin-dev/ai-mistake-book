"""password login and per-teacher quota

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-23 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('teachers', sa.Column('login_name', sa.String(length=32), nullable=True))
    op.add_column('teachers', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column('teachers', sa.Column('page_quota', sa.Integer(), nullable=True))
    op.create_unique_constraint('login_name','teachers', ['login_name'])
    # Teachers that exist today keep the 300-page allowance; later ones get FREE_MONTHLY_PAGES.
    op.execute("UPDATE teachers SET page_quota = 300")


def downgrade() -> None:
    op.drop_constraint('login_name','teachers', type_='unique')
    op.drop_column('teachers', 'page_quota')
    op.drop_column('teachers', 'password_hash')
    op.drop_column('teachers', 'login_name')
