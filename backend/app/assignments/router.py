import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assignments.access import own_assignment
from app.classes.access import own_class
from app.config import get_settings
from app.deps import current_teacher, get_db
from app.ai.base import VisionModel
from app.grading.answer_key import AnswerKeyItem, extract_answer_key, get_answer_key_model
from app.grading.pipeline import clear_page_results, lock_assignment, recompute_submission
from app.models import (
    AnswerItem,
    AnswerKeyStatus,
    Assignment,
    Page,
    PageStatus,
    QuestionResult,
    Student,
    Subject,
    Submission,
    Teacher,
)
from app.quota.service import QuotaExceeded, check_quota
from app.storage.base import Storage, get_storage

log = logging.getLogger(__name__)
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


class PageListItem(BaseModel):
    page_id: int
    seq: int
    status: PageStatus
    fail_reason: str | None
    student_id: int | None
    student_name: str | None
    recognized_name: str | None


class SubmissionListItem(BaseModel):
    id: int
    student_id: int
    student_name: str
    total_score: float
    needs_review_count: int


@router.get("/assignments/{assignment_id}/pages", response_model=list[PageListItem])
async def list_pages(
    assignment_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    await own_assignment(db, teacher, assignment_id)
    rows = (await db.execute(
        select(Page, Student.name)
        .outerjoin(Student, Student.id == Page.student_id)
        .where(Page.assignment_id == assignment_id)
        .order_by(Page.seq)
    )).all()
    return [
        PageListItem(page_id=p.id, seq=p.seq, status=p.status, fail_reason=p.fail_reason,
                     student_id=p.student_id, student_name=name, recognized_name=p.recognized_name)
        for p, name in rows
    ]


@router.get("/assignments/{assignment_id}/submissions", response_model=list[SubmissionListItem])
async def list_submissions(
    assignment_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    await own_assignment(db, teacher, assignment_id)
    rows = (await db.execute(
        select(Submission, Student.name)
        .join(Student, Student.id == Submission.student_id)
        .where(Submission.assignment_id == assignment_id)
        .order_by(Student.name, Submission.id)
    )).all()
    return [
        SubmissionListItem(id=s.id, student_id=s.student_id, student_name=name,
                           total_score=s.total_score, needs_review_count=s.needs_review_count)
        for s, name in rows
    ]


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
HEIC_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1"}

EnqueueGradePage = Callable[..., Awaitable[None]]  # (page_id, retry=0)
RETRYABLE_FAILURES = {"model_unavailable", "internal_error"}


def grade_job_id(page_id: int, retry: int = 0) -> str:
    """A fresh id per retry: arq keeps the result of a finished job and refuses its id."""
    return f"grade:{page_id}" if retry == 0 else f"grade:{page_id}:{retry}"


async def _arq_pool(app: FastAPI):
    """One arq pool per app, created on first use; closed by the app lifespan."""
    lock = getattr(app.state, "arq_lock", None)
    if lock is None:
        lock = app.state.arq_lock = asyncio.Lock()
    async with lock:
        if getattr(app.state, "arq_pool", None) is None:
            app.state.arq_pool = await create_pool(RedisSettings.from_dsn(get_settings().REDIS_URL))
    return app.state.arq_pool


async def close_arq_pool(app: FastAPI) -> None:
    pool = getattr(app.state, "arq_pool", None)
    if pool is not None:
        app.state.arq_pool = None
        await pool.aclose()


def get_enqueuer(request: Request) -> EnqueueGradePage:
    async def enqueue_grade_page(page_id: int, retry: int = 0) -> None:
        pool = await _arq_pool(request.app)
        await pool.enqueue_job("grade_page_job", page_id, _job_id=grade_job_id(page_id, retry))

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


async def _enqueue_or_503(enqueue: EnqueueGradePage, page_id: int, retry: int = 0) -> None:
    try:
        await (enqueue(page_id, retry) if retry else enqueue(page_id))
    except Exception:
        log.exception("enqueue of page %s failed", page_id)
        raise HTTPException(status_code=503, detail="批改队列暂不可用，请稍后重试") from None


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
    await own_assignment(db, teacher, assignment_id)
    teacher_id = teacher.id  # plain locals: ORM attrs expire after a rollback
    data = await read_limited(file)
    kind = sniff_image(data)
    if kind is None:
        raise HTTPException(status_code=415, detail="only JPEG/PNG/HEIC images are accepted")
    ext, content_type = kind
    sha = hashlib.sha256(data).hexdigest()

    async def existing() -> Page | None:
        return (
            await db.execute(
                select(Page).where(Page.assignment_id == assignment_id, Page.image_sha256 == sha)
            )
        ).scalar_one_or_none()

    async def duplicate_out(page: Page) -> PageUploadOut:
        if page.status == PageStatus.failed and page.fail_reason in RETRYABLE_FAILURES:
            # Re-uploading a page that failed for a transient reason retries it.
            await lock_assignment(db, assignment_id)
            page = (await db.execute(
                select(Page).where(Page.id == page.id).execution_options(populate_existing=True)
            )).scalar_one()
            if page.status == PageStatus.failed and page.fail_reason in RETRYABLE_FAILURES:
                page.status, page.fail_reason = PageStatus.queued, None
                page.retry_count += 1
            page_id, seq, status, retry = page.id, page.seq, page.status, page.retry_count
            await db.commit()
            if status == PageStatus.queued:
                await _enqueue_or_503(enqueue, page_id, retry)
            response.status_code = 200
            return PageUploadOut(page_id=page_id, seq=seq, status=status, duplicate=True)
        # A queued duplicate may be a retry after a failed enqueue; the job id keeps it idempotent.
        if page.status == PageStatus.queued:
            await _enqueue_or_503(enqueue, page.id, page.retry_count)
        response.status_code = 200
        return PageUploadOut(page_id=page.id, seq=page.seq, status=page.status, duplicate=True)

    if (page := await existing()) is not None:
        return await duplicate_out(page)

    # Serialises uploads of this assignment until commit: seq allocation and quota check.
    await lock_assignment(db, assignment_id)
    try:
        await check_quota(db, teacher_id)
    except QuotaExceeded:
        raise HTTPException(status_code=429, detail="本月批改额度已用完") from None

    max_seq = (
        await db.execute(select(func.max(Page.seq)).where(Page.assignment_id == assignment_id))
    ).scalar_one()
    page = Page(
        assignment_id=assignment_id,
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
            return await duplicate_out(page)
        raise
    page.image_key = f"originals/{teacher_id}/{assignment_id}/{page.id}.{ext}"
    try:
        await storage.put(page.image_key, data, content_type)
        page_id, seq = page.id, page.seq
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    await _enqueue_or_503(enqueue, page_id)  # page stays queued; a re-upload retries
    response.status_code = 201
    return PageUploadOut(page_id=page_id, seq=seq, status=PageStatus.queued, duplicate=False)


@router.post("/pages/{page_id}:replace", response_model=PageUploadOut)
async def replace_page(
    page_id: int,
    file: UploadFile,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
    enqueue: EnqueueGradePage = Depends(get_enqueuer),
):
    """Retake a failed page in place: same seq, old results and files dropped, graded again."""
    assignment_id = (await db.execute(select(Page.assignment_id).where(Page.id == page_id))).scalar_one_or_none()
    if assignment_id is None:
        raise HTTPException(status_code=404, detail="page not found")
    try:
        await own_assignment(db, teacher, assignment_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="page not found") from None
    teacher_id = teacher.id  # plain local: ORM attrs expire after a rollback
    data = await read_limited(file)
    kind = sniff_image(data)
    if kind is None:
        raise HTTPException(status_code=415, detail="only JPEG/PNG/HEIC images are accepted")
    ext, content_type = kind
    sha = hashlib.sha256(data).hexdigest()

    await lock_assignment(db, assignment_id)
    page = (
        await db.execute(select(Page).where(Page.id == page_id).execution_options(populate_existing=True))
    ).scalar_one_or_none()
    if page is None:  # deleted while we waited for the lock
        await db.rollback()
        raise HTTPException(status_code=404, detail="page not found")
    if page.status != PageStatus.failed:
        await db.rollback()
        raise HTTPException(status_code=409, detail="只有失败的卷子可以重拍")
    clash = (
        await db.execute(
            select(Page.id).where(
                Page.assignment_id == assignment_id, Page.image_sha256 == sha, Page.id != page_id
            )
        )
    ).first()
    if clash is not None:
        await db.rollback()
        raise HTTPException(status_code=409, detail="这张照片已经传过了")
    # Quota-neutral: a replace adds no Page row, and the failed page was counted at its first upload.

    old_original = page.image_key
    new_key = f"originals/{teacher_id}/{assignment_id}/{page_id}.{ext}"
    try:
        old_submissions, old_crops = await clear_page_results(db, page_id)
        for sid in old_submissions - {None}:
            await recompute_submission(db, sid)
        await storage.put(new_key, data, content_type)
        page.image_key, page.image_sha256 = new_key, sha
        page.original_deleted_at = None
        page.student_id = page.recognized_name = None
        page.status, page.fail_reason = PageStatus.queued, None
        page.retry_count += 1
        seq, retry = page.seq, page.retry_count
        await db.commit()
    except IntegrityError:  # the same photo was uploaded concurrently
        await db.rollback()
        raise HTTPException(status_code=409, detail="这张照片已经传过了") from None
    except BaseException:
        await db.rollback()
        raise
    for key in {*old_crops, old_original} - {new_key}:  # best effort; the sweeper catches leftovers
        try:
            await storage.delete(key)
        except Exception:
            log.warning("could not delete old file of replaced page %s", page_id)
    await _enqueue_or_503(enqueue, page_id, retry)
    return PageUploadOut(page_id=page_id, seq=seq, status=PageStatus.queued, duplicate=False)


class AnswerKeyOut(BaseModel):
    answer_key_status: AnswerKeyStatus
    items: list[AnswerKeyItem]


class AnswerKeyConfirmIn(BaseModel):
    items: list[AnswerKeyItem]

    @model_validator(mode="after")
    def _unique_question_no(self):
        numbers = [i.question_no for i in self.items]
        if len(set(numbers)) != len(numbers):
            raise ValueError("question_no must be unique")
        return self


class AnswerKeyConfirmOut(AnswerKeyOut):
    regrade_suggested: bool


async def _load_items(db: AsyncSession, assignment_id: int) -> list[AnswerKeyItem]:
    rows = (
        await db.execute(
            select(AnswerItem).where(AnswerItem.assignment_id == assignment_id).order_by(AnswerItem.id)
        )
    ).scalars()
    return [
        AnswerKeyItem(
            question_no=r.question_no,
            answer=r.answer,
            max_score=r.max_score,
            is_subjective=r.is_subjective,
        )
        for r in rows
    ]


async def _replace_items(
    db: AsyncSession, assignment: Assignment, items: list[AnswerKeyItem], status: AnswerKeyStatus
) -> None:
    await db.execute(delete(AnswerItem).where(AnswerItem.assignment_id == assignment.id))
    db.add_all(
        AnswerItem(assignment_id=assignment.id, **item.model_dump()) for item in items
    )
    assignment.answer_key_status = status


@router.get("/assignments/{assignment_id}/answer-key", response_model=AnswerKeyOut)
async def get_answer_key(
    assignment_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    assignment = await own_assignment(db, teacher, assignment_id)
    return AnswerKeyOut(
        answer_key_status=assignment.answer_key_status, items=await _load_items(db, assignment_id)
    )


@router.post("/assignments/{assignment_id}/answer-key", response_model=AnswerKeyOut)
async def extract_key(
    assignment_id: int,
    file: UploadFile,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    model: VisionModel = Depends(get_answer_key_model),
):
    assignment = await own_assignment(db, teacher, assignment_id)
    data = await read_limited(file)
    if sniff_image(data) is None:
        raise HTTPException(status_code=415, detail="only JPEG/PNG/HEIC images are accepted")
    try:
        items = await extract_answer_key(db, model, teacher.id, data)
    except HTTPException:
        await db.commit()  # keep the usage rows of calls that did return
        raise
    await _replace_items(db, assignment, items, AnswerKeyStatus.pending)
    await db.commit()
    return AnswerKeyOut(answer_key_status=AnswerKeyStatus.pending, items=items)


@router.put("/assignments/{assignment_id}/answer-key", response_model=AnswerKeyConfirmOut)
async def confirm_answer_key(
    assignment_id: int,
    body: AnswerKeyConfirmIn,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    assignment = await own_assignment(db, teacher, assignment_id)
    done_pages = (
        await db.execute(
            select(func.count())
            .select_from(Page)
            .where(Page.assignment_id == assignment_id, Page.status == PageStatus.done)
        )
    ).scalar_one()
    await _replace_items(db, assignment, body.items, AnswerKeyStatus.confirmed)
    await db.commit()
    return AnswerKeyConfirmOut(
        answer_key_status=AnswerKeyStatus.confirmed, items=body.items, regrade_suggested=done_pages > 0
    )
