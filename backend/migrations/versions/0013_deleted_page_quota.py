"""deleted page quota

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-23 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deleted_page_quota',
        sa.Column('teacher_id', sa.BigInteger(), nullable=False),
        sa.Column('page_created_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index(op.f('ix_deleted_page_quota_teacher_id'), 'deleted_page_quota', ['teacher_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_deleted_page_quota_teacher_id'), table_name='deleted_page_quota')
    op.drop_table('deleted_page_quota')
