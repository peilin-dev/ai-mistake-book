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


def test_parse_roster_non_number_tokens_stay_in_name():
    assert parse_roster("张三 李四\nJohn Smith\n2024001 Mary Ann") == [
        RosterEntry("张三 李四", None),
        RosterEntry("John Smith", None),
        RosterEntry("Mary Ann", "2024001"),
    ]


async def test_client_fixture_stays_unauthenticated(client, auth_client):
    assert (await client.get("/api/me")).status_code == 401
    assert (await auth_client.get("/api/me")).status_code == 200


async def test_client_for_other_teacher(client_for, make_teacher, my_class):
    other = await make_teacher()
    r = await client_for(other).get(f"/api/classes/{my_class.id}/students")
    assert r.status_code == 404

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


async def _class_with_files(db, storage, cls):
    from datetime import datetime

    asg = Assignment(class_id=cls.id, subject="math", title="hw")
    db.add(asg)
    await db.flush()
    live = Page(assignment_id=asg.id, seq=1, image_key="originals/t/1.jpg", image_sha256="a")
    purged = Page(assignment_id=asg.id, seq=2, image_key="originals/t/2.jpg", image_sha256="b",
                  original_deleted_at=datetime(2026, 1, 1))
    db.add_all([live, purged])
    await db.flush()
    db.add(QuestionResult(page_id=purged.id, question_no="1", crop_key="crops/t/9.jpg"))
    await db.commit()
    for key in ("originals/t/1.jpg", "crops/t/9.jpg", "keep/other.jpg"):
        await storage.put(key, b"x", "image/jpeg")


async def test_delete_class_removes_originals_and_crops(auth_client, my_class, db, storage):
    from tests.conftest import storage_exists

    await _class_with_files(db, storage, my_class)
    assert (await auth_client.delete(f"/api/classes/{my_class.id}")).status_code == 204
    assert not await storage_exists(storage, "originals/t/1.jpg")
    assert not await storage_exists(storage, "crops/t/9.jpg")
    assert await storage_exists(storage, "keep/other.jpg")


async def test_delete_class_survives_storage_errors(app, auth_client, my_class, db, storage):
    from app.storage.base import get_storage

    await _class_with_files(db, storage, my_class)
    deleted: list[str] = []

    class Flaky:
        async def delete(self, key):
            deleted.append(key)
            raise OSError("disk gone")

    app.dependency_overrides[get_storage] = lambda: Flaky()
    cid = my_class.id
    assert (await auth_client.delete(f"/api/classes/{cid}")).status_code == 204
    assert sorted(deleted) == ["crops/t/9.jpg", "originals/t/1.jpg"]  # purged original skipped
    db.expire_all()
    assert await db.get(Class_, cid) is None


async def add_student(db, cls, name, student_no=None) -> Student:
    s = Student(class_id=cls.id, name=name, student_no=student_no)
    db.add(s)
    await db.commit()
    return s


async def test_rename_student(auth_client, my_class, db):
    s = await add_student(db, my_class, "张三")
    r = await auth_client.patch(f"/api/students/{s.id}", json={"name": " 张珊 ", "student_no": "2024001"})
    assert r.status_code == 200 and r.json()["name"] == "张珊" and r.json()["student_no"] == "2024001"


async def test_rename_student_validation_and_partial(auth_client, my_class, db):
    s = await add_student(db, my_class, "王五", "7")
    assert (await auth_client.patch(f"/api/students/{s.id}", json={"name": "   "})).status_code == 422
    assert (await auth_client.patch(f"/api/students/{s.id}", json={"name": "x" * 65})).status_code == 422
    r = await auth_client.patch(f"/api/students/{s.id}", json={"student_no": None})
    assert r.status_code == 200 and r.json()["name"] == "王五" and r.json()["student_no"] is None
    r = await auth_client.patch(f"/api/students/{s.id}", json={})
    assert r.status_code == 200 and r.json()["name"] == "王五"


async def test_delete_student_without_results(auth_client, my_class, db):
    s = await add_student(db, my_class, "李四")
    assert (await auth_client.delete(f"/api/students/{s.id}")).status_code == 204


async def test_cannot_delete_student_with_results(auth_client, graded_submission):
    r = await auth_client.delete(f"/api/students/{graded_submission.student_id}")
    assert r.status_code == 409 and r.json()["detail"] == "已有成绩的学生不能删除，可以改名"


async def test_cannot_delete_student_referenced_only_by_page(auth_client, make_done_page, roster_zhangsan):
    await make_done_page(1, roster_zhangsan.id, "张三")
    r = await auth_client.delete(f"/api/students/{roster_zhangsan.id}")
    assert r.status_code == 409


async def test_foreign_student_404(auth_client, other_class_student):
    assert (await auth_client.patch(f"/api/students/{other_class_student.id}", json={"name": "x"})).status_code == 404
    assert (await auth_client.delete(f"/api/students/{other_class_student.id}")).status_code == 404
    assert (await auth_client.delete("/api/students/999999")).status_code == 404