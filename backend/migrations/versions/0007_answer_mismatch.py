"""question_results.answer_mismatch

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-21 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('question_results',
                  sa.Column('answer_mismatch', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('question_results', 'answer_mismatch')
