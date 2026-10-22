import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.router import _own_submission
from app.assignments.access import own_assignment
from app.assignments.router import _arq_pool
from app.deps import current_teacher, get_db
from app.models import Assignment, Class_, KnowledgePoint, PracticeItem, PracticePaper, Student, Teacher
from app.practice.jobs import FAILED_TEXT, _utcnow, stale_after_queued, stale_after_running
from app.practice.sources import class_sources, student_sources

log = logging.getLogger(__name__)
router = APIRouter(tags=["practice"])

NO_CLASS_SOURCES = "这次大家做得不错，没有需要练习的题"
NO_STUDENT_SOURCES = "这位同学这次没有需要练习的题"
STILL_GENERATING = "还在出题，请稍等"
PAPER_FAILED = "这张练习纸没出成，请重新生成"
QUEUE_DOWN = "出题队列暂不可用，请稍后重试"
WORKING = ("queued", "running")

EnqueuePractice = Callable[[str, int], Awaitable[None]]  # (function name, paper_id | item_id)


def practice_job_id(function: str, obj_id: int) -> str:
    """A fresh id per request: arq refuses the id of a job whose result it still keeps."""
    prefix = "practice" if function == "practice_paper_job" else "practice-item"
    return f"{prefix}:{obj_id}:{secrets.token_hex(4)}"


def get_practice_enqueuer(request: Request) -> EnqueuePractice:
    async def enqueue(function: str, obj_id: int) -> None:
        pool = await _arq_pool(request.app)
        await pool.enqueue_job(function, obj_id, _job_id=practice_job_id(function, obj_id))

    return enqueue


class ItemOut(BaseModel):
    id: int
    position: int
    source_no: str
    knowledge_point: str | None
    kind: str
    stem: str
    options: list[str] | None
    answer: str
    replacing: bool


class PaperOut(BaseModel):
    id: int
    scope: str  # class | student
    student_name: str | None
    status: str
    partial: bool
    sources_total: int
    sources_done: int
    error: str | None
    generated_at: datetime | None
    last_replace_failed_item: int | None
    items: list[ItemOut]


async def _expire_stale(db: AsyncSession, paper: PracticePaper) -> None:
    """A job that died (worker crash, timeout, lost enqueue) must not leave the page polling forever."""
    now = _utcnow()
    changed = False
    cutoff = {"queued": stale_after_queued(), "running": stale_after_running()}.get(paper.status)
    if cutoff is not None and paper.updated_at < now - cutoff:
        paper.status, paper.error, paper.generated_at = "failed", FAILED_TEXT, now
        changed = True
    stuck = (await db.execute(select(PracticeItem).where(
        PracticeItem.paper_id == paper.id, PracticeItem.replacing.is_(True),
        PracticeItem.updated_at < now - stale_after_running(),
    ))).scalars().all()
    for item in stuck:
        item.replacing = False
        paper.last_replace_failed_item = item.id
        changed = True
    if changed:
        await db.commit()


async def _paper_out(db: AsyncSession, paper: PracticePaper) -> PaperOut:
    await _expire_stale(db, paper)
    rows = (await db.execute(
        select(PracticeItem, KnowledgePoint.name)
        .outerjoin(KnowledgePoint, KnowledgePoint.id == PracticeItem.knowledge_point_id)
        .where(PracticeItem.paper_id == paper.id)
        .order_by(PracticeItem.position)
    )).all()
    student_name = None
    if paper.student_id is not None:
        student_name = (await db.execute(
            select(Student.name).where(Student.id == paper.student_id))).scalar_one_or_none()
    return PaperOut(
        id=paper.id,
        scope="class" if paper.student_id is None else "student",
        student_name=student_name,
        status=paper.status,
        partial=paper.partial,
        sources_total=paper.sources_total,
        sources_done=paper.sources_done,
        error=paper.error,
        generated_at=paper.generated_at,
        last_replace_failed_item=paper.last_replace_failed_item,
        # While a new sheet is being made the previous one is still stored (run_paper replaces it), but
        # it is not shown: the page shows progress, and a failed enqueue brings it back.
        items=[] if paper.status in WORKING else [ItemOut(id=i.id, position=i.position, source_no=i.source_no, knowledge_point=kp, kind=i.kind,
                       stem=i.stem, options=json.loads(i.options) if i.options else None, answer=i.answer,
                       replacing=i.replacing) for i, kp in rows],
    )


async def _find_paper(db: AsyncSession, assignment_id: int, student_key: int, lock: bool = False):
    stmt = select(PracticePaper).where(PracticePaper.assignment_id == assignment_id,
                                       PracticePaper.student_key == student_key)
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


_LOCK_CONFLICTS = {1213, 1205}  # MySQL: deadlock victim, lock wait timeout


def _is_tap_conflict(exc: Exception) -> bool:
    """A simultaneous tap won the race (duplicate key) or MySQL picked us as the lock victim."""
    if isinstance(exc, IntegrityError):
        return True
    args = getattr(getattr(exc, "orig", None), "args", None) or (None,)
    return args[0] in _LOCK_CONFLICTS


_RESTORE = ("status", "partial", "error", "sources_total", "sources_done", "generated_at", "last_replace_failed_item")


async def _claim_paper(db: AsyncSession, assignment_id: int, student_id: int | None, sources_loader,
                       no_sources_text: str) -> tuple[PracticePaper, bool, dict | None]:
    """(paper, True, previous fields) after creating/resetting it to queued and committing (previous is
    None for a new paper); (paper, False, None) if one is in flight. Old items stay until run_paper."""
    key = student_id or 0
    paper = await _find_paper(db, assignment_id, key, lock=True)
    if paper is not None:
        await _expire_stale(db, paper)  # commits (releasing the lock) only when it changed something
        if paper.status in WORKING:
            await db.commit()
            return paper, False, None
    sources = await sources_loader()
    if not sources:
        await db.commit()  # nothing changed; ends the transaction and its row lock
        raise HTTPException(409, no_sources_text)
    previous = None
    if paper is None:
        paper = PracticePaper(assignment_id=assignment_id, student_id=student_id, student_key=key)
        db.add(paper)
    else:
        previous = {f: getattr(paper, f) for f in _RESTORE}
    paper.status, paper.partial, paper.error = "queued", False, None
    paper.sources_total, paper.sources_done = len(sources), 0
    paper.generated_at, paper.last_replace_failed_item = None, None
    await db.commit()
    return paper, True, previous


async def _generate(db: AsyncSession, response: Response, enqueue: EnqueuePractice, assignment_id: int,
                    student_id: int | None, sources_loader, no_sources_text: str) -> PaperOut:
    for _ in range(2):  # the losing tap retries once and then normally finds the winner's paper
        try:
            paper, created, previous = await _claim_paper(db, assignment_id, student_id, sources_loader, no_sources_text)
            break
        except (IntegrityError, OperationalError) as exc:
            if not _is_tap_conflict(exc):
                raise
            await db.rollback()
    else:
        raise HTTPException(409, STILL_GENERATING)
    if not created:
        response.status_code = 200
        return await _paper_out(db, paper)
    try:
        await enqueue("practice_paper_job", paper.id)
    except Exception:
        log.exception("enqueue of practice paper %s failed", paper.id)
        if previous is None:
            paper.status, paper.error = "failed", FAILED_TEXT
        else:  # the previous sheet (still stored) comes back as it was
            for f, v in previous.items():
                setattr(paper, f, v)
        await db.commit()
        raise HTTPException(503, QUEUE_DOWN) from None
    response.status_code = 201
    return await _paper_out(db, paper)


@router.post("/assignments/{assignment_id}/practice", response_model=PaperOut, status_code=201)
async def generate_class_practice(
    assignment_id: int,
    response: Response,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    enqueue: EnqueuePractice = Depends(get_practice_enqueuer),
):
    await own_assignment(db, teacher, assignment_id)
    return await _generate(db, response, enqueue, assignment_id, None,
                           lambda: class_sources(db, assignment_id), NO_CLASS_SOURCES)


@router.post("/submissions/{submission_id}/practice", response_model=PaperOut, status_code=201)
async def generate_student_practice(
    submission_id: int,
    response: Response,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    enqueue: EnqueuePractice = Depends(get_practice_enqueuer),
):
    sub = await _own_submission(db, teacher, submission_id)
    return await _generate(db, response, enqueue, sub.assignment_id, sub.student_id,
                           lambda: student_sources(db, submission_id), NO_STUDENT_SOURCES)


@router.get("/assignments/{assignment_id}/practice", response_model=PaperOut)
async def get_class_practice(
    assignment_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    await own_assignment(db, teacher, assignment_id)
    paper = await _find_paper(db, assignment_id, 0)
    if paper is None:
        raise HTTPException(404, "practice paper not found")
    return await _paper_out(db, paper)


@router.get("/submissions/{submission_id}/practice", response_model=PaperOut)
async def get_student_practice(
    submission_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    sub = await _own_submission(db, teacher, submission_id)
    paper = await _find_paper(db, sub.assignment_id, sub.student_id)
    if paper is None:
        raise HTTPException(404, "practice paper not found")
    return await _paper_out(db, paper)


async def _own_paper(db: AsyncSession, teacher: Teacher, paper_id: int) -> PracticePaper:
    paper = (await db.execute(
        select(PracticePaper)
        .join(Assignment, Assignment.id == PracticePaper.assignment_id)
        .join(Class_, Class_.id == Assignment.class_id)
        .where(PracticePaper.id == paper_id, Class_.teacher_id == teacher.id)
    )).scalar_one_or_none()
    if paper is None:
        raise HTTPException(404, "practice paper not found")
    return paper


@router.get("/practice/{paper_id}", response_model=PaperOut)
async def get_practice(
    paper_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    return await _paper_out(db, await _own_paper(db, teacher, paper_id))


@router.post("/practice-items/{item_id}/replace", status_code=202)
async def replace_item(
    item_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    enqueue: EnqueuePractice = Depends(get_practice_enqueuer),
):
    row = (await db.execute(
        select(PracticeItem, PracticePaper)
        .join(PracticePaper, PracticePaper.id == PracticeItem.paper_id)
        .join(Assignment, Assignment.id == PracticePaper.assignment_id)
        .join(Class_, Class_.id == Assignment.class_id)
        .where(PracticeItem.id == item_id, Class_.teacher_id == teacher.id)
    )).one_or_none()
    if row is None:
        raise HTTPException(404, "practice item not found")
    item, paper = row
    await _expire_stale(db, paper)
    if paper.status in WORKING:
        raise HTTPException(409, STILL_GENERATING)
    if paper.status == "failed":
        raise HTTPException(409, PAPER_FAILED)
    if item.replacing:
        return {"queued": True}  # a second tap while the first replacement is still running
    item.replacing = True
    await db.commit()
    try:
        await enqueue("practice_replace_job", item.id)
    except Exception:
        log.exception("enqueue of practice item %s failed", item.id)
        item.replacing = False
        await db.commit()
        raise HTTPException(503, QUEUE_DOWN) from None
    return {"queued": True}
