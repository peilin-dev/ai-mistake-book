from datetime import timedelta

import pytest
import pytest_asyncio

from app.models import Assignment, KnowledgePoint, Student, Subject, Submission
from tests.conftest import make_result, utcnow


@pytest_asyncio.fixture
async def lisi(db, my_class) -> Student:
    s = Student(class_id=my_class.id, name="李四")
    db.add(s)
    await db.commit()
    return s


@pytest_asyncio.fixture
async def two_students(db, storage, my_assignment, roster_zhangsan, lisi, make_done_page):
    """张三: q1 right, q2 wrong ('9'); 李四: q1 right, q2 wrong ('9'), q3 subjective half."""
    kp = KnowledgePoint(subject=Subject.math, grade_min=1, grade_max=6, code="kp-add", name="加法")
    db.add(kp)
    await db.flush()
    ids = {}
    for seq, stu in ((1, roster_zhangsan), (2, lisi)):
        page = await make_done_page(seq, stu.id, stu.name)
        sub = Submission(assignment_id=my_assignment.id, student_id=stu.id)
        db.add(sub)
        await db.flush()
        key = f"crops/t/{page.id}-2.jpg"
        await storage.put(key, b"x", "image/jpeg")
        rows = [make_result(page.id, sub.id, "1"),
                make_result(page.id, sub.id, "2", is_correct=False, score=0, max_score=4, student_answer="9",
                            crop_key=key, knowledge_point_id=kp.id)]
        if stu is lisi:
            rows.append(make_result(page.id, sub.id, "3", is_correct=False, score=2, max_score=4,
                                    is_subjective=True))
        db.add_all(rows)
        ids[stu.name] = sub.id
    await db.commit()
    return ids


async def test_analytics_overview(auth_client, my_assignment, two_students):
    r = await auth_client.get(f"/api/assignments/{my_assignment.id}/analytics")
    assert r.status_code == 200
    body = r.json()
    assert "students" not in body
    assert body["counted_students"] == 2 and body["roster_size"] == 2
    assert body["average_score"] == pytest.approx((2 + 4) / 2)
    assert body["questions"][0]["question_no"] == "2" and body["questions"][0]["wrong_count"] == 2
    assert body["weak_points"][0] == {"name": "加法", "wrong_count": 2}


async def test_question_detail_groups_and_crops(auth_client, my_assignment, two_students):
    r = await auth_client.get(f"/api/assignments/{my_assignment.id}/analytics/questions/2")
    assert r.status_code == 200
    body = r.json()
    assert body["question_no"] == "2" and body["knowledge_point"] == "加法"
    assert body["is_subjective"] is False
    assert (body["wrong_count"], body["student_count"], body["answered_count"]) == (2, 2, 2)
    assert body["score_buckets"] == []
    assert len(body["groups"]) == 1 and body["groups"][0]["answer"] == "9" and body["groups"][0]["count"] == 2
    assert len(body["crops"]) == 2
    assert {c["student_name"] for c in body["crops"]} == {"张三", "李四"}
    assert all(c["crop_url"].startswith("/api/files/") for c in body["crops"])
    assert {c["submission_id"] for c in body["crops"]} == set(two_students.values())


async def test_subjective_question_detail_has_buckets(auth_client, my_assignment, two_students):
    r = await auth_client.get(f"/api/assignments/{my_assignment.id}/analytics/questions/3")
    assert r.status_code == 200
    body = r.json()
    assert body["is_subjective"] is True and body["groups"] == []
    assert body["score_buckets"] == [{"label": "满分", "count": 0}, {"label": "一半及以上", "count": 1},
                                     {"label": "一半以下", "count": 0}]


async def test_unknown_question_404(auth_client, my_assignment, two_students):
    r = await auth_client.get(f"/api/assignments/{my_assignment.id}/analytics/questions/99")
    assert r.status_code == 404


async def test_history_same_class_same_subject_latest_five(db, auth_client, my_class, roster_zhangsan,
                                                           make_done_page, my_assignment):
    now = utcnow()
    made = []
    for i in range(7):  # oldest first
        a = Assignment(class_id=my_class.id, subject=Subject.math, title=f"m{i}")
        db.add(a)
        await db.flush()
        a.created_at = now - timedelta(days=10 - i)
        made.append(a)
    english = Assignment(class_id=my_class.id, subject=Subject.english, title="en")
    db.add(english)
    await db.flush()
    english.created_at = now - timedelta(days=1)
    made.append(english)
    await db.commit()

    from app.models import Page, PageStatus
    subs = {}
    for n, a in enumerate(made):
        page = Page(assignment_id=a.id, seq=1, image_key="k", image_sha256=f"h{n}", status=PageStatus.done,
                    student_id=roster_zhangsan.id)
        db.add(page)
        sub = Submission(assignment_id=a.id, student_id=roster_zhangsan.id)
        db.add(sub)
        await db.flush()
        db.add(make_result(page.id, sub.id, "1", score=n % 4, max_score=4, is_correct=False))
        subs[a.title] = sub.id
    await db.commit()

    r = await auth_client.get(f"/api/submissions/{subs['m6']}/history")
    assert r.status_code == 200
    body = r.json()
    assert [h["title"] for h in body] == ["m6", "m5", "m4", "m3", "m2"]
    assert body[0] == {"assignment_id": made[6].id, "title": "m6", "created_at": body[0]["created_at"],
                       "score": 2.0, "max_score": 4.0, "ratio": 0.5}
    assert body[0]["created_at"]


async def test_history_skips_assignments_without_results(db, auth_client, my_class, my_assignment,
                                                         roster_zhangsan, graded_submission):
    other = Assignment(class_id=my_class.id, subject=Subject.math, title="nothing graded")
    db.add(other)
    await db.flush()
    db.add(Submission(assignment_id=other.id, student_id=roster_zhangsan.id))
    await db.commit()
    r = await auth_client.get(f"/api/submissions/{graded_submission.id}/history")
    assert [h["assignment_id"] for h in r.json()] == [my_assignment.id]
    assert r.json()[0]["score"] == 2 and r.json()[0]["max_score"] == 6


async def test_other_teacher_gets_404(client_for, make_teacher, my_assignment, two_students):
    other = client_for(await make_teacher())
    sub_id = next(iter(two_students.values()))
    for url in (f"/api/assignments/{my_assignment.id}/analytics",
                f"/api/assignments/{my_assignment.id}/analytics/questions/2",
                f"/api/submissions/{sub_id}/history"):
        assert (await other.get(url)).status_code == 404
    mine_missing = await other.get("/api/submissions/999999/history")
    assert mine_missing.status_code == 404


async def test_question_detail_headcount_includes_rows_without_max_score(db, auth_client, my_assignment,
                                                                         two_students):
    from sqlalchemy import update
    from app.models import QuestionResult
    # 李四's q2 loses its max_score: still in the headcount, not in the accuracy denominator
    await db.execute(update(QuestionResult)
                     .where(QuestionResult.submission_id == two_students["李四"], QuestionResult.question_no == "2")
                     .values(max_score=None))
    await db.commit()
    body = (await auth_client.get(f"/api/assignments/{my_assignment.id}/analytics/questions/2")).json()
    assert (body["wrong_count"], body["student_count"], body["answered_count"]) == (2, 2, 1)
    overview = (await auth_client.get(f"/api/assignments/{my_assignment.id}/analytics")).json()
    q2 = next(q for q in overview["questions"] if q["question_no"] == "2")
    assert (q2["wrong_count"], q2["student_count"], q2["answered_count"]) == (2, 2, 1)
