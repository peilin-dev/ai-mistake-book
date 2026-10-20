import hashlib
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
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
from app.quota.service import QuotaExceeded, check_quota
from app.storage.base import Storage, get_storage

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


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
HEIC_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1"}

EnqueueGradePage = Callable[[int], Awaitable[None]]


def get_enqueuer() -> EnqueueGradePage:
    async def enqueue_grade_page(page_id: int) -> None:
        # PLACEHOLDER: Task 10 replaces this with an arq enqueue.
        return None

    return enqueue_grade_page


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """(extension, content_type) decided by magic bytes, never by client metadata."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data[4:8] == b"ftyp" and data[8:12] in HEIC_BRANDS:
        return "heic", "image/heic"
    return None


async def read_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="file too large (max 10 MB)")
        chunks.append(chunk)
    return b"".join(chunks)


class PageUploadOut(BaseModel):
    page_id: int
    seq: int
    status: PageStatus
    duplicate: bool


@router.post("/assignments/{assignment_id}/pages", response_model=PageUploadOut)
async def upload_page(
    assignment_id: int,
    file: UploadFile,
    response: Response,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
    enqueue: EnqueueGradePage = Depends(get_enqueuer),
):
    assignment = await own_assignment(db, teacher, assignment_id)
    data = await read_limited(file)
    kind = sniff_image(data)
    if kind is None:
        raise HTTPException(status_code=415, detail="only JPEG/PNG/HEIC images are accepted")
    ext, content_type = kind
    sha = hashlib.sha256(data).hexdigest()

    async def existing() -> Page | None:
        return (
            await db.execute(
                select(Page).where(Page.assignment_id == assignment.id, Page.image_sha256 == sha)
            )
        ).scalar_one_or_none()

    def duplicate_out(page: Page) -> PageUploadOut:
        response.status_code = 200
        return PageUploadOut(page_id=page.id, seq=page.seq, status=page.status, duplicate=True)

    if (page := await existing()) is not None:
        return duplicate_out(page)

    try:
        await check_quota(db, teacher.id)
    except QuotaExceeded:
        raise HTTPException(status_code=429, detail="本月批改额度已用完") from None

    max_seq = (
        await db.execute(select(func.max(Page.seq)).where(Page.assignment_id == assignment.id))
    ).scalar_one()
    page = Page(
        assignment_id=assignment.id,
        seq=(max_seq or 0) + 1,
        image_key="",  # real key needs page.id; set right after the flush
        image_sha256=sha,
        status=PageStatus.queued,
    )
    db.add(page)
    try:
        await db.flush()
    except IntegrityError:  # concurrent identical upload won the race
        await db.rollback()
        if (page := await existing()) is not None:
            return duplicate_out(page)
        raise
    page.image_key = f"originals/{teacher.id}/{assignment.id}/{page.id}.{ext}"
    try:
        await storage.put(page.image_key, data, content_type)
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    await enqueue(page.id)
    response.status_code = 201
    return PageUploadOut(page_id=page.id, seq=page.seq, status=page.status, duplicate=False)