"""Grading pipeline for one page (spec section 7)."""
import asyncio
import logging

from pydantic import ValidationError
from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelCallError, ModelOutputError, VisionModel
from app.ai.usage import record_usage
from app.config import Settings, get_settings
from app.grading.crop import crop, prepare_image
from app.grading.matching import match_student
from app.grading.prompts import build_grading_prompt
from app.grading.rules import filter_knowledge_point, needs_review
from app.grading.schema import GradedPage, GradedQuestion
from app.knowledge.service import candidates
from app.models import (
    AnswerItem,
    AnswerKeyStatus,
    Assignment,
    Class_,
    Page,
    PageStatus,
    QuestionResult,
    Student,
    Submission,
)
from app.storage.base import Storage

log = logging.getLogger(__name__)


async def set_page_status(db: AsyncSession, page_id: int, status: PageStatus, reason: str | None) -> None:
    page = await db.get(Page, page_id)  # reloads if a rollback expired it
    page.status, page.fail_reason = status, reason
    await db.commit()


async def grade_page(db: AsyncSession, storage: Storage, model: VisionModel, page_id: int) -> None:
    page = await db.get(Page, page_id)
    if page is None:
        log.warning("grade_page: page %s not found", page_id)
        return
    await set_page_status(db, page_id, PageStatus.processing, None)
    try:
        await _grade(db, storage, model, page, get_settings())
    except ModelCallError:
        # Keep usage already recorded; arq decides whether to retry.
        await set_page_status(db, page_id, PageStatus.queued, None)
        raise
    except Exception:
        log.exception("grade_page: page %s failed", page_id)
        await db.rollback()
        await set_page_status(db, page_id, PageStatus.failed, "internal_error")
        raise


async def _grade(db: AsyncSession, storage: Storage, model: VisionModel, page: Page, settings: Settings) -> None:
    assignment = await db.get(Assignment, page.assignment_id)
    cls = await db.get(Class_, assignment.class_id)
    image = await asyncio.to_thread(prepare_image, await storage.get(page.image_key))
    answers = await _answer_key(db, assignment)
    kps = await candidates(db, assignment.subject, cls.grade)
    prompt = build_grading_prompt(assignment.subject.value, cls.grade, list(answers.values()), kps)

    result = await _call_model(db, model, prompt, image, cls.teacher_id)
    if result is None or not result.questions:
        reason = "model_output_invalid" if result is None else "unreadable"
        await set_page_status(db, page.id, PageStatus.failed, reason)
        return

    roster = [(sid, name) for sid, name in await db.execute(
        select(Student.id, Student.name).where(Student.class_id == cls.id))]
    match = match_student(result.student_name, roster, await _previous_student(db, page),
                          settings.NAME_MATCH_THRESHOLD)
    page.student_id = match.student_id
    old_submissions, old_crops = await _clear_results(db, page.id)
    submission_id = await _submission_id(db, page.assignment_id, match.student_id)
    allowed_kps = {kp.id for kp in kps}

    rows = []
    for gq in result.questions:
        row = _result_row(gq, answers.get(gq.no), allowed_kps)
        row.page_id, row.submission_id = page.id, submission_id
        row.needs_review = needs_review(row.confidence, row.answer_verified, match.status,
                                        settings.REVIEW_CONFIDENCE_THRESHOLD)
        db.add(row)
        rows.append((row, gq))
    await db.flush()  # ids for crop keys
    for row, gq in rows:
        if not row.is_correct:
            row.crop_key = f"crops/{cls.teacher_id}/{assignment.id}/{row.id}.jpg"
            await storage.put(row.crop_key, crop(image, gq.bbox), "image/jpeg")

    for sid in (old_submissions | {submission_id}) - {None}:
        await _recompute_submission(db, sid)
    page.status, page.fail_reason = PageStatus.done, None
    await db.commit()
    for crop_key in old_crops:
        await storage.delete(crop_key)


async def _answer_key(db: AsyncSession, assignment: Assignment) -> dict[str, AnswerItem]:
    if assignment.answer_key_status != AnswerKeyStatus.confirmed:
        return {}
    items = (await db.execute(
        select(AnswerItem).where(AnswerItem.assignment_id == assignment.id).order_by(AnswerItem.id)
    )).scalars()
    return {item.question_no: item for item in items}


async def _call_model(
    db: AsyncSession, model: VisionModel, prompt: str, image: bytes, teacher_id: int
) -> GradedPage | None:
    """Two attempts at a schema-valid answer; ModelCallError propagates."""
    for attempt in (1, 2):
        try:
            result = await model.complete_json(prompt, [image])
        except ModelOutputError as e:
            log.warning("grading output not JSON (attempt %s): %s", attempt, e)
            continue
        await record_usage(db, teacher_id, "grading", result)
        try:
            return GradedPage.model_validate(result.data)
        except ValidationError as e:
            log.warning("grading output invalid (attempt %s): %s", attempt, e)
    return None


async def _previous_student(db: AsyncSession, page: Page) -> int | None:
    stmt = select(Page.student_id).where(
        Page.assignment_id == page.assignment_id,
        Page.seq == page.seq - 1,
        Page.status == PageStatus.done,
    ).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _clear_results(db: AsyncSession, page_id: int) -> tuple[set[int | None], list[str]]:
    """Delete this page's previous results (job retries); return their submissions and crops."""
    old = (await db.execute(
        select(QuestionResult.submission_id, QuestionResult.crop_key).where(QuestionResult.page_id == page_id)
    )).all()
    await db.execute(delete(QuestionResult).where(QuestionResult.page_id == page_id))
    return {sid for sid, _ in old}, [key for _, key in old if key]


async def _submission_id(db: AsyncSession, assignment_id: int, student_id: int | None) -> int | None:
    if student_id is None:
        return None
    find = select(Submission.id).where(
        Submission.assignment_id == assignment_id, Submission.student_id == student_id)
    if (sid := (await db.execute(find)).scalar_one_or_none()) is not None:
        return sid
    sub = Submission(assignment_id=assignment_id, student_id=student_id)
    try:
        async with db.begin_nested():
            db.add(sub)
    except IntegrityError:  # another page of this student created it concurrently
        return (await db.execute(find)).scalar_one()
    return sub.id


def _result_row(gq: GradedQuestion, item: AnswerItem | None, allowed_kps: set[int]) -> QuestionResult:
    if item is not None:
        max_score = item.max_score if item.max_score is not None else gq.max_score
        correct, verified, score = item.answer, True, min(gq.score, max_score)
    else:
        max_score, correct, verified, score = gq.max_score, gq.correct_answer, False, gq.score
    return QuestionResult(
        question_no=gq.no,
        question_text=gq.question_text,
        student_answer=gq.student_answer,
        correct_answer=correct,
        answer_verified=verified,
        is_correct=gq.is_correct,
        score=score,
        max_score=max_score,
        confidence=gq.confidence,
        reviewed=False,
        model_is_correct=None,
        model_score=None,
        error_reason=gq.error_reason,
        knowledge_point_id=filter_knowledge_point(gq.knowledge_point_id, allowed_kps),
    )


async def _recompute_submission(db: AsyncSession, submission_id: int) -> None:
    pending = case((and_(QuestionResult.needs_review.is_(True), QuestionResult.reviewed.is_(False)), 1), else_=0)
    total, review_count = (await db.execute(
        select(func.coalesce(func.sum(QuestionResult.score), 0), func.coalesce(func.sum(pending), 0))
        .where(QuestionResult.submission_id == submission_id)
    )).one()
    sub = await db.get(Submission, submission_id)
    sub.total_score, sub.needs_review_count = float(total), int(review_count)
