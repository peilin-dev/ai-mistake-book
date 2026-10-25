"""Store structured scoring steps and teacher assignment rubrics."""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("question_results", sa.Column("scoring_steps", sa.JSON(), nullable=True))
    op.add_column("assignments", sa.Column("grading_rules", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("assignments", "grading_rules")
    op.drop_column("question_results", "scoring_steps")
