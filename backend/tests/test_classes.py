from sqlalchemy import func, select

from app.classes.roster import RosterEntry, parse_roster
from app.models import (
    Assignment,
    Class_,
    Page,
    QuestionResult,
    Student,
    Submission,
    Teacher,
)


def test_parse_roster_formats():
    text = "张三\n 2024002 李四 \n王五,2024003\n\n张三"
    assert parse_roster(text) == [
        RosterEntry("张三", None),
        RosterEntry("李四", "2024002"),
        RosterEntry("王五", "2024003"),
    ]


def test_parse_roster_fullwidth_comma_tab_and_letter_prefix():
    text = "赵六，2024004\r\nA2024005\t钱七\n   \n孙八\t2024006"
    assert parse_roster(text) == [
        RosterEntry("赵六", "2024004"),
        RosterEntry("钱七", "A2024005"),
        RosterEntry("孙八", "2024006"),
    ]


async def test_grade_must_be_1_to_12(auth_client):
    r = await auth_client.post("/api/classes", json={"name": "五(2)班", "grade": 13})
    assert r.status_code == 422
    r = await auth_client.post("/api/classes", json={"name": "五(2)班", "grade": 0})
    assert r.status_code == 422


async def test_name_is_stripped_and_bounded(auth_client):
    r = await auth_client.post("/api/classes", json={"name": "  三班 ", "grade": 3})
    assert r.status_code == 201
    assert r.json()["name"] == "三班"
    for bad in ["   ", "", "x" * 33]:
        r = await auth_client.post("/api/classes", json={"name": bad, "grade": 3})
        assert r.status_code == 422


async def test_requires_auth(client):
    assert (await client.get("/api/classes")).status_code == 401


async def test_list_only_own_classes_ordered(auth_client, my_class, other_teacher_class):
    r2 = await auth_client.post("/api/classes", json={"name": "二班", "grade": 2})
    r = await auth_client.get("/api/classes")
    assert r.status_code == 200
    assert [c["id"] for c in r.json()] == [my_class.id, r2.json()["id"]]


async def test_other_teachers_class_is_404(auth_client, other_teacher_class):
    cid = other_teacher_class.id
    r = await auth_client.get(f"/api/classes/{cid}/students")
    assert r.status_code == 404
    r = await auth_client.post(f"/api/classes/{cid}/students:import", json={"text": "张三"})
    assert r.status_code == 404
    r = await auth_client.delete(f"/api/classes/{cid}")
    assert r.status_code == 404
    # same as nonexistent
    r = await auth_client.get("/api/classes/99999999/students")
    assert r.status_code == 404


async def test_import_and_rerun_skips_identical(auth_client, my_class):
    url = f"/api/classes/{my_class.id}/students:import"
    r = await auth_client.post(url, json={"text": "张三\n2024002 李四\n王五,2024003"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 3
    assert [s["name"] for s in body["students"]] == ["张三", "李四", "王五"]

    r = await auth_client.post(url, json={"text": "张三\n2024002 李四\n赵六"})
    body = r.json()
    assert body["created"] == 1
    assert [s["name"] for s in body["students"]] == ["张三", "李四", "王五", "赵六"]

    # same name, different student_no is not identical -> appended
    r = await auth_client.post(url, json={"text": "2024009 张三"})
    assert r.json()["created"] == 1

    r = await auth_client.get(f"/api/classes/{my_class.id}/students")
    assert r.status_code == 200
    got = r.json()
    assert len(got) == 5
    assert [s["id"] for s in got] == sorted(s["id"] for s in got)
    assert got[1]["student_no"] == "2024002"


async def test_delete_cascades_full_chain(auth_client, my_class, teacher, db):
    cid = my_class.id
    st = Student(class_id=cid, name="张三")
    asg = Assignment(class_id=cid, subject="math", title="hw")
    db.add_all([st, asg])
    await db.flush()
    page = Page(assignment_id=asg.id, seq=1, image_key="k", image_sha256="a" * 64)
    sub = Submission(assignment_id=asg.id, student_id=st.id)
    db.add_all([page, sub])
    await db.flush()
    db.add_all(
        [
            QuestionResult(submission_id=sub.id, page_id=page.id, question_no="1"),
            QuestionResult(submission_id=None, page_id=page.id, question_no="2"),
        ]
    )
    await db.commit()
    teacher_id, asg_id, page_id = teacher.id, asg.id, page.id

    r = await auth_client.delete(f"/api/classes/{cid}")
    assert r.status_code == 204

    db.expire_all()

    async def count(model, *where):
        return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()

    assert await count(Class_, Class_.id == cid) == 0
    assert await count(Student, Student.class_id == cid) == 0
    assert await count(Assignment, Assignment.class_id == cid) == 0
    assert await count(Page, Page.assignment_id == asg_id) == 0
    assert await count(Submission, Submission.assignment_id == asg_id) == 0
    assert await count(QuestionResult, QuestionResult.page_id == page_id) == 0
    assert await count(Teacher, Teacher.id == teacher_id) == 1
