"""Builds the export PDFs from the statistics and prunes old ones."""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.rules import LECTURE_TOP_N
from app.analytics.stats import StudentQuestion, StudentResult, assignment_stats, group_wrong_answers
from app.export.pdf import (
    LectureQuestion,
    LectureSheet,
    MistakeItem,
    StudentSheet,
    render_lecture,
    render_mistakes,
)
from app.models import Assignment, Class_, Export, Teacher
from app.storage.base import Storage

logger = logging.getLogger(__name__)

MAX_CROPS_PER_QUESTION = 3
PURGE_BATCH = 200
_INVALID_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class NothingToExport(Exception):
    """Raised with the teacher-facing reason when there is nothing to print."""


def safe_name(text: str) -> str:
    return _INVALID_NAME.sub("", text).strip().strip(".") or "导出"


def _date(created_at: datetime) -> str:
    local = created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Shanghai"))
    return local.strftime("%Y-%m-%d")


async def _crop(storage: Storage, key: str) -> bytes | None:
    try:
        return await storage.get(key)
    except FileNotFoundError:
        return None


def _score_text(q: StudentQuestion) -> str:
    def num(v: float) -> str:
        return f"{v:g}"

    if q.max_score is None:
        return f"{num(q.score)} 分"
    if q.score > 0:
        return f"得 {num(q.score)} / {num(q.max_score)} 分"
    return f"0 / {num(q.max_score)} 分"


async def _mistake_sheet(storage: Storage, result: StudentResult, cls: Class_, assignment: Assignment,
                         signature: str) -> StudentSheet | None:
    items = []
    for q in result.questions:
        if not q.wrong:
            continue
        crop = None
        for key in q.crop_keys:
            crop = await _crop(storage, key)
            if crop:
                break
        items.append(MistakeItem(
            question_no=q.question_no, question_text=q.question_text, student_answer=q.answer,
            correct_answer=q.correct_answer, score_text=_score_text(q), crop=crop))
    if not items:
        return None
    return StudentSheet(
        student_name=result.student_name, class_name=cls.name, title=assignment.title,
        date=_date(assignment.created_at), signature=signature, items=items)


async def _lecture_sheet(db: AsyncSession, storage: Storage, assignment: Assignment, cls: Class_,
                         signature: str) -> LectureSheet:
    stats = await assignment_stats(db, assignment.id)
    questions = []
    for stat in stats.questions[:LECTURE_TOP_N]:
        entries = [q for s in stats.students for q in s.questions if q.question_no == stat.question_no]
        groups = [] if stat.is_subjective else [
            (g.answer, g.count) for g in group_wrong_answers(stats.students, stat.question_no)]
        crops: list[bytes] = []
        for q in entries:
            if not q.wrong:
                continue
            for key in q.crop_keys:
                if len(crops) >= MAX_CROPS_PER_QUESTION:
                    break
                data = await _crop(storage, key)
                if data:
                    crops.append(data)
        questions.append(LectureQuestion(
            question_no=stat.question_no,
            question_text=next((q.question_text for q in entries if q.question_text), None),
            correct_answer=next((q.correct_answer for q in entries if q.correct_answer), None),
            accuracy=stat.accuracy, wrong_count=stat.wrong_count, groups=groups, crops=crops))
    return LectureSheet(
        class_name=cls.name, title=assignment.title, date=_date(assignment.created_at), signature=signature,
        overview={"average_score": stats.average_score, "pass_rate": stats.pass_rate,
                  "counted_students": stats.counted_students, "roster_size": stats.roster_size},
        questions=questions)


async def build_export(db: AsyncSession, storage: Storage, teacher: Teacher, assignment: Assignment,
                       kind: str, student_results: list[StudentResult]) -> tuple[bytes, str]:
    """Return (pdf bytes, filename). `student_results` is the one student for "student", the whole
    class for "class_students" and unused for "lecture"."""
    cls = await db.get(Class_, assignment.class_id)
    signature = teacher.display_name or "老师"
    prefix = safe_name(f"{cls.name}-{assignment.title}")
    if kind == "lecture":
        sheet = await _lecture_sheet(db, storage, assignment, cls, signature)
        return await asyncio.to_thread(render_lecture, sheet), f"{prefix}-讲评单.pdf"
    sheets = []
    for r in sorted(student_results, key=lambda r: r.student_name):
        sheet = await _mistake_sheet(storage, r, cls, assignment, signature)
        if sheet is not None:
            sheets.append(sheet)
    if not sheets:
        raise NothingToExport(
            "这位同学这次全对，没有错题可以导出" if kind == "student" else "这次没有同学有错题")
    pdf = await asyncio.to_thread(render_mistakes, sheets)
    if kind == "student":
        return pdf, f"{prefix}-{safe_name(sheets[0].student_name)}-错题单.pdf"
    return pdf, f"{prefix}-错题单.pdf"


async def store_export(db: AsyncSession, storage: Storage, teacher_id: int, kind: str, pdf: bytes) -> str:
    key = f"exports/{teacher_id}/{uuid.uuid4().hex}.pdf"
    await storage.put(key, pdf, "application/pdf")
    try:
        db.add(Export(teacher_id=teacher_id, file_key=key, kind=kind))
        await db.commit()
    except BaseException:
        # No row means the purge would never find the file, so take it back out.
        try:
            await db.rollback()
        except Exception:
            pass
        try:
            await storage.delete(key)
        except Exception:
            logger.warning("failed to remove orphan export %s", key, exc_info=True)
        raise
    return key


async def purge_old_exports(db: AsyncSession, storage: Storage, now: datetime, days: int = 7) -> int:
    """Delete exports older than `days` (file and row); a failed file delete keeps the row for retry."""
    cutoff = now - timedelta(days=days)
    purged = 0
    last_id = 0
    while True:
        rows = (await db.execute(
            select(Export).where(Export.created_at < cutoff, Export.id > last_id)
            .order_by(Export.id).limit(PURGE_BATCH)
        )).scalars().all()
        if not rows:
            return purged
        for row in rows:
            last_id = row.id
            try:
                await storage.delete(row.file_key)
            except Exception as e:
                logger.warning("failed to delete export %s; will retry: %s", row.id, e)
                continue
            await db.delete(row)
            purged += 1
        await db.commit()
