"""initial

Revision ID: 0001
Revises: 
Create Date: 2026-10-20 21:47:33.889586

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Indexes go with their tables (MySQL cannot drop an index an FK relies on).
    op.create_table('knowledge_points',
    sa.Column('subject', sa.Enum('chinese', 'math', 'english', 'physics', 'chemistry', 'biology', 'history', 'geography', 'politics', 'science', 'other', name='subject', native_enum=False, length=32), nullable=False),
    sa.Column('grade_band', sa.String(length=16), nullable=False),
    sa.Column('parent_id', sa.BigInteger(), nullable=True),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['knowledge_points.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_knowledge_points_parent_id'), 'knowledge_points', ['parent_id'], unique=False)
    op.create_table('schools',
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_table('teachers',
    sa.Column('unionid', sa.String(length=64), nullable=True),
    sa.Column('mp_openid', sa.String(length=64), nullable=True),
    sa.Column('display_name', sa.String(length=64), nullable=True),
    sa.Column('school_id', sa.BigInteger(), nullable=True),
    sa.Column('last_subject', sa.Enum('chinese', 'math', 'english', 'physics', 'chemistry', 'biology', 'history', 'geography', 'politics', 'science', 'other', name='subject', native_enum=False, length=32), nullable=True),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('mp_openid'),
    sa.UniqueConstraint('unionid'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_table('classes',
    sa.Column('teacher_id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('grade', sa.Integer(), nullable=False),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_classes_teacher_id'), 'classes', ['teacher_id'], unique=False)
    op.create_table('usage_records',
    sa.Column('teacher_id', sa.BigInteger(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('model', sa.String(length=64), nullable=False),
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_fen', sa.Float(), nullable=False),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_usage_records_teacher_id'), 'usage_records', ['teacher_id'], unique=False)
    op.create_table('assignments',
    sa.Column('class_id', sa.BigInteger(), nullable=False),
    sa.Column('subject', sa.Enum('chinese', 'math', 'english', 'physics', 'chemistry', 'biology', 'history', 'geography', 'politics', 'science', 'other', name='subject', native_enum=False, length=32), nullable=False),
    sa.Column('title', sa.String(length=128), nullable=False),
    sa.Column('answer_key_status', sa.Enum('none', 'pending', 'confirmed', name='answer_key_status', native_enum=False, length=32), nullable=False),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_assignments_class_id'), 'assignments', ['class_id'], unique=False)
    op.create_table('students',
    sa.Column('class_id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('student_no', sa.String(length=32), nullable=True),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_students_class_id'), 'students', ['class_id'], unique=False)
    op.create_table('answer_items',
    sa.Column('assignment_id', sa.BigInteger(), nullable=False),
    sa.Column('question_no', sa.String(length=32), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('max_score', sa.Float(), nullable=True),
    sa.Column('is_subjective', sa.Boolean(), nullable=False),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_answer_items_assignment_id'), 'answer_items', ['assignment_id'], unique=False)
    op.create_table('pages',
    sa.Column('assignment_id', sa.BigInteger(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('image_key', sa.String(length=255), nullable=False),
    sa.Column('image_sha256', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('queued', 'processing', 'done', 'failed', name='page_status', native_enum=False, length=32), nullable=False),
    sa.Column('fail_reason', sa.String(length=64), nullable=True),
    sa.Column('student_id', sa.BigInteger(), nullable=True),
    sa.Column('original_deleted_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('assignment_id', 'image_sha256', name='uq_page_assignment_sha'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_pages_assignment_id'), 'pages', ['assignment_id'], unique=False)
    op.create_index(op.f('ix_pages_student_id'), 'pages', ['student_id'], unique=False)
    op.create_table('submissions',
    sa.Column('assignment_id', sa.BigInteger(), nullable=False),
    sa.Column('student_id', sa.BigInteger(), nullable=False),
    sa.Column('total_score', sa.Float(), nullable=False),
    sa.Column('needs_review_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('assignment_id', 'student_id', name='uq_submission_assignment_student'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_submissions_assignment_id'), 'submissions', ['assignment_id'], unique=False)
    op.create_index(op.f('ix_submissions_student_id'), 'submissions', ['student_id'], unique=False)
    op.create_table('question_results',
    sa.Column('submission_id', sa.BigInteger(), nullable=True),
    sa.Column('page_id', sa.BigInteger(), nullable=False),
    sa.Column('question_no', sa.String(length=32), nullable=False),
    sa.Column('question_text', sa.Text(), nullable=True),
    sa.Column('student_answer', sa.Text(), nullable=True),
    sa.Column('correct_answer', sa.Text(), nullable=True),
    sa.Column('answer_verified', sa.Boolean(), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('max_score', sa.Float(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('needs_review', sa.Boolean(), nullable=False),
    sa.Column('reviewed', sa.Boolean(), nullable=False),
    sa.Column('model_is_correct', sa.Boolean(), nullable=True),
    sa.Column('model_score', sa.Float(), nullable=True),
    sa.Column('error_reason', sa.Text(), nullable=True),
    sa.Column('knowledge_point_id', sa.BigInteger(), nullable=True),
    sa.Column('crop_key', sa.String(length=255), nullable=True),
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['knowledge_point_id'], ['knowledge_points.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index(op.f('ix_question_results_knowledge_point_id'), 'question_results', ['knowledge_point_id'], unique=False)
    op.create_index(op.f('ix_question_results_page_id'), 'question_results', ['page_id'], unique=False)
    op.create_index(op.f('ix_question_results_submission_id'), 'question_results', ['submission_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # Indexes go with their tables (MySQL cannot drop an index an FK relies on).
    op.drop_table('question_results')
    op.drop_table('submissions')
    op.drop_table('pages')
    op.drop_table('answer_items')
    op.drop_table('students')
    op.drop_table('assignments')
    op.drop_table('usage_records')
    op.drop_table('classes')
    op.drop_table('teachers')
    op.drop_table('schools')
    op.drop_table('knowledge_points')
    # ### end Alembic commands ###
