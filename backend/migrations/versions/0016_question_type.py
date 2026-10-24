"""Classify feedback by question type."""
from alembic import op
import sqlalchemy as sa
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("question_results", sa.Column("question_type", sa.String(24), nullable=True))

def downgrade():
    op.drop_column("question_results", "question_type")
