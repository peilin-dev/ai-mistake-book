from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.access import own_assignment
from app.classes.access import own_class
from app.deps import current_teacher, get_db
from app.models import (
    AnswerKeyStatus,
    Assignment,
    Page,
    PageStatus,
    QuestionResult,
    Subject,
    Teacher,
)

router = APIRouter(tags=["assignments"])


class AssignmentIn(BaseModel):
    class_id: int
    subject: Subject
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    class_id: int
    subject: Subject
    title: str
    answer_key_status: AnswerKeyStatus


class ProgressOut(BaseModel):
    total: int
    queued: int
    processing: int
    done: int
    failed: int
    needs_review: int


@router.post("/assignments", response_model=AssignmentOut, status_code=201)
async def create_assignment(
    body: AssignmentIn,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    await own_class(db, teacher, body.class_id)
    a = Assignment(class_id=body.class_id, subject=body.subject, title=body.title)
    db.add(a)
    teacher.last_subject = body.subject
    await db.commit()  # insert + last_subject update in one transaction
    return a


@router.get("/classes/{class_id}/assignments", response_model=list[AssignmentOut])
async def list_assignments(
    class_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    await own_class(db, teacher, class_id)
    result = await db.execute(
        select(Assignment).where(Assignment.class_id == class_id).order_by(Assignment.id.desc())
    )
    return list(result.scalars())


@router.get("/assignments/{assignment_id}", response_model=AssignmentOut)
async def get_assignment(
    assignment_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    return await own_assignment(db, teacher, assignment_id)


@router.get("/assignments/{assignment_id}/progress", response_model=ProgressOut)
async def assignment_progress(
    assignment_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    await own_assignment(db, teacher, assignment_id)
    statuses = (PageStatus.queued, PageStatus.processing, PageStatus.done, PageStatus.failed)
    counts = (
        await db.execute(
            select(
                func.count(Page.id),
                *(func.coalesce(func.sum(case((Page.status == s, 1), else_=0)), 0) for s in statuses),
            ).where(Page.assignment_id == assignment_id)
        )
    ).one()
    needs_review = (
        await db.execute(
            select(func.count(QuestionResult.id))
            .join(Page, Page.id == QuestionResult.page_id)
            .where(
                Page.assignment_id == assignment_id,
                QuestionResult.needs_review.is_(True),
                QuestionResult.reviewed.is_(False),
            )
        )
    ).scalar_one()
    total, queued, processing, done, failed = (int(c) for c in counts)
    return ProgressOut(
        total=total,
        queued=queued,
        processing=processing,
        done=done,
        failed=failed,
        needs_review=needs_review,
    )
