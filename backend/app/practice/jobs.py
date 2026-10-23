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
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update

from app.config import get_settings
from app.models import Assignment, Class_, KnowledgePoint, PracticeItem, PracticePaper, Submission
from app.practice.generate import Draft, dedupe, generate_drafts, same_answer, verify_draft
from app.practice.rules import CONCURRENCY, MAX_SOURCES, REPLACE_CANDIDATES, VARIANTS_PER_SOURCE
from app.practice.sources import Source, _usable, class_sources, student_sources

log = logging.getLogger(__name__)

FAILED_TEXT = "这次没出成题，请稍后重试"
ATTEMPTS_PER_SOURCE = 2  # first try plus one retry
REPLACE_ATTEMPTS = 2  # first batch of candidates plus one retry


def _attempt_s() -> float:
    """One attempt: a generate call, then the (concurrent) verifications of at most two calls each."""
    return 3 * get_settings().MODEL_TIMEOUT_S


def paper_job_timeout_s() -> float:
    """Worst case: waves of sources x two attempts each."""
    waves = math.ceil(MAX_SOURCES / CONCURRENCY)
    return waves * ATTEMPTS_PER_SOURCE * _attempt_s() + 60


def replace_job_timeout_s() -> float:
    return REPLACE_ATTEMPTS * _attempt_s() + 60


def stale_after_queued() -> timedelta:
    """A queued paper not picked up this long has lost its job (lost enqueue, worker gone)."""
    return timedelta(seconds=paper_job_timeout_s() + 120)


def stale_after_running() -> timedelta:
    """Running papers and replacing items commit after every attempt (progress / heartbeat), so
    one silent attempt-length is all a live job ever needs."""
    return timedelta(seconds=_attempt_s())


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


async def _variants(gen_model, verify_model, teacher_id: int, source: Source, buf: _UsageBuffer,
                    heartbeat=None) -> list[Draft]:
    """Up to VARIANTS_PER_SOURCE verified drafts; a short source is generated once more for the gap.

    `heartbeat()` runs before a retry so the paper's updated_at keeps moving (see stale_after_running).
    """
    kept: list[Draft] = []
    rejected: list[str] = []
    for attempt in range(ATTEMPTS_PER_SOURCE):
        if attempt and heartbeat is not None:
            await heartbeat()
        need = VARIANTS_PER_SOURCE - len(kept)
        kept_pairs = [(d.kind, d.stem) for d in kept]
        raw = await generate_drafts(buf, gen_model, teacher_id, source, need, [d.stem for d in kept] + rejected)
        fresh = dedupe(raw, kept_pairs)
        new_answer = [d for d in fresh if not same_answer(d, source.correct_answer)]
        drafts = new_answer[:need]
        oks = await asyncio.gather(*(verify_draft(buf, verify_model, teacher_id, d) for d in drafts))
        kept += [d for d, ok in zip(drafts, oks) if ok]
        rejected += [d.stem for d, ok in zip(drafts, oks) if not ok]
        log.info("practice source %s attempt %d: %d drafts, %d duplicate, %d same answer, %d unverified, %d kept",
                 source.question_no, attempt + 1, len(raw), len(raw) - len(fresh), len(fresh) - len(new_answer),
                 sum(1 for ok in oks if not ok), sum(1 for ok in oks if ok))
        if len(kept) >= VARIANTS_PER_SOURCE:
            break
    return kept


async def run_paper(db, gen_model, verify_model, paper_id: int) -> None:
    # Claim atomically: only a queued paper runs, so a late or duplicate job (stale retry, a job
    # enqueued before a regenerate) can neither revive a failed/done paper nor run it twice.
    claimed = await db.execute(
        update(PracticePaper).where(PracticePaper.id == paper_id, PracticePaper.status == "queued")
        .values(status="running", sources_done=0, error=None)
    )
    await db.commit()
    if claimed.rowcount != 1:
        log.info("practice paper %s is not queued; job skipped", paper_id)
        return
    paper = await db.get(PracticePaper, paper_id, populate_existing=True)
    assignment_id, student_id = paper.assignment_id, paper.student_id
    teacher_id = await _teacher_id(db, assignment_id)

    sources = await _paper_sources(db, assignment_id, student_id)
    paper.sources_total = len(sources)
    await db.commit()

    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()
    done = 0
    broken: list[BaseException] = []  # set once the session failed: nobody may touch it again

    async def heartbeat(buf: _UsageBuffer) -> None:
        async with lock:
            if broken:
                return
            try:
                db.add_all(buf.rows)
                buf.rows = []
                paper.updated_at = _utcnow()
                await db.commit()
            except Exception as exc:
                broken.append(exc)

    async def one(source: Source) -> list[Draft]:
        nonlocal done
        buf = _UsageBuffer()
        async with sem:
            if broken:
                return []
            try:
                kept = await _variants(gen_model, verify_model, teacher_id, source, buf, lambda: heartbeat(buf))
            except Exception:  # one bad source must not sink the paper
                log.exception("practice paper %s: source %s failed", paper_id, source.question_no)
                kept = []
        async with lock:
            if broken:
                return []
            try:
                db.add_all(buf.rows)
                done += 1
                paper.sources_done = done
                await db.commit()
            except Exception as exc:
                broken.append(exc)
                return []
        return kept

    # Children never raise (errors land in `broken`); a cancellation of this task cancels them all
    # and gather only returns once every child has finished.
    results = await asyncio.gather(*(one(s) for s in sources))
    if broken:
        raise broken[0]

    # Lock the row: a stale-expired run and its regenerated successor must not interleave their writes.
    paper = (await db.execute(
        select(PracticePaper).where(PracticePaper.id == paper_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one()
    await db.execute(delete(PracticeItem).where(PracticeItem.paper_id == paper_id))
    placed: list[tuple[str, str]] = []
    position = 0
    for source, kept in zip(sources, results):
        for d in dedupe(kept, placed):  # also drops (near-)identical questions across sources
            position += 1
            placed.append((d.kind, d.stem))
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
    paper.last_replace_failed_item = None  # it pointed at an item of the previous sheet
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


async def _paper_pairs(db, paper_id: int) -> list[tuple[str, str]]:
    return [(k, s) for k, s in (await db.execute(
        select(PracticeItem.kind, PracticeItem.stem).where(PracticeItem.paper_id == paper_id)
    )).all()]


async def _replacement(db, gen_model, verify_model, teacher_id: int, source: Source,
                       item: PracticeItem, paper_id: int) -> Draft | None:
    """The first candidate that repeats nothing on the paper (the replaced item included), has an answer
    other than the source's and the replaced item's, and passes verification; a second batch is asked for, told what was dropped, when the first yields none."""
    avoid: list[str] = []
    for attempt in range(REPLACE_ATTEMPTS):
        buf = _UsageBuffer()
        existing = await _paper_pairs(db, paper_id)
        raw = await generate_drafts(buf, gen_model, teacher_id, source, REPLACE_CANDIDATES,
                                    [s for _, s in existing] + avoid, replacing=(item.stem, item.answer))
        fresh = dedupe(raw, existing)
        new_answer = [d for d in fresh
                      if not same_answer(d, source.correct_answer) and not same_answer(d, item.answer)]
        oks = await asyncio.gather(*(verify_draft(buf, verify_model, teacher_id, d) for d in new_answer))
        picked = next((d for d, ok in zip(new_answer, oks) if ok), None)
        log.info("practice replace %s attempt %d: %d drafts, %d duplicate, %d same answer, %d unverified, %s",
                 item.id, attempt + 1, len(raw), len(raw) - len(fresh), len(fresh) - len(new_answer),
                 sum(1 for ok in oks if not ok),
                 "picked" if picked else "none usable")
        # Usage rows plus a heartbeat for the stale check (stale_after_running).
        db.add_all(buf.rows)
        item.updated_at = _utcnow()
        await db.commit()
        if picked is not None:
            return picked
        avoid += [d.stem for d in raw]
    return None


async def run_replace(db, gen_model, verify_model, item_id: int) -> bool:
    item = await db.get(PracticeItem, item_id)
    if item is None:
        return False  # the paper was regenerated meanwhile
    paper = await db.get(PracticePaper, item.paper_id)
    paper_id = paper.id
    picked: Draft | None = None
    if paper.status == "done":
        source = await _item_source(db, paper, item)
        if source is not None:
            teacher_id = await _teacher_id(db, paper.assignment_id)
            picked = await _replacement(db, gen_model, verify_model, teacher_id, source, item, paper_id)
    ok = False
    if picked is not None:
        # Another replace on this paper may have written the same question meanwhile: lock the paper,
        # look again, and only then write (the lock is held until finish_replace commits).
        paper = (await db.execute(
            select(PracticePaper).where(PracticePaper.id == paper_id).with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        item = await db.get(PracticeItem, item_id, populate_existing=True)
        if item is None or paper is None:
            await db.commit()
            return False
        if paper.status == "done" and dedupe([picked], await _paper_pairs(db, paper_id)):
            item.kind, item.stem, item.answer = picked.kind, picked.stem, picked.answer
            item.options = json.dumps(picked.options, ensure_ascii=False) if picked.options is not None else None
            ok = True
        else:
            log.info("practice replace %s: candidate became a duplicate or the paper changed; dropped", item_id)
    await finish_replace(db, item_id, ok)
    return ok


# ---------- arq entry points (registered in app.jobs.worker) ----------

def _models(ctx: dict):
    gen, ver = ctx.get("practice_generate_model"), ctx.get("practice_verify_model")
    if gen is None or ver is None:
        raise RuntimeError("practice models are not configured")
    return gen, ver


async def _cleanup(ctx: dict, what: str, fn, obj_id: int) -> None:
    """Best effort, in a fresh session: the job's own session may be broken or mid-cancellation."""
    try:
        async with ctx["sessionmaker"]() as db:
            await fn(db, obj_id)
    except Exception:
        log.exception("could not record the failure of practice %s %s", what, obj_id)


async def practice_paper_job(ctx: dict, paper_id: int) -> None:
    try:
        async with ctx["sessionmaker"]() as db:
            await run_paper(db, *_models(ctx), paper_id)
    except asyncio.CancelledError:  # arq job timeout: still tell the page, then let arq see it
        log.warning("practice paper %s cancelled", paper_id)
        await _cleanup(ctx, "paper", mark_paper_failed, paper_id)
        raise
    except Exception:
        log.exception("practice paper %s failed", paper_id)
        await _cleanup(ctx, "paper", mark_paper_failed, paper_id)


async def _replace_failed(db, item_id: int) -> None:
    await finish_replace(db, item_id, False)


async def practice_replace_job(ctx: dict, item_id: int) -> None:
    try:
        async with ctx["sessionmaker"]() as db:
            await run_replace(db, *_models(ctx), item_id)
    except asyncio.CancelledError:
        log.warning("practice replace %s cancelled", item_id)
        await _cleanup(ctx, "item", _replace_failed, item_id)
        raise
    except Exception:
        log.exception("practice replace %s failed", item_id)
        await _cleanup(ctx, "item", _replace_failed, item_id)
