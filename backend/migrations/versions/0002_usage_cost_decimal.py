"""usage_records.cost_fen as DECIMAL(10,4)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20 22:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('usage_records', 'cost_fen', existing_type=sa.Float(),
                    type_=sa.Numeric(10, 4), existing_nullable=False)


def downgrade() -> None:
    op.alter_column('usage_records', 'cost_fen', existing_type=sa.Numeric(10, 4),
                    type_=sa.Float(), existing_nullable=False)