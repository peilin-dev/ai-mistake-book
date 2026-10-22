import asyncio
import io

import pytest
from arq import Retry
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.base import ModelCallError, ModelOutputError
from app.ai.fake import FakeModel
from app.grading.crop import crop, prepare_image
from app.grading.pipeline import grade_page
from app.grading.prompts import build_grading_prompt
from app.db import make_engine
from app.jobs.worker import WorkerSettings, grade_page_job
from app.models import KnowledgePoint, Page, QuestionResult, Student, Submission, Subject, UsageRecord
from tests.conftest import graded, q


async def _reset(db) -> None:
    """See other sessions' commits: end this session's snapshot and drop cached objects."""
    await db.rollback()
    db.expire_all()


async def _results(db) -> list[QuestionResult]:
    stmt = select(QuestionResult).order_by(QuestionResult.question_no)
    return list((await db.execute(stmt)).scalars().all())


# --- brief tests ---

async def test_grades_page_and_creates_submission(db, storage, uploaded_page, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[
        q(no="1", is_correct=True, score=2, max_score=2, confidence=0.95),
        q(no="2", is_correct=False, score=0, max_score=4, confidence=0.9)])])
    await grade_page(db, storage, model, uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "done" and page.student_id == roster_zhangsan.id
    sub = (await db.execute(select(Submission))).scalar_one()
    assert sub.total_score == 2
    results = await _results(db)
    assert results[0].crop_key is None and results[1].crop_key is not None
    assert all(r.answer_verified is False and not r.needs_review for r in results)  # 无答案卷，单张不比较
    assert sub.needs_review_count == 0
    assert all(r.submission_id == sub.id and r.page_id == page.id for r in results)


async def test_confirmed_answer_key_marks_verified(db, storage, uploaded_page, confirmed_key_q1_q2, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[q(no="1", confidence=0.95)])])
    await grade_page(db, storage, model, uploaded_page.id)
    r = (await db.execute(select(QuestionResult))).scalar_one()
    assert r.answer_verified is True and r.needs_review is False


async def test_second_page_without_name_joins_previous_student(db, storage, two_uploaded_pages, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[q(no="1")]),
                       graded(student_name=None, questions=[q(no="5")])])
    await grade_page(db, storage, model, two_uploaded_pages[0].id)
    await grade_page(db, storage, model, two_uploaded_pages[1].id)
    assert (await db.execute(select(func.count(Submission.id)))).scalar() == 1
    sub = (await db.execute(select(Submission))).scalar_one()
    assert sub.total_score == 4  # both pages summed into one submission
    page2 = await db.get(Page, two_uploaded_pages[1].id)
    assert page2.student_id == roster_zhangsan.id


async def test_nameless_page_repeating_question_numbers_goes_to_review(db, storage, two_uploaded_pages,
                                                                       roster_zhangsan):
    # Same question numbers as the previous page: another student's paper, not this one's back page.
    model = FakeModel([graded(student_name="张三", questions=[q(no="1"), q(no="2")]),
                       graded(student_name=None, questions=[q(no="2"), q(no="3")])])
    await grade_page(db, storage, model, two_uploaded_pages[0].id)
    await grade_page(db, storage, model, two_uploaded_pages[1].id)
    page2 = await db.get(Page, two_uploaded_pages[1].id)
    assert page2.status == "done" and page2.student_id is None
    rows = (await db.execute(select(QuestionResult).where(QuestionResult.page_id == page2.id))).scalars().all()
    assert all(r.submission_id is None and r.needs_review for r in rows)
    sub = (await db.execute(select(Submission))).scalar_one()
    assert sub.total_score == 4  # page 1 only


async def test_late_nameless_page_repeating_question_numbers_is_not_attached(db, storage, two_uploaded_pages,
                                                                             roster_zhangsan):
    # Page 2 finishes first (nothing to continue yet); page 1 then must not pull it in.
    model = FakeModel([graded(student_name=None, questions=[q(no="1")]),
                       graded(student_name="张三", questions=[q(no="1"), q(no="2")])])
    await grade_page(db, storage, model, two_uploaded_pages[1].id)
    await grade_page(db, storage, model, two_uploaded_pages[0].id)
    page2 = await db.get(Page, two_uploaded_pages[1].id)
    await db.refresh(page2)
    assert page2.student_id is None
    sub = (await db.execute(select(Submission))).scalar_one()
    assert sub.total_score == 4


async def test_unreadable_page_fails(db, storage, uploaded_page):
    await grade_page(db, storage, FakeModel([graded(student_name=None, questions=[])]), uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "failed" and page.fail_reason == "unreadable"
    assert (await db.execute(select(func.count(UsageRecord.id)))).scalar() == 1


async def test_invalid_output_retries_then_fails(db, storage, uploaded_page):
    model = FakeModel([{"oops": 1}, ModelOutputError("bad")])
    await grade_page(db, storage, model, uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "failed" and page.fail_reason == "model_output_invalid"
    assert len(model.prompts) == 2


async def test_usage_recorded(db, storage, uploaded_page, roster_zhangsan):
    await grade_page(db, storage, FakeModel([graded(student_name="张三", questions=[q(no="1")])]), uploaded_page.id)
    assert (await db.execute(select(func.count(UsageRecord.id)))).scalar() == 1
    usage = (await db.execute(select(UsageRecord))).scalar_one()
    assert usage.purpose == "grading"


# --- additional pipeline behaviour ---

async def test_invalid_then_valid_output_succeeds(db, storage, uploaded_page, roster_zhangsan):
    model = FakeModel([{"oops": 1}, graded(student_name="张三", questions=[q(no="1")])])
    await grade_page(db, storage, model, uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "done" and len(model.prompts) == 2
    assert (await db.execute(select(func.count(UsageRecord.id)))).scalar() == 2


async def test_model_call_error_requeues_and_reraises(db, storage, uploaded_page):
    with pytest.raises(ModelCallError):
        await grade_page(db, storage, FakeModel([ModelCallError("503")]), uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "queued"


async def test_unexpected_error_marks_internal_error(db, storage, uploaded_page):
    await storage.delete(uploaded_page.image_key)
    with pytest.raises(FileNotFoundError):
        await grade_page(db, storage, FakeModel([]), uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "failed" and page.fail_reason == "internal_error"


async def test_regrading_same_page_does_not_duplicate(db, storage, uploaded_page, roster_zhangsan):
    response = graded(student_name="张三", questions=[q(no="1"), q(no="2", is_correct=False, score=0)])
    model = FakeModel([response, response])
    await grade_page(db, storage, model, uploaded_page.id)
    await grade_page(db, storage, model, uploaded_page.id)
    assert len(await _results(db)) == 2
    sub = (await db.execute(select(Submission))).scalar_one()
    assert sub.total_score == 2 and sub.needs_review_count == 0


async def test_answer_key_overrides_answer_and_clips_score(db, storage, uploaded_page, confirmed_key_q1_q2,
                                                           roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[
        q(no="1", correct_answer="8", score=4, max_score=4),
        q(no="9", correct_answer="自解", score=3, max_score=3)])])
    await grade_page(db, storage, model, uploaded_page.id)
    r1, r9 = await _results(db)
    assert (r1.correct_answer, r1.max_score, r1.score, r1.answer_verified) == ("7", 2, 2, True)
    assert (r9.correct_answer, r9.max_score, r9.score, r9.answer_verified) == ("自解", 3, 3, False)
    assert r9.needs_review is False and r1.needs_review is False  # unverified alone is not reviewed


async def test_is_correct_comes_from_model_even_with_key(db, storage, uploaded_page, confirmed_key_q1_q2,
                                                         roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[q(no="2", is_correct=False, score=0, max_score=4)])])
    await grade_page(db, storage, model, uploaded_page.id)
    r = (await db.execute(select(QuestionResult))).scalar_one()
    assert r.is_correct is False and r.correct_answer == "12" and r.crop_key is not None


async def test_low_confidence_needs_review(db, storage, uploaded_page, confirmed_key_q1_q2, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[q(no="1", confidence=0.5)])])
    await grade_page(db, storage, model, uploaded_page.id)
    r = (await db.execute(select(QuestionResult))).scalar_one()
    assert r.needs_review is True and r.reviewed is False
    assert r.model_is_correct is None and r.model_score is None


async def test_fuzzy_match_marks_all_questions_for_review(db, storage, uploaded_page, confirmed_key_q1_q2,
                                                          roster_zhangsan):
    model = FakeModel([graded(student_name="张三丰", questions=[q(no="1"), q(no="2", max_score=4, score=4)])])
    await grade_page(db, storage, model, uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.student_id == roster_zhangsan.id
    assert all(r.needs_review for r in await _results(db))


async def test_unmatched_page_keeps_results_without_submission(db, storage, uploaded_page, roster_zhangsan):
    model = FakeModel([graded(student_name="王五", questions=[q(no="1")])])
    await grade_page(db, storage, model, uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "done" and page.student_id is None
    r = (await db.execute(select(QuestionResult))).scalar_one()
    assert r.submission_id is None and r.page_id == page.id and r.needs_review
    assert (await db.execute(select(func.count(Submission.id)))).scalar() == 0


async def test_continuation_requires_previous_page_done(db, storage, two_uploaded_pages, roster_zhangsan):
    first = two_uploaded_pages[0]
    first.student_id = roster_zhangsan.id  # matched but not done yet
    await db.commit()
    await grade_page(db, storage, FakeModel([graded(student_name=None, questions=[q(no="5")])]),
                     two_uploaded_pages[1].id)
    page2 = await db.get(Page, two_uploaded_pages[1].id)
    assert page2.student_id is None


async def test_knowledge_point_outside_candidates_is_dropped(db, storage, uploaded_page, roster_zhangsan):
    ok = KnowledgePoint(subject=Subject.math, grade_min=5, grade_max=5, code="m5", name="圆柱体积")
    other = KnowledgePoint(subject=Subject.math, grade_min=9, grade_max=9, code="m9", name="二次函数")
    db.add_all([ok, other])
    await db.commit()
    model = FakeModel([graded(student_name="张三", questions=[
        q(no="1", knowledge_point_id=ok.id), q(no="2", knowledge_point_id=other.id)])])
    await grade_page(db, storage, model, uploaded_page.id)
    r1, r2 = await _results(db)
    assert r1.knowledge_point_id == ok.id and r2.knowledge_point_id is None
    assert f"{ok.id}: 圆柱体积" in model.prompts[0] and "二次函数" not in model.prompts[0]


async def test_crop_key_and_content(db, storage, uploaded_page, roster_zhangsan, teacher, my_assignment):
    model = FakeModel([graded(student_name="张三", questions=[
        q(no="1", is_correct=False, score=0, bbox=[0.0, 0.5, 0.5, 1.0])])])
    await grade_page(db, storage, model, uploaded_page.id)
    r = (await db.execute(select(QuestionResult))).scalar_one()
    assert r.crop_key == f"crops/{teacher.id}/{my_assignment.id}/{r.id}.jpg"
    with Image.open(io.BytesIO(await storage.get(r.crop_key))) as img:
        assert img.format == "JPEG" and img.size == (300, 400)


# --- worker job ---

@pytest.fixture
async def job_ctx(settings, storage):
    engine = make_engine(settings.DATABASE_URL)
    ctx = {"sessionmaker": async_sessionmaker(engine, expire_on_commit=False), "storage": storage}
    yield ctx
    await engine.dispose()


async def test_job_retries_on_model_call_error(db, job_ctx, uploaded_page):
    page_id = uploaded_page.id
    job_ctx.update(model=FakeModel([ModelCallError("503")]), job_try=1)
    with pytest.raises(Retry):
        await grade_page_job(job_ctx, page_id)
    await _reset(db)
    assert (await db.get(Page, page_id)).status == "queued"


async def test_job_final_try_marks_model_unavailable(db, job_ctx, uploaded_page):
    page_id = uploaded_page.id
    job_ctx.update(model=FakeModel([ModelCallError("503")]), job_try=WorkerSettings.max_tries)
    await grade_page_job(job_ctx, page_id)
    await _reset(db)
    page = await db.get(Page, page_id)
    assert page.status == "failed" and page.fail_reason == "model_unavailable"


async def test_job_grades_page(db, job_ctx, uploaded_page, roster_zhangsan):
    page_id = uploaded_page.id
    job_ctx.update(model=FakeModel([graded(student_name="张三", questions=[q(no="1")])]), job_try=1)
    await grade_page_job(job_ctx, page_id)
    await _reset(db)
    assert (await db.get(Page, page_id)).status == "done"


def test_worker_settings(settings):
    assert WorkerSettings.functions == [grade_page_job]
    assert WorkerSettings.max_tries == 3
    assert WorkerSettings.job_timeout == 2 * 120 + 60 == 2 * settings.MODEL_TIMEOUT_S + 60


# --- enqueuer ---

class FakeArqPool:
    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, args, kwargs))


async def test_upload_enqueues_arq_job(app, auth_client, my_assignment, jpeg_bytes, storage):
    pool = FakeArqPool()
    app.state.arq_pool = pool
    r = await auth_client.post(f"/api/assignments/{my_assignment.id}/pages",
                               files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    page_id = r.json()["page_id"]
    assert pool.jobs == [("grade_page_job", (page_id,), {"_job_id": f"grade:{page_id}"})]


# --- image helpers and prompt ---

def _jpeg(size, exif=None) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, (200, 10, 10))
    if exif is not None:
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def test_prepare_image_downsizes_long_side():
    out = prepare_image(_jpeg((4000, 3000)))
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "JPEG" and img.size == (2048, 1536)


def test_prepare_image_never_upscales_and_converts_png():
    buf = io.BytesIO()
    Image.new("RGBA", (300, 200)).save(buf, format="PNG")
    with Image.open(io.BytesIO(prepare_image(buf.getvalue()))) as img:
        assert img.format == "JPEG" and img.mode == "RGB" and img.size == (300, 200)


def test_prepare_image_honours_exif_orientation():
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° CW to display
    with Image.open(io.BytesIO(prepare_image(_jpeg((400, 200), exif=exif)))) as img:
        assert img.size == (200, 400)


def test_crop_uses_relative_bbox():
    with Image.open(io.BytesIO(crop(_jpeg((1000, 500)), (0.1, 0.2, 0.5, 0.6)))) as img:
        assert img.format == "JPEG" and img.size == (400, 200)


def test_crop_never_empty():
    with Image.open(io.BytesIO(crop(_jpeg((100, 100)), (0.999, 0.999, 1.0, 1.0)))) as img:
        assert img.size[0] >= 1 and img.size[1] >= 1


def test_prompt_lists_answers_and_candidates():
    from app.models import AnswerItem
    kp = KnowledgePoint(id=42, subject=Subject.math, grade_min=5, grade_max=5, code="x", name="分数加法")
    item = AnswerItem(question_no="3", answer="62.8dm³", max_score=4)
    prompt = build_grading_prompt("math", 5, [item], [kp])
    assert "数学" in prompt and "5" in prompt
    assert "62.8dm³" in prompt and "42: 分数加法" in prompt
    assert "student_name" in prompt and "bbox" in prompt and "knowledge_point_id" in prompt
    assert "null" in prompt


def test_prompt_without_answer_key_asks_model_to_solve():
    prompt = build_grading_prompt("math", 5, [], [])
    assert "标准答案" in prompt and "62.8dm³" not in prompt


# --- concurrency and late continuation (READ COMMITTED, as in the worker) ---

@pytest.fixture
async def rc_sessionmaker(settings):
    engine = make_engine(settings.DATABASE_URL)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class GatedModel(FakeModel):
    """FakeModel whose calls wait at a barrier, so model phases of several pages overlap."""

    def __init__(self, responses, barrier: asyncio.Barrier) -> None:
        super().__init__(responses)
        self._barrier = barrier

    async def complete_json(self, prompt, images):
        await asyncio.wait_for(self._barrier.wait(), 10)
        return await super().complete_json(prompt, images)


async def _grade_in_new_session(rc_sessionmaker, storage, model, page_id):
    async with rc_sessionmaker() as s:
        await grade_page(s, storage, model, page_id)


async def test_concurrent_pages_of_same_student_share_one_submission(
        db, rc_sessionmaker, storage, two_uploaded_pages, roster_zhangsan):
    ids, student_id = [p.id for p in two_uploaded_pages], roster_zhangsan.id
    barrier = asyncio.Barrier(2)
    await asyncio.gather(*(
        _grade_in_new_session(rc_sessionmaker, storage,
                              GatedModel([graded(student_name="张三", questions=[q(no=no)])], barrier), pid)
        for pid, no in zip(ids, ("1", "2"))))
    await _reset(db)
    sub = (await db.execute(select(Submission))).scalar_one()
    assert sub.student_id == student_id and sub.total_score == 4 and sub.needs_review_count == 0
    pages = [await db.get(Page, pid) for pid in ids]
    assert [p.status for p in pages] == ["done", "done"]
    assert all(r.submission_id == sub.id for r in await _results(db))


async def test_nameless_page_finished_first_joins_previous_page_later(
        db, rc_sessionmaker, storage, two_uploaded_pages, confirmed_key_q1_q2, roster_zhangsan):
    p1, p2 = two_uploaded_pages
    ids, student_id = (p1.id, p2.id), roster_zhangsan.id
    p1.status = "processing"  # page 1 still being graded
    await db.commit()

    await _grade_in_new_session(rc_sessionmaker, storage, FakeModel([graded(
        student_name="  ", questions=[q(no="2", score=4, max_score=4)])]), ids[1])
    await _reset(db)
    page2 = await db.get(Page, ids[1])
    assert page2.status == "done" and page2.student_id is None and page2.recognized_name is None
    assert (await db.execute(select(QuestionResult))).scalar_one().needs_review is True

    await _grade_in_new_session(rc_sessionmaker, storage, FakeModel([graded(
        student_name=" 张三 ", questions=[q(no="1")])]), ids[0])
    await _reset(db)
    page1, page2 = await db.get(Page, ids[0]), await db.get(Page, ids[1])
    assert page1.recognized_name == "张三"
    assert page1.student_id == page2.student_id == student_id
    sub = (await db.execute(select(Submission))).scalar_one()
    assert sub.total_score == 6 and sub.needs_review_count == 0
    results = await _results(db)
    assert len(results) == 2
    assert all(r.submission_id == sub.id and r.needs_review is False for r in results)


async def test_late_continuation_stops_at_first_named_page(
        db, rc_sessionmaker, storage, make_page, roster_zhangsan):
    pages = [await make_page(1), await make_page(2), await make_page(3), await make_page(4)]
    ids, student_id = [p.id for p in pages], roster_zhangsan.id
    pages[0].status = "processing"
    await db.commit()
    # Back pages carry other question numbers than the front page (repeats would go to review).
    for pid, name, no in ((ids[1], None, "5"), (ids[2], "王五", "1"), (ids[3], None, "5")):
        await _grade_in_new_session(rc_sessionmaker, storage, FakeModel([graded(
            student_name=name, questions=[q(no=no)])]), pid)
    await _grade_in_new_session(rc_sessionmaker, storage, FakeModel([graded(
        student_name="张三", questions=[q(no="1")])]), ids[0])
    await _reset(db)
    students = [(await db.get(Page, pid)).student_id for pid in ids]
    assert students == [student_id, student_id, None, None]
    sub = (await db.execute(select(Submission))).scalar_one()
    assert sub.total_score == 4

# --- final review fix 5/8: vanished pages and done pages ---

class DeletingModel(FakeModel):
    """Deletes the page (as a class delete would) while the model call is in flight."""

    def __init__(self, responses, db, page_id):
        super().__init__(responses)
        self._db, self._page_id = db, page_id

    async def complete_json(self, prompt, images):
        from sqlalchemy import delete

        await self._db.execute(delete(Page).where(Page.id == self._page_id))
        await self._db.commit()
        return await super().complete_json(prompt, images)


async def test_page_deleted_during_grading_returns_quietly(db, rc_sessionmaker, storage, uploaded_page):
    page_id = uploaded_page.id
    model = DeletingModel([graded(student_name=None, questions=[q(no="1")])], db, page_id)
    await _grade_in_new_session(rc_sessionmaker, storage, model, page_id)  # no exception
    await _reset(db)
    assert await db.get(Page, page_id) is None
    assert (await db.execute(select(func.count(QuestionResult.id)))).scalar() == 0


async def test_job_on_vanished_page_after_model_error_returns_quietly(db, job_ctx, uploaded_page):
    page_id = uploaded_page.id
    job_ctx.update(model=DeletingModel([ModelCallError("503")], db, page_id), job_try=3)
    assert await grade_page_job(job_ctx, page_id) is None
    job_ctx.update(model=FakeModel([]), job_try=1)
    assert await grade_page_job(job_ctx, page_id) is None  # page already gone


async def test_done_page_is_not_regraded(db, storage, uploaded_page, roster_zhangsan):
    page_id = uploaded_page.id
    await grade_page(db, storage, FakeModel([graded(student_name="张三", questions=[q(no="1")])]), page_id)
    r = (await db.execute(select(QuestionResult))).scalar_one()
    r.score, r.reviewed = 1, True  # a teacher correction
    await db.commit()
    model = FakeModel([graded(student_name="张三", questions=[q(no="9")])])
    await grade_page(db, storage, model, page_id)  # duplicate delivery of the job
    assert model.prompts == []
    await _reset(db)
    r = (await db.execute(select(QuestionResult))).scalar_one()
    assert (r.question_no, r.score, r.reviewed) == ("1", 1, True)
    assert (await db.execute(select(func.count(UsageRecord.id)))).scalar() == 1


async def test_is_subjective_from_model_without_key(db, storage, uploaded_page, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[q(no="1", is_subjective=True)])])
    await grade_page(db, storage, model, uploaded_page.id)
    assert (await db.execute(select(QuestionResult))).scalar_one().is_subjective is True


async def test_is_subjective_from_answer_key(db, storage, uploaded_page, confirmed_key_q1_q2, roster_zhangsan):
    confirmed_key_q1_q2[0].is_subjective = True
    await db.commit()
    model = FakeModel([graded(student_name="张三", questions=[q(no="1", is_subjective=False)])])
    await grade_page(db, storage, model, uploaded_page.id)
    assert (await db.execute(select(QuestionResult))).scalar_one().is_subjective is True
