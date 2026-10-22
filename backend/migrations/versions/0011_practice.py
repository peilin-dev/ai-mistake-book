"""practice

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-23 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('practice_papers',
    sa.Column('assignment_id', sa.BigInteger(), nullable=False),
    sa.Column('student_id', sa.BigInteger(), nullable=True),
    sa.Column('student_key', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('partial', sa.Boolean(), nullable=False),
    sa.Column('sources_total', sa.Integer(), nullable=False),
    sa.Column('sources_done', sa.Integer(), nullable=False),
    sa.Column('error', sa.String(length=128), nullable=True),
    sa.Column('generated_at', sa.DateTime(), nullable=True),
    sa.Column('last_replace_failed_item', sa.Integer(), nullable=True),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('assignment_id', 'student_key', name='uq_practice_paper_key'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_practice_papers_assignment_id'), 'practice_papers', ['assignment_id'], unique=False)
    op.create_index(op.f('ix_practice_papers_student_id'), 'practice_papers', ['student_id'], unique=False)
    op.create_table('practice_items',
    sa.Column('paper_id', sa.BigInteger(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('source_no', sa.String(length=32), nullable=False),
    sa.Column('knowledge_point_id', sa.BigInteger(), nullable=True),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('stem', sa.Text(), nullable=False),
    sa.Column('options', sa.Text(), nullable=True),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('replacing', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['knowledge_point_id'], ['knowledge_points.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['paper_id'], ['practice_papers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_practice_items_knowledge_point_id'), 'practice_items', ['knowledge_point_id'], unique=False)
    op.create_index(op.f('ix_practice_items_paper_id'), 'practice_items', ['paper_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_practice_items_paper_id'), table_name='practice_items')
    op.drop_index(op.f('ix_practice_items_knowledge_point_id'), table_name='practice_items')
    op.drop_table('practice_items')
    op.drop_index(op.f('ix_practice_papers_student_id'), table_name='practice_papers')
    op.drop_index(op.f('ix_practice_papers_assignment_id'), table_name='practice_papers')
    op.drop_table('practice_papers')
