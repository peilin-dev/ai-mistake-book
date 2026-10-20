"""Teacher review queue and corrections (spec 7.3)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.assignments.access import own_assignment
from app.deps import current_teacher, get_db
from app.grading.pipeline import (
    attach_following_pages,
    fresh_page,
    get_or_create_submission,
    lock_assignment,
    recompute_submission,
)
from app.grading.rules import needs_review
from app.models import Assignment, Class_, Page, PageStatus, QuestionResult, Student, Submission, Teacher
from app.storage.base import Storage, get_storage

router = APIRouter(tags=["review"])


class AssignPage(BaseModel):
    student_id: int


class CorrectQuestion(BaseModel):
    is_correct: bool | None = None
    score: float | None = None


def _question_fields(r: QuestionResult) -> dict:
    return {
        "id": r.id,
        "question_no": r.question_no,
        "question_text": r.question_text,
        "student_answer": r.student_answer,
        "correct_answer": r.correct_answer,
        "is_correct": r.is_correct,
        "score": r.score,
        "max_score": r.max_score,
        "confidence": r.confidence,
    }


def _result_out(r: QuestionResult, storage: Storage) -> dict:
    return {
        **_question_fields(r),
        "page_id": r.page_id,
        "needs_review": r.needs_review,
        "reviewed": r.reviewed,
        "model_is_correct": r.model_is_correct,
        "model_score": r.model_score,
        "crop_url": storage.signed_url(r.crop_key) if r.crop_key else None,
    }


def _reason(page_student_id: int | None, r: QuestionResult, threshold: float) -> str:
    if page_student_id is None:
        return "student_uncertain"
    if r.confidence < threshold:
        return "low_confidence"
    if not r.answer_verified:
        return "unverified_answer"
    return "student_uncertain"  # fuzzy name match


@router.get("/assignments/{assignment_id}/review")
async def review_queue(
    assignment_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> dict:
    await own_assignment(db, teacher, assignment_id)
    threshold = get_settings().REVIEW_CONFIDENCE_THRESHOLD
    pages = (await db.execute(
        select(Page).where(
            Page.assignment_id == assignment_id,
            Page.status == PageStatus.done,
            Page.student_id.is_(None),
        ).order_by(Page.seq)
    )).scalars()
    rows = (await db.execute(
        select(QuestionResult, Page, Student.name)
        .join(Page, Page.id == QuestionResult.page_id)
        .outerjoin(Student, Student.id == Page.student_id)
        .where(
            Page.assignment_id == assignment_id,
            QuestionResult.needs_review.is_(True),
            QuestionResult.reviewed.is_(False),
        )
        .order_by(Page.seq, QuestionResult.id)
    )).all()
    return {
        "pages_unassigned": [
            {
                "page_id": p.id,
                "image_url": None if p.original_deleted_at else storage.signed_url(p.image_key),
                "recognized_name": p.recognized_name,
            }
            for p in pages
        ],
        "questions": [
            {
                **_question_fields(r),
                "student_name": name,
                "reason": _reason(page.student_id, r, threshold),
                "crop_url": storage.signed_url(r.crop_key) if r.crop_key else None,
                # The page lets the teacher fix a fuzzy student match via PATCH /pages/{page_id}.
                "page_id": page.id,
                "recognized_name": page.recognized_name,
                "image_url": None if page.original_deleted_at else storage.signed_url(page.image_key),
            }
            for r, page, name in rows
        ],
    }


@router.patch("/pages/{page_id}")
async def assign_student(
    page_id: int,
    body: AssignPage,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
) -> dict:
    owned = (await db.execute(
        select(Page.assignment_id, Class_.id)
        .join(Assignment, Assignment.id == Page.assignment_id)
        .join(Class_, Class_.id == Assignment.class_id)
        .where(Page.id == page_id, Class_.teacher_id == teacher.id)
    )).first()
    if owned is None:
        raise HTTPException(404, "page not found")
    assignment_id, class_id = owned
    await lock_assignment(db, assignment_id)
    page = (await db.execute(
        select(Page).where(Page.id == page_id).execution_options(populate_existing=True)
    )).scalar_one()
    if page.status != PageStatus.done:
        raise HTTPException(409, "页面尚未批改完成")
    student = (await db.execute(
        select(Student.id).where(Student.id == body.student_id, Student.class_id == class_id)
    )).scalar_one_or_none()
    if student is None:
        raise HTTPException(404, "student not found")

    settings = get_settings()
    old_student_id = page.student_id
    results = (await db.execute(
        select(QuestionResult).where(QuestionResult.page_id == page_id).execution_options(populate_existing=True)
    )).scalars().all()
    old_submissions = {r.submission_id for r in results} - {None}
    page.student_id = student
    submission_id = await get_or_create_submission(db, assignment_id, student)
    for r in results:
        r.submission_id = submission_id
        if not r.reviewed:  # teacher confirmed the student, so only the other rules remain
            r.needs_review = needs_review(r.confidence, r.answer_verified, "exact",
                                          settings.REVIEW_CONFIDENCE_THRESHOLD)
    last = page
    if old_student_id is not None and old_student_id != student:
        # Nameless pages that continued this page followed the old student; move them too.
        last, moved = await _move_continuation(db, page, old_student_id, submission_id)
        old_submissions |= moved
    await attach_following_pages(db, last, submission_id, settings)
    for sid in old_submissions | {submission_id}:
        await recompute_submission(db, sid)
    await db.commit()
    return {"page_id": page.id, "student_id": page.student_id}


async def _move_continuation(
    db: AsyncSession, page: Page, old_student_id: int, submission_id: int
) -> tuple[Page, set[int]]:
    """Move done, nameless pages after `page` still on the old student; return the last
    page moved (or `page`) and the submissions their results left."""
    last, left = page, set()
    seq = page.seq + 1
    while (nxt := await fresh_page(db, Page.assignment_id == page.assignment_id, Page.seq == seq)) is not None:
        if (nxt.status != PageStatus.done or nxt.recognized_name is not None
                or nxt.student_id != old_student_id):
            break
        nxt.student_id = page.student_id
        stmt = select(QuestionResult).where(QuestionResult.page_id == nxt.id).execution_options(
            populate_existing=True)
        for row in (await db.execute(stmt)).scalars():
            if row.submission_id is not None:
                left.add(row.submission_id)
            row.submission_id = submission_id
        last = nxt
        seq += 1
    return last, left


async def _own_result(db: AsyncSession, teacher: Teacher, result_id: int) -> tuple[int, int]:
    """(assignment_id, page_id) of a result the teacher owns; 404 otherwise."""
    row = (await db.execute(
        select(Page.assignment_id, QuestionResult.page_id)
        .join(Page, Page.id == QuestionResult.page_id)
        .join(Assignment, Assignment.id == Page.assignment_id)
        .join(Class_, Class_.id == Assignment.class_id)
        .where(QuestionResult.id == result_id, Class_.teacher_id == teacher.id)
    )).first()
    if row is None:
        raise HTTPException(404, "question result not found")
    return row[0], row[1]


@router.patch("/question-results/{result_id}")
async def correct_question(
    result_id: int,
    body: CorrectQuestion,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> dict:
    if body.is_correct is None and body.score is None:
        raise HTTPException(422, "is_correct or score is required")
    assignment_id, _ = await _own_result(db, teacher, result_id)
    await lock_assignment(db, assignment_id)
    r = (await db.execute(
        select(QuestionResult).where(QuestionResult.id == result_id).execution_options(populate_existing=True)
    )).scalar_one()
    if body.score is not None and not (0 <= body.score <= (r.max_score if r.max_score is not None else body.score)):
        raise HTTPException(422, "score must be between 0 and max_score")
    if r.model_is_correct is None:
        r.model_is_correct, r.model_score = r.is_correct, r.score
    if body.is_correct is not None:
        r.is_correct = body.is_correct
    if body.score is not None:
        r.score = body.score
    elif body.is_correct is not None:
        r.score = 0 if not body.is_correct else (r.max_score or 0)
    r.reviewed, r.needs_review = True, False
    if r.submission_id is not None:
        await recompute_submission(db, r.submission_id)
    await db.commit()
    return _result_out(r, storage)


@router.get("/submissions/{submission_id}")
async def get_submission(
    submission_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> dict:
    row = (await db.execute(
        select(Submission, Student.name)
        .join(Student, Student.id == Submission.student_id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(Class_, Class_.id == Assignment.class_id)
        .where(Submission.id == submission_id, Class_.teacher_id == teacher.id)
    )).first()
    if row is None:
        raise HTTPException(404, "submission not found")
    sub, student_name = row
    results = (await db.execute(
        select(QuestionResult)
        .join(Page, Page.id == QuestionResult.page_id)
        .where(QuestionResult.submission_id == submission_id)
        .order_by(Page.seq, QuestionResult.id)
    )).scalars()
    return {
        "id": sub.id,
        "assignment_id": sub.assignment_id,
        "student_id": sub.student_id,
        "student_name": student_name,
        "total_score": sub.total_score,
        "needs_review_count": sub.needs_review_count,
        "questions": [_result_out(r, storage) for r in results],
    }
