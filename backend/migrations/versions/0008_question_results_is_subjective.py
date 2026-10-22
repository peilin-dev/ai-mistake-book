"""question_results.is_subjective

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-22 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('question_results',
                  sa.Column('is_subjective', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('question_results', 'is_subjective')
