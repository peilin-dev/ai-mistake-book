"""Persist per-question instructional feedback."""
from alembic import op
import sqlalchemy as sa
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

def upgrade():
    for name in ("scoring_basis", "strengths", "guidance"):
        op.add_column("question_results", sa.Column(name, sa.Text(), nullable=True))

def downgrade():
    for name in ("guidance", "strengths", "scoring_basis"):
        op.drop_column("question_results", name)
