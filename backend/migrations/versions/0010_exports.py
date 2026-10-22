"""exports

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-22 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('exports',
    sa.Column('teacher_id', sa.BigInteger(), nullable=False),
    sa.Column('file_key', sa.String(length=255), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_exports_teacher_id'), 'exports', ['teacher_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_exports_teacher_id'), table_name='exports')
    op.drop_table('exports')
