import pytest
from sqlalchemy import select

from app.models import Page, PageStatus, QuestionResult, Submission
from tests.conftest import make_result


async def test_teacher_correction_updates_total(auth_client, graded_submission):
    qr = graded_submission.questions[0]
    r = await auth_client.patch(f"/api/question-results/{qr.id}", json={"is_correct": False, "score": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["reviewed"] is True and body["model_is_correct"] is True and body["model_score"] == 2
    sub = (await auth_client.get(f"/api/submissions/{graded_submission.id}")).json()
    assert sub["total_score"] == graded_submission.total_score - 2
    assert sub["student_name"] == "张三" and [q["question_no"] for q in sub["questions"]] == ["1", "2"]


async def test_is_correct_only_sets_score(auth_client, graded_submission):
    q1, q2 = graded_submission.questions
    r = await auth_client.patch(f"/api/question-results/{q1.id}", json={"is_correct": False})
    assert r.json()["score"] == 0
    r = await auth_client.patch(f"/api/question-results/{q2.id}", json={"is_correct": True})
    assert r.json()["score"] == 4
    sub = (await auth_client.get(f"/api/submissions/{graded_submission.id}")).json()
    assert sub["total_score"] == 4


async def test_second_modification_keeps_model_values(auth_client, graded_submission):
    qr = graded_submission.questions[0]
    await auth_client.patch(f"/api/question-results/{qr.id}", json={"is_correct": False})
    body = (await auth_client.patch(f"/api/question-results/{qr.id}", json={"score": 1})).json()
    assert body["model_is_correct"] is True and body["model_score"] == 2
    assert body["score"] == 1 and body["is_correct"] is False


async def test_invalid_corrections(auth_client, graded_submission):
    qid = graded_submission.questions[0].id
    assert (await auth_client.patch(f"/api/question-results/{qid}", json={})).status_code == 422
    assert (await auth_client.patch(f"/api/question-results/{qid}", json={"score": 3})).status_code == 422
    assert (await auth_client.patch(f"/api/question-results/{qid}", json={"score": -1})).status_code == 422


async def test_correction_clears_review_queue_and_count(auth_client, db, my_assignment, graded_submission):
    qr = graded_submission.questions[1]
    qr.needs_review = True
    sub = await db.get(Submission, graded_submission.id)
    sub.needs_review_count = 1
    await db.commit()
    review = (await auth_client.get(f"/api/assignments/{my_assignment.id}/review")).json()
    assert [q["id"] for q in review["questions"]] == [qr.id]
    await auth_client.patch(f"/api/question-results/{qr.id}", json={"score": 1})
    assert (await auth_client.get(f"/api/assignments/{my_assignment.id}/review")).json()["questions"] == []
    got = (await auth_client.get(f"/api/submissions/{graded_submission.id}")).json()
    assert got["needs_review_count"] == 0 and got["total_score"] == 3


async def test_assign_student_to_unmatched_page(auth_client, unmatched_page, roster_zhangsan):
    r = await auth_client.patch(f"/api/pages/{unmatched_page.id}", json={"student_id": roster_zhangsan.id})
    assert r.status_code == 200
    assert r.json() == {"page_id": unmatched_page.id, "student_id": roster_zhangsan.id}
    review = (await auth_client.get(f"/api/assignments/{unmatched_page.assignment_id}/review")).json()
    assert review["pages_unassigned"] == []
    assert review["questions"] == []  # confirmed student, 0.95 confidence, verified


async def test_assign_moves_results_and_fixes_both_totals(
    auth_client, db, unmatched_page, graded_submission, roster_zhangsan, my_class
):
    from app.models import Student

    lisi = Student(class_id=my_class.id, name="李四")
    db.add(lisi)
    await db.commit()
    pid, zid, gid = unmatched_page.id, roster_zhangsan.id, graded_submission.id
    first = await auth_client.patch(f"/api/pages/{pid}", json={"student_id": zid})
    assert first.status_code == 200
    zs = (await db.execute(select(Submission).where(Submission.student_id == zid))).scalars().all()
    assert len(zs) == 1 and zs[0].id == gid and zs[0].total_score == 4  # 2 + 2 + 0
    lid = lisi.id
    await auth_client.patch(f"/api/pages/{pid}", json={"student_id": lid})
    db.expire_all()
    assert (await db.get(Submission, gid)).total_score == 2
    ls = (await db.execute(select(Submission).where(Submission.student_id == lid))).scalar_one()
    assert ls.total_score == 2
    rows = (await db.execute(select(QuestionResult.submission_id).where(
        QuestionResult.page_id == pid))).scalars().all()
    assert set(rows) == {ls.id}


async def test_assign_recomputes_needs_review(auth_client, db, unmatched_page, roster_zhangsan):
    qs = (await db.execute(select(QuestionResult).where(QuestionResult.page_id == unmatched_page.id)
                           .order_by(QuestionResult.id))).scalars().all()
    qs[1].confidence = 0.5
    await db.commit()
    pid = unmatched_page.id
    await auth_client.patch(f"/api/pages/{pid}", json={"student_id": roster_zhangsan.id})
    db.expire_all()
    qs = (await db.execute(select(QuestionResult).where(QuestionResult.page_id == pid)
                           .order_by(QuestionResult.id))).scalars().all()
    assert [q.needs_review for q in qs] == [False, True]
    sub = await db.get(Submission, qs[0].submission_id)
    assert sub.needs_review_count == 1


async def test_assign_forward_resolves_following_nameless_page(
    auth_client, db, unmatched_page, roster_zhangsan, make_done_page
):
    nxt = await make_done_page(2, None, None)
    db.add(make_result(nxt.id, None, "3", needs_review=True))
    await db.commit()
    nid, zid = nxt.id, roster_zhangsan.id
    await auth_client.patch(f"/api/pages/{unmatched_page.id}", json={"student_id": zid})
    db.expire_all()
    nxt = await db.get(Page, nid)
    assert nxt.student_id == zid
    qr = (await db.execute(select(QuestionResult).where(QuestionResult.page_id == nid))).scalar_one()
    assert qr.submission_id is not None and qr.needs_review is False


async def test_reassign_moves_continuation_pages(
    auth_client, db, my_assignment, my_class, roster_zhangsan, make_done_page
):
    from app.models import Student

    lisi = Student(class_id=my_class.id, name="李四")
    db.add(lisi)
    await db.commit()
    p1 = await make_done_page(1, roster_zhangsan.id, "张小三")  # fuzzy match -> 张三
    p2 = await make_done_page(2, roster_zhangsan.id, None)  # nameless continuation
    sub_a = Submission(assignment_id=my_assignment.id, student_id=roster_zhangsan.id,
                       total_score=4, needs_review_count=1)
    db.add(sub_a)
    await db.flush()
    db.add_all([make_result(p1.id, sub_a.id, "1", needs_review=True),
                make_result(p2.id, sub_a.id, "2")])
    await db.commit()
    p1_id, p2_id, a_id, b_id = p1.id, p2.id, sub_a.id, lisi.id

    r = await auth_client.patch(f"/api/pages/{p1_id}", json={"student_id": b_id})
    assert r.status_code == 200
    db.expire_all()
    assert (await db.get(Page, p1_id)).student_id == b_id
    assert (await db.get(Page, p2_id)).student_id == b_id
    sub_b = (await db.execute(select(Submission).where(Submission.student_id == b_id))).scalar_one()
    sids = (await db.execute(select(QuestionResult.submission_id))).scalars().all()
    assert set(sids) == {sub_b.id} and len(sids) == 2
    assert sub_b.total_score == 4
    old = await db.get(Submission, a_id)
    assert old.total_score == 0 and old.needs_review_count == 0


async def test_assign_page_not_done_is_409(auth_client, db, unmatched_page, roster_zhangsan):
    unmatched_page.status = PageStatus.processing
    await db.commit()
    r = await auth_client.patch(f"/api/pages/{unmatched_page.id}", json={"student_id": roster_zhangsan.id})
    assert r.status_code == 409 and r.json()["detail"] == "页面尚未批改完成"


async def test_cannot_assign_student_from_other_class(auth_client, unmatched_page, other_class_student):
    r = await auth_client.patch(f"/api/pages/{unmatched_page.id}", json={"student_id": other_class_student.id})
    assert r.status_code == 404


async def test_review_reasons(auth_client, db, my_assignment, unmatched_page, roster_zhangsan, make_done_page):
    page2 = await make_done_page(2, roster_zhangsan.id, "张三")
    from app.models import Submission

    sub = Submission(assignment_id=my_assignment.id, student_id=roster_zhangsan.id)
    db.add(sub)
    await db.flush()
    db.add_all([
        make_result(page2.id, sub.id, "a", needs_review=True, confidence=0.5),
        make_result(page2.id, sub.id, "b", needs_review=True, answer_verified=False, answer_mismatch=True),
        make_result(page2.id, sub.id, "c", needs_review=True),
        make_result(page2.id, sub.id, "d", needs_review=False),
    ])
    await db.commit()
    review = (await auth_client.get(f"/api/assignments/{my_assignment.id}/review")).json()
    by_no = {q["question_no"]: q for q in review["questions"]}
    assert set(by_no) == {"1", "2", "a", "b", "c"}
    assert by_no["1"]["reason"] == "student_uncertain" and by_no["1"]["student_name"] is None
    assert by_no["a"]["reason"] == "low_confidence" and by_no["a"]["student_name"] == "张三"
    assert by_no["b"]["reason"] == "answer_mismatch"
    assert by_no["c"]["reason"] == "student_uncertain"
    assert [q["question_no"] for q in review["questions"]][:2] == ["1", "2"]  # page seq order
    assert review["pages_unassigned"][0]["recognized_name"] == "张小三"
    assert review["pages_unassigned"][0]["image_url"]


async def test_review_question_carries_page_for_fuzzy_fix(
    auth_client, db, my_assignment, my_class, roster_zhangsan, make_done_page, storage
):
    from datetime import datetime

    from app.models import Student

    lisi = Student(class_id=my_class.id, name="李四")
    db.add(lisi)
    page = await make_done_page(1, roster_zhangsan.id, "张小三")
    sub = Submission(assignment_id=my_assignment.id, student_id=roster_zhangsan.id)
    db.add(sub)
    await db.flush()
    db.add(make_result(page.id, sub.id, "1", needs_review=True))
    await db.commit()
    pid, key, lid = page.id, page.image_key, lisi.id

    item = (await auth_client.get(f"/api/assignments/{my_assignment.id}/review")).json()["questions"][0]
    assert item["page_id"] == pid and item["recognized_name"] == "张小三"
    assert item["image_url"] == storage.signed_url(key)
    r = await auth_client.patch(f"/api/pages/{item['page_id']}", json={"student_id": lid})
    assert r.status_code == 200 and r.json()["student_id"] == lid
    assert (await auth_client.get(f"/api/assignments/{my_assignment.id}/review")).json()["questions"] == []

    (await db.get(Page, pid)).student_id = roster_zhangsan.id
    p = await db.get(Page, pid)
    p.original_deleted_at = datetime(2026, 1, 1)
    await db.execute(QuestionResult.__table__.update().values(needs_review=True))
    await db.commit()
    item = (await auth_client.get(f"/api/assignments/{my_assignment.id}/review")).json()["questions"][0]
    assert item["image_url"] is None


async def test_image_url_null_after_original_deleted(auth_client, db, unmatched_page):
    from datetime import datetime

    unmatched_page.original_deleted_at = datetime(2026, 1, 1)
    await db.commit()
    review = (await auth_client.get(f"/api/assignments/{unmatched_page.assignment_id}/review")).json()
    assert review["pages_unassigned"][0]["image_url"] is None


async def test_crop_url_signed(auth_client, db, my_assignment, graded_submission, storage):
    qr = graded_submission.questions[1]
    qr.crop_key = "crops/x.jpg"
    qr.needs_review = True
    await db.commit()
    review = (await auth_client.get(f"/api/assignments/{my_assignment.id}/review")).json()
    assert review["questions"][0]["crop_url"] == storage.signed_url("crops/x.jpg")


async def test_foreign_resources_are_404(client_for, make_teacher, graded_submission, unmatched_page,
                                         roster_zhangsan, my_assignment):
    other = client_for(await make_teacher())
    qid = graded_submission.questions[0].id
    assert (await other.patch(f"/api/question-results/{qid}", json={"score": 1})).status_code == 404
    assert (await other.patch(f"/api/pages/{unmatched_page.id}",
                              json={"student_id": roster_zhangsan.id})).status_code == 404
    assert (await other.get(f"/api/submissions/{graded_submission.id}")).status_code == 404
    assert (await other.get(f"/api/assignments/{my_assignment.id}/review")).status_code == 404


async def test_missing_submission_404(auth_client):
    assert (await auth_client.get("/api/submissions/999999")).status_code == 404


async def test_api_engine_is_read_committed(settings):
    from sqlalchemy import text

    from app.db import get_sessionmaker

    async with get_sessionmaker()() as s:
        assert (await s.execute(text("SELECT @@transaction_isolation"))).scalar() == "READ-COMMITTED"


async def test_read_after_lock_sees_concurrent_commit(db, settings, unmatched_page):
    """A reads the page, B commits a change, A locks then re-reads: A must see B's commit."""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import make_engine
    from app.grading.pipeline import fresh_page, lock_assignment

    pid, aid = unmatched_page.id, unmatched_page.assignment_id
    await db.execute(update(Page).where(Page.id == pid).values(status=PageStatus.processing))
    await db.commit()
    # a real consistent read (establishes the InnoDB snapshot under REPEATABLE READ)
    assert (await db.execute(select(Page.status).where(Page.id == pid))).scalar() == PageStatus.processing
    engine = make_engine(settings.DATABASE_URL)
    async with async_sessionmaker(engine)() as b:
        await b.execute(update(Page).where(Page.id == pid).values(status=PageStatus.done))
        await b.commit()
    await engine.dispose()
    await lock_assignment(db, aid)
    assert (await fresh_page(db, Page.id == pid)).status == PageStatus.done


# --- M3 Task 4: no-answer-key review by class majority ---

@pytest.fixture
async def mismatch_result(db, my_assignment, roster_zhangsan, make_done_page) -> QuestionResult:
    page = await make_done_page(1, roster_zhangsan.id, "张三")
    sub = Submission(assignment_id=my_assignment.id, student_id=roster_zhangsan.id, needs_review_count=1)
    db.add(sub)
    await db.flush()
    r = make_result(page.id, sub.id, "3", answer_verified=False, answer_mismatch=True, needs_review=True)
    db.add(r)
    await db.commit()
    r.assignment_id = my_assignment.id  # convenience for the test
    return r


async def test_review_reason_answer_mismatch(auth_client, mismatch_result):
    items = (await auth_client.get(f"/api/assignments/{mismatch_result.assignment_id}/review")).json()["questions"]
    assert items[0]["reason"] == "answer_mismatch"


async def test_unverified_without_mismatch_is_not_its_own_reason(auth_client, db, mismatch_result):
    mismatch_result.answer_mismatch = False  # still needs_review: falls back to student_uncertain
    await db.commit()
    items = (await auth_client.get(f"/api/assignments/{mismatch_result.assignment_id}/review")).json()["questions"]
    assert items[0]["reason"] == "student_uncertain"


async def test_assign_keeps_answer_mismatch_flag(auth_client, db, unmatched_page, roster_zhangsan):
    qs = (await db.execute(select(QuestionResult).where(QuestionResult.page_id == unmatched_page.id)
                           .order_by(QuestionResult.id))).scalars().all()
    qs[0].answer_mismatch = True
    await db.commit()
    pid = unmatched_page.id
    await auth_client.patch(f"/api/pages/{pid}", json={"student_id": roster_zhangsan.id})
    db.expire_all()
    qs = (await db.execute(select(QuestionResult).where(QuestionResult.page_id == pid)
                           .order_by(QuestionResult.id))).scalars().all()
    assert [q.needs_review for q in qs] == [True, False]


async def test_assignment_has_answer_key_flag(auth_client, my_assignment):
    body = (await auth_client.get(f"/api/assignments/{my_assignment.id}")).json()
    assert body["has_answer_key"] is False and body["class_id"] == my_assignment.class_id


async def test_assignment_has_answer_key_when_confirmed(auth_client, my_assignment, confirmed_key_q1_q2):
    assert (await auth_client.get(f"/api/assignments/{my_assignment.id}")).json()["has_answer_key"] is True