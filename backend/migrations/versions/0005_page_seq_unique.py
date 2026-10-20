"""unique (assignment_id, seq) on pages

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-21 18:00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint('uq_page_assignment_seq', 'pages', ['assignment_id', 'seq'])


def downgrade() -> None:
    # The FK on assignment_id has its own index (ix_pages_assignment_id), so this index can go.
    op.drop_constraint('uq_page_assignment_seq', 'pages', type_='unique')
