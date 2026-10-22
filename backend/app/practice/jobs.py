"""Background practice work: generate a whole paper, or replace one question.

Session use under concurrency: sources are generated/verified concurrently (Semaphore(CONCURRENCY)),
but one AsyncSession must never be used by two coroutines at once. The concurrent model calls
therefore record usage into a per-source `_UsageBuffer` (record_usage only add()s and flush()es),
and the rows are written to the real session — together with the `sources_done` progress commit —
under an asyncio.Lock when that source finishes. All other DB work runs outside the gather.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.config import get_settings
from app.models import Assignment, Class_, KnowledgePoint, PracticeItem, PracticePaper, Submission
from app.practice.generate import Draft, dedupe, generate_drafts, verify_draft
from app.practice.rules import CONCURRENCY, VARIANTS_PER_SOURCE
from app.practice.sources import Source, _usable, class_sources, student_sources

log = logging.getLogger(__name__)

FAILED_TEXT = "这次没出成题，请稍后重试"
ATTEMPTS_PER_SOURCE = 2  # first try plus one retry


def paper_job_timeout_s() -> float:
    """Worst case: two waves of sources x two attempts x (generate + two verify calls)."""
    return 12 * get_settings().MODEL_TIMEOUT_S + 60


def replace_job_timeout_s() -> float:
    return 3 * get_settings().MODEL_TIMEOUT_S + 60


def stale_after_paper() -> timedelta:
    """A queued/running paper untouched this long has lost its job (crash, timeout, lost enqueue)."""
    return timedelta(seconds=paper_job_timeout_s() + 120)


def stale_after_replace() -> timedelta:
    return timedelta(seconds=replace_job_timeout_s() + 120)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class _UsageBuffer:
    """Stands in for the session inside concurrent model calls; see the module docstring."""

    def __init__(self) -> None:
        self.rows: list = []

    def add(self, obj) -> None:
        self.rows.append(obj)

    async def flush(self) -> None:
        pass


async def _teacher_id(db, assignment_id: int) -> int:
    return (await db.execute(
        select(Class_.teacher_id).join(Assignment, Assignment.class_id == Class_.id)
        .where(Assignment.id == assignment_id)
    )).scalar_one()


async def _paper_sources(db, assignment_id: int, student_id: int | None) -> list[Source]:
    if student_id is None:
        return await class_sources(db, assignment_id)
    sub_id = (await db.execute(
        select(Submission.id).where(Submission.assignment_id == assignment_id, Submission.student_id == student_id)
    )).scalar_one_or_none()
    return [] if sub_id is None else await student_sources(db, sub_id)


async def _variants(gen_model, verify_model, teacher_id: int, source: Source, buf: _UsageBuffer) -> list[Draft]:
    """Up to VARIANTS_PER_SOURCE verified drafts; a short source is generated once more for the gap."""
    kept: list[Draft] = []
    rejected: list[str] = []
    for _ in range(ATTEMPTS_PER_SOURCE):
        need = VARIANTS_PER_SOURCE - len(kept)
        kept_stems = [d.stem for d in kept]
        drafts = await generate_drafts(buf, gen_model, teacher_id, source, need, kept_stems + rejected)
        drafts = dedupe(drafts, kept_stems)[:need]
        oks = await asyncio.gather(*(verify_draft(buf, verify_model, teacher_id, d) for d in drafts))
        kept += [d for d, ok in zip(drafts, oks) if ok]
        rejected += [d.stem for d, ok in zip(drafts, oks) if not ok]
        if len(kept) >= VARIANTS_PER_SOURCE:
            break
    return kept


async def run_paper(db, gen_model, verify_model, paper_id: int) -> None:
    paper = await db.get(PracticePaper, paper_id)
    if paper is None:
        return
    assignment_id, student_id = paper.assignment_id, paper.student_id
    teacher_id = await _teacher_id(db, assignment_id)
    paper.status, paper.sources_done, paper.error = "running", 0, None
    await db.commit()

    sources = await _paper_sources(db, assignment_id, student_id)
    paper.sources_total = len(sources)
    await db.commit()

    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()
    done = 0

    async def one(source: Source) -> list[Draft]:
        nonlocal done
        buf = _UsageBuffer()
        async with sem:
            try:
                kept = await _variants(gen_model, verify_model, teacher_id, source, buf)
            except Exception:  # one bad source must not sink the paper
                log.exception("practice paper %s: source %s failed", paper_id, source.question_no)
                kept = []
        async with lock:
            db.add_all(buf.rows)
            done += 1
            paper.sources_done = done
            await db.commit()
        return kept

    results = await asyncio.gather(*(one(s) for s in sources))

    await db.execute(delete(PracticeItem).where(PracticeItem.paper_id == paper_id))
    stems: list[str] = []
    position = 0
    for source, kept in zip(sources, results):
        for d in dedupe(kept, stems):  # also drops near-identical questions across sources
            position += 1
            stems.append(d.stem)
            db.add(PracticeItem(
                paper_id=paper_id, position=position, source_no=source.question_no,
                knowledge_point_id=source.knowledge_point_id, kind=d.kind, stem=d.stem,
                options=json.dumps(d.options, ensure_ascii=False) if d.options is not None else None,
                answer=d.answer,
            ))
    paper.partial = position < len(sources) * VARIANTS_PER_SOURCE
    paper.status = "done" if position else "failed"
    paper.error = None if position else FAILED_TEXT
    paper.generated_at = _utcnow()
    await db.commit()


async def mark_paper_failed(db, paper_id: int) -> None:
    paper = await db.get(PracticePaper, paper_id)
    if paper is not None and paper.status in ("queued", "running"):
        paper.status, paper.error, paper.generated_at = "failed", FAILED_TEXT, _utcnow()
        await db.commit()


async def _item_source(db, paper: PracticePaper, item: PracticeItem) -> Source | None:
    """The item's source question rebuilt from current results (independent of today's ranking)."""
    assignment = await db.get(Assignment, paper.assignment_id)
    cls = await db.get(Class_, assignment.class_id)
    usable = await _usable(db, assignment)
    if item.source_no not in usable:
        return None
    text, answer = usable[item.source_no]
    kp_name = None
    if item.knowledge_point_id is not None:
        kp = await db.get(KnowledgePoint, item.knowledge_point_id)
        kp_name = kp.name if kp else None
    return Source(question_no=item.source_no, text=text, correct_answer=answer,
                  knowledge_point_id=item.knowledge_point_id, knowledge_point=kp_name, grade=cls.grade,
                  subject=assignment.subject.value, lost=None)


async def finish_replace(db, item_id: int, ok: bool) -> None:
    item = await db.get(PracticeItem, item_id)
    if item is None:
        return
    paper = await db.get(PracticePaper, item.paper_id)
    item.replacing = False
    if ok:
        if paper.last_replace_failed_item == item_id:
            paper.last_replace_failed_item = None
    else:
        paper.last_replace_failed_item = item_id
    await db.commit()


async def run_replace(db, gen_model, verify_model, item_id: int) -> bool:
    item = await db.get(PracticeItem, item_id)
    if item is None:
        return False  # the paper was regenerated meanwhile
    paper = await db.get(PracticePaper, item.paper_id)
    ok = False
    if paper.status == "done":
        source = await _item_source(db, paper, item)
        if source is not None:
            teacher_id = await _teacher_id(db, paper.assignment_id)
            stems = list((await db.execute(
                select(PracticeItem.stem).where(PracticeItem.paper_id == paper.id)
            )).scalars())
            drafts = dedupe(await generate_drafts(db, gen_model, teacher_id, source, 1, stems), stems)[:1]
            if drafts and await verify_draft(db, verify_model, teacher_id, drafts[0]):
                d = drafts[0]
                item.kind, item.stem, item.answer = d.kind, d.stem, d.answer
                item.options = json.dumps(d.options, ensure_ascii=False) if d.options is not None else None
                ok = True
    await finish_replace(db, item_id, ok)
    return ok


# ---------- arq entry points (registered in app.jobs.worker) ----------

async def practice_paper_job(ctx: dict, paper_id: int) -> None:
    async with ctx["sessionmaker"]() as db:
        try:
            gen, ver = ctx.get("practice_generate_model"), ctx.get("practice_verify_model")
            if gen is None or ver is None:
                raise RuntimeError("practice models are not configured")
            await run_paper(db, gen, ver, paper_id)
        except Exception:
            log.exception("practice paper %s failed", paper_id)
            await db.rollback()
            await mark_paper_failed(db, paper_id)


async def practice_replace_job(ctx: dict, item_id: int) -> None:
    async with ctx["sessionmaker"]() as db:
        try:
            gen, ver = ctx.get("practice_generate_model"), ctx.get("practice_verify_model")
            if gen is None or ver is None:
                raise RuntimeError("practice models are not configured")
            await run_replace(db, gen, ver, item_id)
        except Exception:
            log.exception("practice replace %s failed", item_id)
            await db.rollback()
            await finish_replace(db, item_id, False)
