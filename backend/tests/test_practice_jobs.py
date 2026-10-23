import asyncio
import json
import re

from sqlalchemy import select

from app.ai.base import ModelCallError, ModelResult
from app.models import KnowledgePoint, PracticeItem, PracticePaper, Student, Subject, Submission, UsageRecord
from app.practice.jobs import FAILED_TEXT, run_paper, run_replace
from app.practice.rules import CONCURRENCY, REPLACE_CANDIDATES
from tests.conftest import make_result

WRONG = dict(is_correct=False, score=0, max_score=2)


class RoutedModel:
    """Test double answering by prompt content (calls may run concurrently, so order is not fixed)."""

    provider = "fake"

    def __init__(self, fn, delay: float = 0) -> None:
        self.fn = fn
        self.delay = delay
        self.prompts: list[str] = []
        self.inflight = 0
        self.max_inflight = 0

    async def complete_json(self, prompt: str, images: list[bytes]) -> ModelResult:
        self.prompts.append(prompt)
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            await asyncio.sleep(self.delay)
            out = self.fn(prompt)
            if isinstance(out, Exception):
                raise out
            return ModelResult(out, 0, 0, "fake", "fake")
        finally:
            self.inflight -= 1


def source_of(prompt: str) -> str:
    """'源题N' named in a generation prompt."""
    return re.search(r"原题：(源题\d+)", prompt).group(1)


def count_of(prompt: str) -> int:
    return int(re.search(r"请出 (\d+) 道题", prompt).group(1))


def calls_for(model: RoutedModel, src: str) -> int:
    return sum(1 for p in model.prompts if f"原题：{src}\n" in p)


def generator(bad: dict[str, int] | None = None, fail: dict[str, int] | None = None):
    """Each call returns `count` calc items '<src>变式<letter>' answering 10 (letters, so no two stems
    share their numbers and look like near-duplicates).

    bad[src] = how many items of each call are marked 坏 (the verifier rejects them);
    fail[src] = how many first calls for that source raise ModelCallError.
    """
    bad, fail = dict(bad or {}), dict(fail or {})
    seq: dict[str, int] = {}

    def fn(prompt: str):
        src = source_of(prompt)
        if fail.get(src, 0) > 0:
            fail[src] -= 1
            return ModelCallError("down")
        items = []
        for i in range(count_of(prompt)):
            seq[src] = seq.get(src, 0) + 1
            mark = "坏" if i < bad.get(src, 0) else ""
            items.append({"kind": "calc", "stem": f"{src}变式{'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[seq[src] - 1]}{mark}", "options": None, "answer": "10"})
        return {"objective": True, "items": items}

    return fn


def verifier(prompt: str):
    stem = re.search(r"题目：(.*)", prompt).group(1)
    return {"answer": "99" if "坏" in stem else "10"}


async def build_sources(db, assignment, n_sources: int = 3, n_students: int = 2):
    """Every student gets questions 1..n wrong; question k has text '源题k' (answer 7, so the variants'
    answer 10 differs from it). Returns (students, subs, kp)."""
    kp = KnowledgePoint(subject=Subject.math, grade_min=1, grade_max=6, code=f"kp-{assignment.id}", name="面积")
    db.add(kp)
    await db.flush()
    students, subs = [], []
    for i in range(n_students):
        stu = Student(class_id=assignment.class_id, name=f"王小明{i}")
        db.add(stu)
        await db.flush()
        students.append(stu)
    from app.models import Page, PageStatus
    for i, stu in enumerate(students):
        page = Page(assignment_id=assignment.id, seq=500 + i, image_key=f"k{assignment.id}-{i}",
                    image_sha256=f"bs{assignment.id}-{i}", status=PageStatus.done, student_id=stu.id)
        db.add(page)
        await db.flush()
        sub = Submission(assignment_id=assignment.id, student_id=stu.id, total_score=0)
        db.add(sub)
        await db.flush()
        for k in range(1, n_sources + 1):
            db.add(make_result(page.id, sub.id, str(k), question_text=f"源题{k}", correct_answer="7",
                               knowledge_point_id=kp.id, **WRONG))
        subs.append(sub)
    await db.commit()
    return students, subs, kp


async def new_paper(db, assignment, student_id: int | None = None) -> PracticePaper:
    p = PracticePaper(assignment_id=assignment.id, student_id=student_id, student_key=student_id or 0,
                      status="queued", sources_total=0, sources_done=0)
    db.add(p)
    await db.commit()
    return p


async def items_of(db, paper_id: int) -> list[PracticeItem]:
    return list((await db.execute(
        select(PracticeItem).where(PracticeItem.paper_id == paper_id).order_by(PracticeItem.position)
    )).scalars())


async def test_run_paper_keeps_only_verified_and_marks_partial(db, my_assignment):
    _, _, kp = await build_sources(db, my_assignment)
    paper = await new_paper(db, my_assignment)
    # 源题2: one of two drafts fails verification on both attempts -> only 1 kept.
    gen = RoutedModel(generator(bad={"源题2": 1}))
    ver = RoutedModel(verifier)
    await run_paper(db, gen, ver, paper.id)

    await db.refresh(paper)
    assert (paper.status, paper.partial, paper.error) == ("done", True, None)
    assert (paper.sources_total, paper.sources_done) == (3, 3)
    assert paper.generated_at is not None
    items = await items_of(db, paper.id)
    assert [i.position for i in items] == [1, 2, 3, 4, 5]
    assert [i.source_no for i in items] == ["1", "1", "2", "3", "3"]
    assert all("坏" not in i.stem for i in items)
    assert all(i.knowledge_point_id == kp.id and i.kind == "calc" and i.answer == "10" for i in items)
    assert all(i.options is None and i.replacing is False for i in items)
    assert len({i.stem for i in items}) == 5


async def test_run_paper_full_paper_is_not_partial(db, my_assignment):
    await build_sources(db, my_assignment, n_sources=2)
    paper = await new_paper(db, my_assignment)
    await run_paper(db, RoutedModel(generator()), RoutedModel(verifier), paper.id)
    await db.refresh(paper)
    assert (paper.status, paper.partial) == ("done", False)
    assert len(await items_of(db, paper.id)) == 4


async def test_run_paper_retries_source_once(db, my_assignment):
    await build_sources(db, my_assignment, n_sources=3)
    paper = await new_paper(db, my_assignment)
    # 源题1: first call fails, retry succeeds. 源题2: both drafts bad every time -> exactly 2 calls, 0 kept.
    # 源题3: one bad draft first time; the retry asks for just the 1 missing question.
    gen = RoutedModel(generator(fail={"源题1": 1}, bad={"源题2": 2, "源题3": 0}))
    calls_3 = []
    inner = gen.fn

    def fn(prompt):
        if source_of(prompt) == "源题3":
            calls_3.append(count_of(prompt))
            if len(calls_3) == 1:
                return {"objective": True, "items": [
                    {"kind": "calc", "stem": "源题3变式A坏", "options": None, "answer": "10"},
                    {"kind": "calc", "stem": "源题3变式B", "options": None, "answer": "10"}]}
        return inner(prompt)

    gen.fn = fn
    await run_paper(db, gen, RoutedModel(verifier), paper.id)

    assert calls_for(gen, "源题1") == 2
    assert calls_for(gen, "源题2") == 2
    assert calls_3 == [2, 1]
    retry_prompt = [p for p in gen.prompts if "原题：源题3\n" in p][1]
    assert "源题3变式B" in retry_prompt  # the kept stem is passed as "do not repeat"
    items = await items_of(db, paper.id)
    assert [i.source_no for i in items] == ["1", "1", "3", "3"]
    await db.refresh(paper)
    assert (paper.status, paper.partial) == ("done", True)


async def test_run_paper_zero_items_fails_with_message(db, my_assignment):
    await build_sources(db, my_assignment, n_sources=2)
    paper = await new_paper(db, my_assignment)
    await run_paper(db, RoutedModel(generator()), RoutedModel(lambda p: ModelCallError("down")), paper.id)
    await db.refresh(paper)
    assert (paper.status, paper.error) == ("failed", FAILED_TEXT)
    assert paper.generated_at is not None
    assert await items_of(db, paper.id) == []


async def test_run_paper_without_sources_fails(db, my_assignment):
    paper = await new_paper(db, my_assignment)
    await run_paper(db, RoutedModel(generator()), RoutedModel(verifier), paper.id)
    await db.refresh(paper)
    assert (paper.status, paper.error, paper.sources_total) == ("failed", FAILED_TEXT, 0)


async def test_run_paper_progress_counts(db, my_assignment, monkeypatch):
    await build_sources(db, my_assignment, n_sources=5)
    paper = await new_paper(db, my_assignment)
    seen: list[tuple[str, int, int]] = []
    real_commit = db.commit

    async def spy_commit():
        seen.append((paper.status, paper.sources_done, paper.sources_total))
        await real_commit()

    monkeypatch.setattr(db, "commit", spy_commit)
    gen = RoutedModel(generator(), delay=0.05)
    ver = RoutedModel(verifier, delay=0.05)
    await run_paper(db, gen, ver, paper.id)

    running = [s for s in seen if s[0] == "running"]
    assert [d for _, d, _ in running if d] == [1, 2, 3, 4, 5]  # one commit per finished source, in order
    assert all(t == 5 for _, d, t in running if d)
    assert seen[-1] == ("done", 5, 5)
    assert 2 <= gen.max_inflight <= CONCURRENCY  # sources run concurrently, capped by CONCURRENCY
    usage = (await db.execute(select(UsageRecord.purpose))).scalars().all()
    assert usage.count("practice_generate") == len(gen.prompts) == 5
    assert usage.count("practice_verify") == len(ver.prompts) == 10


async def test_run_paper_student_scope_uses_student_sources(db, my_assignment):
    students, subs, _ = await build_sources(db, my_assignment, n_sources=2)
    paper = await new_paper(db, my_assignment, student_id=students[0].id)
    gen = RoutedModel(generator())
    await run_paper(db, gen, RoutedModel(verifier), paper.id)
    await db.refresh(paper)
    assert (paper.status, paper.sources_total) == ("done", 2)
    assert all("王小明" not in p for p in gen.prompts)  # no student names in prompts


async def _done_paper(db, my_assignment):
    await build_sources(db, my_assignment, n_sources=2)
    paper = await new_paper(db, my_assignment)
    await run_paper(db, RoutedModel(generator()), RoutedModel(verifier), paper.id)
    return paper, await items_of(db, paper.id)


async def test_replace_swaps_only_when_verified(db, my_assignment):
    paper, items = await _done_paper(db, my_assignment)
    target = items[0]
    others = [i.stem for i in items]
    old_stem = target.stem

    # Verified: swapped, and the prompt lists every stem already on the paper.
    target.replacing = True
    await db.commit()
    gen = RoutedModel(lambda p: {"objective": True, "items": [
        {"kind": "choice", "stem": "新题", "options": ["8", "10"], "answer": "B"}]})
    assert await run_replace(db, gen, RoutedModel(lambda p: {"answer": "B"}), target.id) is True
    assert all(s in gen.prompts[0] for s in others)
    assert count_of(gen.prompts[0]) == REPLACE_CANDIDATES
    assert f"被替换的题：{old_stem}（答案：10）" in gen.prompts[0] and "原题正确答案：7" in gen.prompts[0]
    await db.refresh(target)
    await db.refresh(paper)
    assert (target.stem, target.kind, json.loads(target.options), target.answer) == ("新题", "choice", ["8", "10"], "B")
    assert (target.replacing, target.position, target.source_no) == (False, 1, "1")
    assert paper.last_replace_failed_item is None

    # Not verified: original kept, failure remembered.
    target.replacing = True
    await db.commit()
    gen2 = RoutedModel(lambda p: {"objective": True, "items": [
        {"kind": "calc", "stem": "另一题", "options": None, "answer": "5"}]})
    assert await run_replace(db, gen2, RoutedModel(lambda p: {"answer": "6"}), target.id) is False
    await db.refresh(target)
    await db.refresh(paper)
    assert (target.stem, target.replacing) == ("新题", False)
    assert paper.last_replace_failed_item == target.id

    # A duplicate of a stem already on the paper is never used.
    dup = RoutedModel(lambda p: {"objective": True, "items": [
        {"kind": "calc", "stem": items[1].stem, "options": None, "answer": "10"}]})
    ver = RoutedModel(verifier)
    assert await run_replace(db, dup, ver, target.id) is False
    assert ver.prompts == []

    # A later success clears the failure marker.
    ok = RoutedModel(lambda p: {"objective": True, "items": [
        {"kind": "calc", "stem": "第三题", "options": None, "answer": "10"}]})
    assert await run_replace(db, ok, RoutedModel(verifier), target.id) is True
    await db.refresh(paper)
    assert paper.last_replace_failed_item is None


async def test_jobs_mark_failure_when_something_crashes(db, settings, my_assignment):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import make_engine
    from app.practice.jobs import practice_paper_job, practice_replace_job

    paper, items = await _done_paper(db, my_assignment)
    paper_id, item_id = paper.id, items[0].id
    items[0].replacing = True
    await db.commit()
    engine = make_engine(settings.DATABASE_URL)
    ctx = {"sessionmaker": async_sessionmaker(engine, expire_on_commit=False),
           "practice_generate_model": RoutedModel(lambda p: RuntimeError("boom")),
           "practice_verify_model": RoutedModel(verifier)}
    try:
        await practice_replace_job(ctx, item_id)  # generate_drafts lets non-model errors escape
        paper.status = "running"
        await db.commit()
        ctx["practice_generate_model"] = None  # misconfigured worker
        await practice_paper_job(ctx, paper_id)
    finally:
        await engine.dispose()
    await db.rollback()
    db.expire_all()
    p = await db.get(PracticePaper, paper_id)
    it = await db.get(PracticeItem, item_id)
    assert (p.status, p.error, p.last_replace_failed_item) == ("failed", FAILED_TEXT, item_id)
    assert it.replacing is False

# --- fix round 1 ---

async def test_paper_job_commit_failure_stops_all_session_use(db, settings, my_assignment):
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import make_engine
    from app.practice.jobs import practice_paper_job

    await build_sources(db, my_assignment, n_sources=5)
    paper_id = (await new_paper(db, my_assignment)).id
    engine = make_engine(settings.DATABASE_URL)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    calls: list[str] = []
    state = {"commits": 0, "failed_at": None, "first": None}

    def factory():
        s = sm()
        if state["first"] is None:  # instrument the job's working session only
            state["first"] = s
            real_commit, real_add_all, real_execute = s.commit, s.add_all, s.execute

            async def commit():
                state["commits"] += 1
                calls.append("commit")
                if state["commits"] == 3:  # claim, sources_total, then the first progress commit fails
                    state["failed_at"] = len(calls)
                    raise OperationalError("COMMIT", {}, Exception(2013, "Lost connection"))
                await real_commit()

            def add_all(rows):
                calls.append("add_all")
                real_add_all(rows)

            async def execute(*a, **k):
                calls.append("execute")
                return await real_execute(*a, **k)

            s.commit, s.add_all, s.execute = commit, add_all, execute
        return s

    gen = RoutedModel(generator(), delay=0.05)
    ctx = {"sessionmaker": factory, "practice_generate_model": gen,
           "practice_verify_model": RoutedModel(verifier, delay=0.05)}
    try:
        await practice_paper_job(ctx, paper_id)
    finally:
        await engine.dispose()
    assert state["failed_at"] is not None
    assert calls[state["failed_at"]:] == []  # no sibling touched the session after the failure
    assert len(gen.prompts) <= 5  # one generate call per source at most: nothing retried after the failure
    await db.rollback()
    db.expire_all()
    p = await db.get(PracticePaper, paper_id)
    assert (p.status, p.error) == ("failed", FAILED_TEXT)


async def test_run_paper_only_runs_a_queued_paper(db, my_assignment):
    await build_sources(db, my_assignment, n_sources=1)
    paper = await new_paper(db, my_assignment)
    for status in ("failed", "done", "running"):
        paper.status, paper.error = status, "x"
        await db.commit()
        gen = RoutedModel(generator())
        await run_paper(db, gen, RoutedModel(verifier), paper.id)
        await db.refresh(paper)
        assert (paper.status, paper.error, gen.prompts) == (status, "x", [])


async def test_paper_job_cancelled_marks_failed(db, settings, my_assignment):
    import pytest
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import make_engine
    from app.practice.jobs import practice_paper_job, practice_replace_job

    paper, items = await _done_paper(db, my_assignment)
    paper_id, item_id = paper.id, items[0].id
    items[0].replacing = True
    await db.commit()
    engine = make_engine(settings.DATABASE_URL)
    ctx = {"sessionmaker": async_sessionmaker(engine, expire_on_commit=False),
           "practice_generate_model": RoutedModel(generator(), delay=5),
           "practice_verify_model": RoutedModel(verifier)}
    try:
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):  # what arq's job timeout does
            await asyncio.wait_for(practice_replace_job(ctx, item_id), 0.3)
        paper.status = "queued"
        await db.commit()
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await asyncio.wait_for(practice_paper_job(ctx, paper_id), 0.3)
    finally:
        await engine.dispose()
    await db.rollback()
    db.expire_all()
    p = await db.get(PracticePaper, paper_id)
    it = await db.get(PracticeItem, item_id)
    assert (p.status, p.error) == ("failed", FAILED_TEXT)
    assert (it.replacing, p.last_replace_failed_item) == (False, item_id)

# --- final review fixes ---

def fixed(items_per_call: list[list[tuple[str, str]]]):
    """A generator returning the given (stem, answer) calc items, one list per call."""
    calls = iter(items_per_call)

    def fn(prompt: str):
        return {"objective": True, "items": [
            {"kind": "calc", "stem": st, "options": None, "answer": ans} for st, ans in next(calls)]}
    return fn


async def _done_paper_with(db, my_assignment, stems: list[str]):
    paper, items = await _done_paper(db, my_assignment)
    for it, st in zip(items, stems):
        it.stem, it.answer = st, "1"  # replacement candidates answer 10: a different answer
    await db.commit()
    return paper, items


async def test_replace_skips_duplicate_and_swapped_candidates(db, my_assignment):
    paper, items = await _done_paper_with(db, my_assignment, ["6 × 7 =", "3 × 5 ="])
    target = items[0]
    target.replacing = True
    await db.commit()
    from datetime import timedelta

    from tests.conftest import utcnow
    target.updated_at = before = utcnow() - timedelta(hours=1)
    await db.commit()
    # The first candidate swaps the replaced item's numbers, the second repeats another item.
    gen = RoutedModel(fixed([[("7 × 6 =", "10"), ("5×3=", "10"), ("8 × 9 =", "10")]]))
    ver = RoutedModel(verifier)
    assert await run_replace(db, gen, ver, target.id) is True
    await db.refresh(target)
    assert (target.stem, target.replacing) == ("8 × 9 =", False)
    assert len(gen.prompts) == 1 and len(ver.prompts) == 1  # duplicates are never verified
    assert target.updated_at > before  # the heartbeat keeps a live replace from looking stale


async def test_replace_retries_once_avoiding_dropped_candidates(db, my_assignment):
    paper, items = await _done_paper_with(db, my_assignment, ["6 × 7 =", "3 × 5 ="])
    target = items[0]
    # First batch: only duplicates or wrong answers; the retry is told about all of them.
    gen = RoutedModel(fixed([[("7×6=", "10"), ("4 × 4 =坏", "10")], [("2 × 9 =", "10")]]))
    assert await run_replace(db, gen, RoutedModel(verifier), target.id) is True
    assert len(gen.prompts) == 2
    assert "7×6=" in gen.prompts[1] and "4 × 4 =坏" in gen.prompts[1]
    await db.refresh(target)
    assert target.stem == "2 × 9 ="

    # Both batches unusable: the original stays and the failure is remembered.
    gen = RoutedModel(fixed([[("9 × 2 =", "10")], [("2×9=", "10")]]))
    assert await run_replace(db, gen, RoutedModel(verifier), target.id) is False
    await db.refresh(target)
    await db.refresh(paper)
    assert (target.stem, paper.last_replace_failed_item) == ("2 × 9 =", target.id)


async def test_concurrent_replaces_never_write_the_same_question(db, settings, my_assignment):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import make_engine

    paper, items = await _done_paper_with(db, my_assignment, ["6 × 7 =", "3 × 5 ="])
    a, b, paper_id = items[0].id, items[1].id, paper.id
    engine = make_engine(settings.DATABASE_URL)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    # Both read the paper before either writes (the delay), and both come up with the same question.
    gen = RoutedModel(lambda p: {"objective": True, "items": [
        {"kind": "calc", "stem": "9 × 9 =", "options": None, "answer": "10"}]}, delay=0.2)
    ver = RoutedModel(verifier, delay=0.1)
    try:
        async with sm() as s1, sm() as s2:
            results = await asyncio.gather(run_replace(s1, gen, ver, a), run_replace(s2, gen, ver, b))
    finally:
        await engine.dispose()
    assert sorted(results) == [False, True]
    db.expire_all()
    stems = [i.stem for i in await items_of(db, paper_id)]
    assert stems.count("9 × 9 =") == 1
    loser = b if results[0] else a
    p = await db.get(PracticePaper, paper_id)
    assert p.last_replace_failed_item == loser


async def test_run_paper_drops_near_duplicates_across_sources(db, my_assignment):
    await build_sources(db, my_assignment, n_sources=2)
    paper = await new_paper(db, my_assignment)

    def fn(prompt):
        if source_of(prompt) == "源题1":
            return {"objective": True, "items": [
                {"kind": "calc", "stem": "0.7 × 0.4 =", "options": None, "answer": "10"},
                {"kind": "calc", "stem": "0.4 × 0.7 =", "options": None, "answer": "10"}]}
        return {"objective": True, "items": [
            {"kind": "calc", "stem": "0.4×0.7=", "options": None, "answer": "10"},
            {"kind": "calc", "stem": "1.2 × 3 =", "options": None, "answer": "10"}]}

    await run_paper(db, RoutedModel(fn), RoutedModel(verifier), paper.id)
    stems = [i.stem for i in await items_of(db, paper.id)]
    assert sorted(stems) == ["0.7 × 0.4 =", "1.2 × 3 ="]


async def test_run_paper_retry_refreshes_updated_at(db, my_assignment, monkeypatch):
    await build_sources(db, my_assignment, n_sources=1)
    paper = await new_paper(db, my_assignment)
    seen: list[tuple[str, int]] = []
    real_commit = db.commit

    async def spy_commit():
        seen.append((paper.status, paper.sources_done))
        await real_commit()

    monkeypatch.setattr(db, "commit", spy_commit)
    await run_paper(db, RoutedModel(generator(bad={"源题1": 1})), RoutedModel(verifier), paper.id)
    # claim, sources_total, the heartbeat before the retry, the progress commit, the final write.
    assert seen[1:] == [("running", 0), ("running", 0), ("running", 1), ("done", 1)]
    usage = (await db.execute(select(UsageRecord.purpose))).scalars().all()
    assert usage.count("practice_generate") == 2


async def test_run_paper_clears_a_stale_replace_failure_marker(db, my_assignment):
    paper, items = await _done_paper(db, my_assignment)
    paper.status, paper.last_replace_failed_item = "queued", items[0].id
    await db.commit()
    await run_paper(db, RoutedModel(generator()), RoutedModel(verifier), paper.id)
    await db.refresh(paper)
    assert (paper.status, paper.last_replace_failed_item) == ("done", None)
    assert len(await items_of(db, paper.id)) == 4  # the previous sheet was replaced, not appended to

async def test_variants_reusing_the_answer_are_dropped(db, my_assignment):
    await build_sources(db, my_assignment, n_sources=1)
    paper = await new_paper(db, my_assignment)
    gen = RoutedModel(fixed([[("3 × 9 =", "27"), ("14 ÷ 2 =", "7")], [("2 × 8 =", "16")]]))
    ver = RoutedModel(lambda p: {"answer": {"3 × 9 =": "27", "2 × 8 =": "16"}.get(
        re.search(r"题目：(.*)", p).group(1), "?")})
    await run_paper(db, gen, ver, paper.id)
    # '14 ÷ 2 = 7' repeats the source's answer 7: never verified, the retry fills the gap.
    assert [i.stem for i in await items_of(db, paper.id)] == ["3 × 9 =", "2 × 8 ="]
    assert len(ver.prompts) == 2


async def test_replacement_reusing_the_replaced_answer_is_dropped(db, my_assignment):
    paper, items = await _done_paper_with(db, my_assignment, ["6 × 7 =", "3 × 5 ="])
    gen = RoutedModel(fixed([[("1 × 1 =", "1"), ("2 × 5 =", "10")]]))
    assert await run_replace(db, gen, RoutedModel(verifier), items[0].id) is True
    await db.refresh(items[0])
    assert items[0].stem == "2 × 5 ="
