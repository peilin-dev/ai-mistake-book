import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Subject(str, enum.Enum):
    chinese = "chinese"
    math = "math"
    english = "english"
    physics = "physics"
    chemistry = "chemistry"
    biology = "biology"
    history = "history"
    geography = "geography"
    politics = "politics"
    science = "science"
    other = "other"


class PageStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class AnswerKeyStatus(str, enum.Enum):
    none = "none"
    pending = "pending"
    confirmed = "confirmed"


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    # VARCHAR storage so adding values later needs no ALTER TYPE.
    return Enum(
        cls,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def _utcnow() -> datetime:
    """Naive UTC timestamp (all times are stored as UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


def _fk(target: str, nullable: bool = False) -> Mapped[int]:
    return mapped_column(
        BigInteger, ForeignKey(target, ondelete="CASCADE"), nullable=nullable, index=True
    )


class _Base(TimestampMixin, Base):
    __abstract__ = True
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


class School(_Base):
    __tablename__ = "schools"
    name: Mapped[str] = mapped_column(String(128))


class Teacher(_Base):
    __tablename__ = "teachers"
    unionid: Mapped[str | None] = mapped_column(String(64), unique=True)
    mp_openid: Mapped[str | None] = mapped_column(String(64), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(64))
    school_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("schools.id", ondelete="SET NULL")
    )
    last_subject: Mapped[Subject | None] = mapped_column(_enum(Subject, "subject"))


class Class_(_Base):
    __tablename__ = "classes"
    teacher_id: Mapped[int] = _fk("teachers.id")
    name: Mapped[str] = mapped_column(String(64))
    grade: Mapped[int] = mapped_column(Integer)


class Student(_Base):
    __tablename__ = "students"
    class_id: Mapped[int] = _fk("classes.id")
    name: Mapped[str] = mapped_column(String(64))
    student_no: Mapped[str | None] = mapped_column(String(32))


class Assignment(_Base):
    __tablename__ = "assignments"
    class_id: Mapped[int] = _fk("classes.id")
    subject: Mapped[Subject] = mapped_column(_enum(Subject, "subject"))
    title: Mapped[str] = mapped_column(String(128))
    answer_key_status: Mapped[AnswerKeyStatus] = mapped_column(
        _enum(AnswerKeyStatus, "answer_key_status"), default=AnswerKeyStatus.none
    )


class AnswerItem(_Base):
    __tablename__ = "answer_items"
    assignment_id: Mapped[int] = _fk("assignments.id")
    question_no: Mapped[str] = mapped_column(String(32))
    answer: Mapped[str] = mapped_column(Text)
    max_score: Mapped[float | None] = mapped_column(Float)
    is_subjective: Mapped[bool] = mapped_column(Boolean, default=False)


class Page(_Base):
    __tablename__ = "pages"
    assignment_id: Mapped[int] = _fk("assignments.id")
    seq: Mapped[int] = mapped_column(Integer)
    image_key: Mapped[str] = mapped_column(String(255))
    image_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[PageStatus] = mapped_column(
        _enum(PageStatus, "page_status"), default=PageStatus.queued
    )
    fail_reason: Mapped[str | None] = mapped_column(String(64))
    # Student name the model read off this page; NULL when none was written.
    recognized_name: Mapped[str | None] = mapped_column(String(64))
    student_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("students.id", ondelete="SET NULL"), index=True
    )
    original_deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Teacher-triggered retries of a failed page; part of the arq job id (grade:{id}:{n}).
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint("assignment_id", "image_sha256", name="uq_page_assignment_sha"),
        UniqueConstraint("assignment_id", "seq", name="uq_page_assignment_seq"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class Submission(_Base):
    __tablename__ = "submissions"
    assignment_id: Mapped[int] = _fk("assignments.id")
    student_id: Mapped[int] = _fk("students.id")
    total_score: Mapped[float] = mapped_column(Float, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class KnowledgePoint(_Base):
    __tablename__ = "knowledge_points"
    subject: Mapped[Subject] = mapped_column(_enum(Subject, "subject"))
    grade_min: Mapped[int] = mapped_column(Integer)  # inclusive
    grade_max: Mapped[int] = mapped_column(Integer)  # inclusive
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))


class QuestionResult(_Base):
    __tablename__ = "question_results"
    submission_id: Mapped[int | None] = _fk("submissions.id", nullable=True)
    page_id: Mapped[int] = _fk("pages.id")
    question_no: Mapped[str] = mapped_column(String(32))
    question_text: Mapped[str | None] = mapped_column(Text)
    student_answer: Mapped[str | None] = mapped_column(Text)
    correct_answer: Mapped[str | None] = mapped_column(Text)
    answer_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0)
    max_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    # No answer key: this row's AI answer disagrees with the class majority (or ties).
    answer_mismatch: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    is_subjective: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    model_is_correct: Mapped[bool | None] = mapped_column(Boolean)
    model_score: Mapped[float | None] = mapped_column(Float)
    error_reason: Mapped[str | None] = mapped_column(Text)
    knowledge_point_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_points.id", ondelete="SET NULL"), index=True
    )
    crop_key: Mapped[str | None] = mapped_column(String(255))


class UsageRecord(_Base):
    __tablename__ = "usage_records"
    teacher_id: Mapped[int] = _fk("teachers.id")
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_fen: Mapped[float] = mapped_column(Numeric(10, 4, asdecimal=False), default=0)


class Export(_Base):
    """A generated PDF kept in storage until the daily purge removes it."""
    __tablename__ = "exports"
    teacher_id: Mapped[int] = _fk("teachers.id")
    file_key: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16))  # "lecture" | "student" | "class_students"


class AiNote(_Base):
    """Cached AI text for an assignment: a wrong-answer cause or a student summary."""
    __tablename__ = "ai_notes"
    assignment_id: Mapped[int] = _fk("assignments.id")
    kind: Mapped[str] = mapped_column(String(16))  # "cause" | "summary"
    ref: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("assignment_id", "kind", "ref", name="uq_ai_note_ref"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
