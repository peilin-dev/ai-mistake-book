import pytest_asyncio
from sqlalchemy import func, select

from app.ai.base import ModelCallError
from app.analytics.notes import _cause_ref, get_analysis_model
from app.models import AiNote, Student, Submission, UsageRecord
from tests.conftest import make_result


@pytest_asyncio.fixture
async def install_analysis_model(app):
    from app.ai.fake import FakeModel

    def _install(responses: list) -> FakeModel:
        model = FakeModel(responses)
        app.dependency_overrides[get_analysis_model] = lambda: model
        return model

    return _install


@pytest_asyncio.fixture
async def add_student(db, my_class, my_assignment, make_done_page):
    """Factory: a student with a done page and q2 answered `answer` (wrong, 0/4)."""
    counter = [0]

    async def _add(name: str, answer: str, q1_ok: bool = True) -> int:
        counter[0] += 1
        stu = Student(class_id=my_class.id, name=name)
        db.add(stu)
        await db.flush()
        page = await make_done_page(counter[0], stu.id, name)
        sub = Submission(assignment_id=my_assignment.id, student_id=stu.id)
        db.add(sub)
        await db.flush()
        db.add_all([
            make_result(page.id, sub.id, "1", is_correct=q1_ok, score=2 if q1_ok else 0, max_score=2),
            make_result(page.id, sub.id, "2", question_text="3x=12, x=?", correct_answer="4",
                        is_correct=False, score=0, max_score=4, student_answer=answer),
        ])
        await db.commit()
        return sub.id

    return _add


def _url(a, no="2"):
    return f"/api/assignments/{a.id}/analytics/questions/{no}/causes"


async def test_causes_generated_once_and_cached(auth_client, my_assignment, add_student, install_analysis_model, db):
    await add_student("张三", "9")
    await add_student("李四", "9")
    fake = install_analysis_model([{"causes": [{"key": "9", "cause": "把除法算成了减法" + "啊" * 60}]}])
    r1 = await auth_client.post(_url(my_assignment))
    assert r1.status_code == 200
    causes = r1.json()["causes"]
    assert list(causes) == ["9"] and len(causes["9"]) == 40 and causes["9"].startswith("把除法算成了减法")
    r2 = await auth_client.post(_url(my_assignment))
    assert r2.json() == r1.json()
    assert len(fake.prompts) == 1
    assert "张三" not in fake.prompts[0] and "李四" not in fake.prompts[0]
    n = (await db.execute(select(func.count()).select_from(UsageRecord).where(UsageRecord.purpose == "analysis"))).scalar_one()
    assert n == 1


async def test_causes_regenerated_when_group_changes(auth_client, my_assignment, add_student, install_analysis_model, db):
    await add_student("张三", "9")
    await add_student("李四", "9")
    fake = install_analysis_model([{"causes": [{"key": "9", "cause": "甲"}]}, {"causes": [{"key": "9", "cause": "乙"}]}])
    assert (await auth_client.post(_url(my_assignment))).json()["causes"] == {"9": "甲"}
    await add_student("王五", "9")
    assert (await auth_client.post(_url(my_assignment))).json()["causes"] == {"9": "乙"}
    assert len(fake.prompts) == 2
    rows = (await db.execute(select(AiNote))).scalars().all()
    assert len(rows) == 1 and rows[0].text == "乙" and rows[0].ref == _cause_ref("2", "9") and rows[0].kind == "cause"


async def test_single_student_and_blank_groups_skipped(auth_client, my_assignment, add_student, install_analysis_model):
    await add_student("张三", "9")
    await add_student("李四", "10")
    await add_student("王五", "")
    await add_student("赵六", "")
    fake = install_analysis_model([])
    r = await auth_client.post(_url(my_assignment))
    assert r.status_code == 200 and r.json() == {"causes": {}}
    assert fake.prompts == []


async def test_cause_generation_failure_returns_groups_without_causes(
        auth_client, my_assignment, add_student, install_analysis_model):
    await add_student("张三", "9")
    await add_student("李四", "9")
    install_analysis_model([ModelCallError("boom")])
    r = await auth_client.post(_url(my_assignment))
    assert r.status_code == 200 and r.json() == {"causes": {}}


async def test_summary_cached_and_usage_recorded(auth_client, my_assignment, add_student, install_analysis_model, db):
    sub_id = await add_student("张三", "9", q1_ok=False)
    fake = install_analysis_model([{"summary": "本次作业失分较多。" + "好" * 200}])
    r1 = await auth_client.post(f"/api/submissions/{sub_id}/summary")
    assert r1.status_code == 200
    s = r1.json()["summary"]
    assert s.startswith("本次作业失分较多。") and len(s) == 120
    r2 = await auth_client.post(f"/api/submissions/{sub_id}/summary")
    assert r2.json() == r1.json() and len(fake.prompts) == 1
    assert "张三" not in fake.prompts[0]
    n = (await db.execute(select(func.count()).select_from(UsageRecord).where(UsageRecord.purpose == "analysis"))).scalar_one()
    assert n == 1


async def test_summary_failure_returns_none(auth_client, my_assignment, add_student, install_analysis_model):
    sub_id = await add_student("张三", "9")
    install_analysis_model([ModelCallError("boom")])
    r = await auth_client.post(f"/api/submissions/{sub_id}/summary")
    assert r.status_code == 200 and r.json() == {"summary": None}


async def test_notes_other_teacher_404(client_for, make_teacher, my_assignment, add_student, install_analysis_model):
    sub_id = await add_student("张三", "9")
    install_analysis_model([])
    other = client_for(await make_teacher())
    assert (await other.post(_url(my_assignment))).status_code == 404
    assert (await other.post(f"/api/submissions/{sub_id}/summary")).status_code == 404

async def test_long_answer_ref_is_bounded(auth_client, my_assignment, add_student, install_analysis_model, db):
    long = "9" * 600
    await add_student("张三", long)
    await add_student("李四", long)
    install_analysis_model([{"causes": [{"key": long, "cause": "x"}]}])
    r = await auth_client.post(_url(my_assignment))
    assert r.status_code == 200 and r.json()["causes"] == {long: "x"}
    ref = (await db.execute(select(AiNote.ref))).scalar_one()
    assert len(ref) <= 128


async def test_concurrent_duplicate_note_still_200(auth_client, my_assignment, add_student, install_analysis_model,
                                                   db, monkeypatch):
    from app.analytics import notes
    await add_student("张三", "9")
    await add_student("李四", "9")
    db.add(AiNote(assignment_id=my_assignment.id, kind="cause", ref=_cause_ref("2", "9"),
                  fingerprint="other", text="先到的"))
    await db.commit()

    async def _blind(*a, **k):
        return None  # the race: this request read before the other one wrote
    monkeypatch.setattr(notes, "_get_note", _blind)
    install_analysis_model([{"causes": [{"key": "9", "cause": "后到的"}]}])
    r = await auth_client.post(_url(my_assignment))
    assert r.status_code == 200 and r.json()["causes"] == {"9": "后到的"}


async def test_concurrent_duplicate_summary_still_200(auth_client, my_assignment, add_student,
                                                      install_analysis_model, db, monkeypatch):
    from app.analytics import notes
    sub_id = await add_student("张三", "9")
    db.add(AiNote(assignment_id=my_assignment.id, kind="summary", ref=f"submission:{sub_id}",
                  fingerprint="other", text="先到的"))
    await db.commit()

    async def _blind(*a, **k):
        return None
    monkeypatch.setattr(notes, "_get_note", _blind)
    install_analysis_model([{"summary": "后到的"}])
    r = await auth_client.post(f"/api/submissions/{sub_id}/summary")
    assert r.status_code == 200 and r.json() == {"summary": "后到的"}


async def test_summary_regenerated_when_scores_change(auth_client, my_assignment, add_student,
                                                      install_analysis_model, db):
    from app.models import QuestionResult
    sub_id = await add_student("张三", "9")
    fake = install_analysis_model([{"summary": "甲"}, {"summary": "乙"}])
    url = f"/api/submissions/{sub_id}/summary"
    assert (await auth_client.post(url)).json() == {"summary": "甲"}
    assert (await auth_client.post(url)).json() == {"summary": "甲"} and len(fake.prompts) == 1
    qr = (await db.execute(select(QuestionResult).where(
        QuestionResult.submission_id == sub_id, QuestionResult.question_no == "2"))).scalar_one()
    qr.score, qr.is_correct = 4, True
    await db.commit()
    assert (await auth_client.post(url)).json() == {"summary": "乙"} and len(fake.prompts) == 2


async def test_malformed_cause_output_keeps_valid_and_retries_missing(
        auth_client, my_assignment, add_student, install_analysis_model):
    for name in ("a", "b"):
        await add_student(name, "9")
    for name in ("c", "d"):
        await add_student(name, "8")
    fake = install_analysis_model([
        {"causes": [{"key": "invented", "cause": "x"}, "oops", {"key": "9", "cause": "甲"}, {"key": "8"}]},
        {"causes": "not a list"},
        {"causes": [{"key": "8", "cause": "乙"}]},
    ])
    assert (await auth_client.post(_url(my_assignment))).json() == {"causes": {"9": "甲"}}
    assert (await auth_client.post(_url(my_assignment))).json() == {"causes": {"9": "甲"}}
    assert (await auth_client.post(_url(my_assignment))).json() == {"causes": {"9": "甲", "8": "乙"}}
    assert len(fake.prompts) == 3
    assert "9" not in fake.prompts[1].split("常见错误答案")[1].split("要求")[0].replace("8", "")