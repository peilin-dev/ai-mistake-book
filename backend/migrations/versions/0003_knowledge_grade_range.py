"""knowledge_points: grade_band -> grade_min/grade_max, unique code

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows (none expected before the first import) get the widest band.
    op.add_column('knowledge_points', sa.Column('grade_min', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('knowledge_points', sa.Column('grade_max', sa.Integer(), nullable=False, server_default='12'))
    op.alter_column('knowledge_points', 'grade_min', existing_type=sa.Integer(), server_default=None)
    op.alter_column('knowledge_points', 'grade_max', existing_type=sa.Integer(), server_default=None)
    op.drop_column('knowledge_points', 'grade_band')
    op.create_unique_constraint('uq_knowledge_points_code', 'knowledge_points', ['code'])


def downgrade() -> None:
    op.drop_constraint('uq_knowledge_points_code', 'knowledge_points', type_='unique')
    op.add_column('knowledge_points', sa.Column('grade_band', sa.String(length=16), nullable=False, server_default=''))
    op.execute("UPDATE knowledge_points SET grade_band = CONCAT(grade_min, '-', grade_max)")
    op.alter_column('knowledge_points', 'grade_band', existing_type=sa.String(length=16), server_default=None)
    op.drop_column('knowledge_points', 'grade_max')
    op.drop_column('knowledge_points', 'grade_min')
