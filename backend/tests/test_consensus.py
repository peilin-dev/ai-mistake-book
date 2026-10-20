"""No-answer-key review by class majority (M3 Task 4, option B)."""
import pytest_asyncio
from sqlalchemy import select

from app.ai.fake import FakeModel
from app.grading.consensus import majority, normalize_answer, refresh_answer_consensus
from app.grading.pipeline import grade_page
from app.models import QuestionResult, Student, Submission
from tests.conftest import graded, make_result, q

NAMES = ["张三", "李四", "王五"]


def test_majority():
    assert majority(["62.8", "62.8", "157"]) == "62.8"
    assert majority(["a", "b"]) is None and majority([]) is None
    assert majority(["x"]) == "x"


def test_normalize_answer():
    assert normalize_answer(" ６２.８ dm³ ") == normalize_answer("62.8dm³")
    assert normalize_answer("A B\tc") == "abc"
    assert normalize_answer(None) == ""


async def results_of(db, page) -> list[QuestionResult]:
    page_id = page.id
    db.expire_all()
    stmt = select(QuestionResult).where(QuestionResult.page_id == page_id).order_by(QuestionResult.question_no)
    return list((await db.execute(stmt)).scalars())


@pytest_asyncio.fixture
async def results_for_q(db):
    async def _get(no: str) -> list[QuestionResult]:
        db.expire_all()
        stmt = select(QuestionResult).where(QuestionResult.question_no == no).order_by(QuestionResult.id)
        return list((await db.execute(stmt)).scalars())

    return _get


@pytest_asyncio.fixture
async def page_maker(db, my_class, make_page):
    """Factory: one uploaded page per answer for question "3", each with its own roster student.

    Question "1" is on every page too; its AI answer is "7" on the first page and "8" after.
    Returns [(page_id, model)] in seq order; grade them with grade_all.
    """

    async def _make(answers: list[str]) -> list[tuple[int, FakeModel]]:
        names = NAMES[:len(answers)]
        db.add_all([Student(class_id=my_class.id, name=n) for n in names])
        await db.commit()
        out = []
        for i, (name, ans) in enumerate(zip(names, answers)):
            page = await make_page(i + 1)
            model = FakeModel([graded(student_name=name, questions=[
                q(no="1", correct_answer="7" if i == 0 else "8"),
                q(no="3", correct_answer=ans, max_score=4, score=4)])])
            out.append((page.id, model))
        return out

    return _make


async def grade_all(db, storage, pages) -> None:
    for page_id, model in pages:
        await grade_page(db, storage, model, page_id)


@pytest_asyncio.fixture
async def three_pages_same_q(page_maker):
    return await page_maker(["62.8", "62.8", "157"])


@pytest_asyncio.fixture
async def two_pages_conflicting(page_maker):
    return await page_maker(["62.8", "157"])


async def test_minority_answer_flagged(db, storage, three_pages_same_q, results_for_q):
    await grade_all(db, storage, three_pages_same_q)
    rows = await results_for_q("3")
    flagged = {r.correct_answer: r.needs_review for r in rows}
    assert flagged == {"62.8": False, "157": True}
    assert {r.correct_answer: r.answer_mismatch for r in rows} == {"62.8": False, "157": True}


async def test_tie_flags_all(db, storage, two_pages_conflicting, results_for_q):
    await grade_all(db, storage, two_pages_conflicting)
    rows = await results_for_q("3")
    assert len(rows) == 2
    assert all(r.needs_review and r.answer_mismatch for r in rows)
    subs = (await db.execute(select(Submission).execution_options(populate_existing=True))).scalars().all()
    # q1 ("7" vs "8") and q3 are both ties on each paper
    assert sorted(s.needs_review_count for s in subs) == [2, 2]


async def test_earlier_page_flips_back_when_majority_forms(db, storage, page_maker, results_for_q):
    pages = await page_maker(["62.8", "157", "６２.８ "])
    await grade_all(db, storage, pages[:2])
    assert all(r.needs_review for r in await results_for_q("3"))
    await grade_all(db, storage, pages[2:])
    rows = await results_for_q("3")
    assert [r.needs_review for r in rows] == [False, True, False]
    first_sub = (await db.execute(select(Submission).where(Submission.id == rows[0].submission_id)
                                  .execution_options(populate_existing=True))).scalar_one()
    assert first_sub.needs_review_count == 1  # q1 "7" is now the minority against "8", "8"


async def test_single_page_not_flagged(db, storage, uploaded_page, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[q(no="1"), q(no="2", correct_answer="12")])])
    await grade_page(db, storage, model, uploaded_page.id)
    rows = await results_of(db, uploaded_page)
    assert len(rows) == 2
    assert all(not r.needs_review and not r.answer_mismatch for r in rows)


async def test_answer_key_present_ignores_consensus(db, storage, confirmed_key_q1_q2, two_pages_conflicting,
                                                    results_for_q):
    await grade_all(db, storage, two_pages_conflicting)
    rows = await results_for_q("1")
    assert len(rows) == 2
    assert all(r.answer_verified and not r.answer_mismatch and not r.needs_review for r in rows)
    assert all(r.needs_review for r in await results_for_q("3"))  # q3 has no key: tie


# --- refresh_answer_consensus directly ---

async def test_refresh_skips_reviewed_and_derives_student_status(
        db, settings, my_assignment, my_class, roster_zhangsan, make_done_page):
    lisi = Student(class_id=my_class.id, name="李四")
    db.add(lisi)
    await db.commit()
    exact = await make_done_page(1, roster_zhangsan.id, " 张 三")
    cont = await make_done_page(2, roster_zhangsan.id, None)
    fuzzy = await make_done_page(3, lisi.id, "李小四")
    nobody = await make_done_page(4, None, "某某")
    reviewed = await make_done_page(5, lisi.id, "李四")
    sub = Submission(assignment_id=my_assignment.id, student_id=roster_zhangsan.id)
    db.add(sub)
    await db.flush()
    common = dict(answer_verified=False, needs_review=True, answer_mismatch=True)
    db.add_all([
        make_result(exact.id, sub.id, "3", correct_answer="5", **common),
        make_result(cont.id, sub.id, "3", correct_answer="5", **common),
        make_result(fuzzy.id, None, "3", correct_answer="5", **common),
        make_result(nobody.id, None, "3", correct_answer="5", **common),
        make_result(reviewed.id, None, "3", correct_answer="9", answer_verified=False,
                    needs_review=False, reviewed=True),
        make_result(exact.id, sub.id, "4", correct_answer="x", **common),  # other question: untouched
    ])
    await db.commit()

    touched = await refresh_answer_consensus(db, my_assignment.id, {"3"}, settings)
    await db.commit()
    assert touched == {sub.id}
    rows = {(r.page_id, r.question_no): r for r in (await db.execute(
        select(QuestionResult).execution_options(populate_existing=True))).scalars()}
    assert not rows[(exact.id, "3")].answer_mismatch and not rows[(exact.id, "3")].needs_review
    assert not rows[(cont.id, "3")].needs_review
    assert not rows[(fuzzy.id, "3")].answer_mismatch and rows[(fuzzy.id, "3")].needs_review
    assert rows[(nobody.id, "3")].needs_review
    r = rows[(reviewed.id, "3")]
    assert (r.reviewed, r.needs_review, r.answer_mismatch) == (True, False, False)
    assert rows[(exact.id, "4")].answer_mismatch and rows[(exact.id, "4")].needs_review


async def test_refresh_ignores_pages_not_done(db, settings, my_assignment, roster_zhangsan, make_done_page):
    done = await make_done_page(1, roster_zhangsan.id, "张三")
    other = await make_done_page(2, None, None)
    other.status = "processing"
    db.add_all([make_result(done.id, None, "3", correct_answer="5", answer_verified=False),
                make_result(other.id, None, "3", correct_answer="6", answer_verified=False)])
    await db.commit()
    await refresh_answer_consensus(db, my_assignment.id, {"3"}, settings)
    await db.commit()
    r = (await db.execute(select(QuestionResult).where(QuestionResult.page_id == done.id)
                          .execution_options(populate_existing=True))).scalar_one()
    assert r.answer_mismatch is False and r.needs_review is False  # alone among done pages
