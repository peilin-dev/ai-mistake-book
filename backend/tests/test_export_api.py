from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.export.service import purge_old_exports
from app.models import Export, QuestionResult, Student, Submission
from tests.conftest import make_result, paper_jpeg, storage_exists, utcnow


@pytest_asyncio.fixture
async def lisi(db, my_class) -> Student:
    s = Student(class_id=my_class.id, name="李四")
    db.add(s)
    await db.commit()
    return s


@pytest_asyncio.fixture
async def two_students(db, storage, my_assignment, roster_zhangsan, lisi, make_done_page):
    """张三 wrong on q2 (with crop); 李四 all correct."""
    ids = {}
    for seq, stu in ((1, roster_zhangsan), (2, lisi)):
        page = await make_done_page(seq, stu.id, stu.name)
        sub = Submission(assignment_id=my_assignment.id, student_id=stu.id)
        db.add(sub)
        await db.flush()
        rows = [make_result(page.id, sub.id, "1")]
        if stu is roster_zhangsan:
            key = f"crops/t/{page.id}-2.jpg"
            await storage.put(key, paper_jpeg(seed=3), "image/jpeg")
            rows.append(make_result(page.id, sub.id, "2", is_correct=False, score=1, max_score=4,
                                    student_answer="9", correct_answer="8", crop_key=key))
        else:
            rows.append(make_result(page.id, sub.id, "2", score=4, max_score=4))
        db.add_all(rows)
        ids[stu.name] = sub.id
    await db.commit()
    return ids


def url_of(a) -> str:
    return f"/api/assignments/{a.id}/exports"


async def test_export_lecture_returns_signed_pdf_url(auth_client, my_assignment, two_students):
    r = await auth_client.post(url_of(my_assignment), json={"kind": "lecture"})
    assert r.status_code == 201
    body = r.json()
    assert body["url"].startswith("/api/files/exports/") and ".pdf?" in body["url"]
    assert body["filename"].endswith("-讲评单.pdf") and body["filename"].startswith("五(2)班-")
    got = await auth_client.get(body["url"])
    assert got.status_code == 200 and got.content.startswith(b"%PDF")


async def test_export_student_requires_own_submission(db, auth_client, my_assignment, two_students,
                                                      make_assignment, roster_zhangsan):
    foreign = await make_assignment()
    sub = Submission(assignment_id=foreign.id, student_id=roster_zhangsan.id)
    db.add(sub)
    await db.commit()
    for body in ({"kind": "student"}, {"kind": "student", "submission_id": sub.id},
                 {"kind": "student", "submission_id": 999999}):
        r = await auth_client.post(url_of(my_assignment), json=body)
        assert r.status_code in (404, 422), body


async def test_export_student_pdf(auth_client, my_assignment, two_students):
    r = await auth_client.post(url_of(my_assignment),
                               json={"kind": "student", "submission_id": two_students["张三"]})
    assert r.status_code == 201
    assert r.json()["filename"].endswith("-张三-错题单.pdf")
    assert (await auth_client.get(r.json()["url"])).content.startswith(b"%PDF")


async def test_export_student_all_correct_409(auth_client, my_assignment, two_students):
    r = await auth_client.post(url_of(my_assignment),
                               json={"kind": "student", "submission_id": two_students["李四"]})
    assert r.status_code == 409
    assert r.json()["detail"] == "这位同学这次全对，没有错题可以导出"


async def test_export_class_students_one_page_each(auth_client, my_assignment, two_students, monkeypatch):
    from app.export import service
    seen = []
    real = service.render_mistakes

    def spy(sheets):
        seen.append([s.student_name for s in sheets])
        return real(sheets)

    monkeypatch.setattr(service, "render_mistakes", spy)
    r = await auth_client.post(url_of(my_assignment), json={"kind": "class_students"})
    assert r.status_code == 201
    assert seen == [["张三"]]  # 李四 has no mistakes, so no sheet
    assert (await auth_client.get(r.json()["url"])).content.startswith(b"%PDF")
    assert r.json()["filename"].endswith("-错题单.pdf")


async def test_export_class_students_none_wrong_409(db, auth_client, my_assignment, two_students):
    await db.execute(update(QuestionResult).values(is_correct=True, score=4, max_score=4))
    await db.commit()
    r = await auth_client.post(url_of(my_assignment), json={"kind": "class_students"})
    assert r.status_code == 409 and r.json()["detail"] == "这次没有同学有错题"


async def test_export_uses_signature_or_default(db, auth_client, teacher, my_assignment, two_students,
                                                monkeypatch):
    from app.export import service
    seen = []
    real = service.render_lecture

    def spy(sheet):
        seen.append(sheet.signature)
        return real(sheet)

    monkeypatch.setattr(service, "render_lecture", spy)
    await auth_client.post(url_of(my_assignment), json={"kind": "lecture"})
    teacher.display_name = "王老师"
    await db.commit()
    await auth_client.post(url_of(my_assignment), json={"kind": "lecture"})
    assert seen == ["老师", "王老师"]


async def test_export_other_teacher_404(client_for, make_teacher, my_assignment, two_students):
    other = client_for(await make_teacher())
    r = await other.post(url_of(my_assignment), json={"kind": "lecture"})
    assert r.status_code == 404


async def _paper(db, assignment, student_id=None, status="done"):
    from app.models import PracticeItem, PracticePaper
    p = PracticePaper(assignment_id=assignment.id, student_id=student_id, student_key=student_id or 0,
                      status=status)
    db.add(p)
    await db.flush()
    db.add_all([
        PracticeItem(paper_id=p.id, position=1, source_no="2", kind="choice", stem="哪个最大？",
                     options='["12","40","7"]', answer="B"),
        PracticeItem(paper_id=p.id, position=2, source_no="2", kind="calc", stem="计算 3 + 4", answer="7"),
    ])
    await db.commit()
    return p


async def test_export_practice_class_and_student(db, auth_client, my_assignment, two_students, roster_zhangsan):
    from pypdf import PdfReader
    import io
    await _paper(db, my_assignment)
    await _paper(db, my_assignment, roster_zhangsan.id)
    r = await auth_client.post(url_of(my_assignment), json={"kind": "practice"})
    assert r.status_code == 201, r.text
    assert r.json()["filename"].endswith("-练习纸.pdf") and "张三" not in r.json()["filename"]
    got = await auth_client.get(r.json()["url"])
    assert got.content.startswith(b"%PDF")
    assert "参考答案" in "".join(p.extract_text() for p in PdfReader(io.BytesIO(got.content)).pages)

    r = await auth_client.post(url_of(my_assignment), json={
        "kind": "practice_student", "submission_id": two_students["张三"], "include_answers": False})
    assert r.status_code == 201, r.text
    assert r.json()["filename"].endswith("-张三-练习纸.pdf")
    got = await auth_client.get(r.json()["url"])
    assert got.content.startswith(b"%PDF")
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(got.content)).pages)
    assert "参考答案" not in text and "张三" in text


@pytest.mark.parametrize("bad", ["{not json", '{"a": 1}', '[1, null, {"x": 1}, "A & <b>"]', '"str"'])
async def test_export_practice_bad_options_still_pdf(db, auth_client, my_assignment, two_students, bad):
    from app.models import PracticeItem
    p = await _paper(db, my_assignment)
    item = (await db.execute(select(PracticeItem).where(PracticeItem.paper_id == p.id,
                                                        PracticeItem.position == 1))).scalar_one()
    item.options = bad
    await db.commit()
    r = await auth_client.post(url_of(my_assignment), json={"kind": "practice"})
    assert r.status_code == 201, r.text
    assert (await auth_client.get(r.json()["url"])).content.startswith(b"%PDF")


async def test_export_practice_not_ready_409(db, auth_client, my_assignment, two_students, roster_zhangsan):
    msg = "还没有可以导出的练习纸"
    r = await auth_client.post(url_of(my_assignment), json={"kind": "practice"})
    assert r.status_code == 409 and r.json()["detail"] == msg
    await _paper(db, my_assignment, status="running")
    r = await auth_client.post(url_of(my_assignment), json={"kind": "practice"})
    assert r.status_code == 409 and r.json()["detail"] == msg
    r = await auth_client.post(url_of(my_assignment), json={
        "kind": "practice_student", "submission_id": two_students["张三"]})
    assert r.status_code == 409 and r.json()["detail"] == msg
    r = await auth_client.post(url_of(my_assignment), json={"kind": "practice_student"})
    assert r.status_code == 422


async def test_purge_old_exports_deletes_files_and_rows(db, storage, teacher):
    now = utcnow()
    old = Export(teacher_id=teacher.id, file_key=f"exports/{teacher.id}/old.pdf", kind="lecture",
                 created_at=now - timedelta(days=8))
    fresh = Export(teacher_id=teacher.id, file_key=f"exports/{teacher.id}/new.pdf", kind="lecture",
                   created_at=now - timedelta(days=1))
    db.add_all([old, fresh])
    await db.commit()
    for e in (old, fresh):
        await storage.put(e.file_key, b"%PDF", "application/pdf")
    assert await purge_old_exports(db, storage, now) == 1
    assert not await storage_exists(storage, old.file_key)
    assert await storage_exists(storage, fresh.file_key)
    keys = (await db.execute(select(Export.file_key))).scalars().all()
    assert keys == [fresh.file_key]


async def test_store_export_failed_commit_removes_file(db, storage, teacher, monkeypatch):
    from app.export.service import store_export
    seen = {}
    real_put = storage.put

    async def spy_put(key, data, ct):
        seen["key"] = key
        await real_put(key, data, ct)

    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(storage, "put", spy_put)
    monkeypatch.setattr(db, "commit", boom)
    with pytest.raises(RuntimeError):
        await store_export(db, storage, teacher.id, "lecture", b"%PDF")
    assert "key" in seen and not await storage_exists(storage, seen["key"])


async def test_export_survives_missing_crop(db, auth_client, storage, my_assignment, two_students):
    keys = (await db.execute(select(QuestionResult.crop_key).where(QuestionResult.crop_key.is_not(None)))
            ).scalars().all()
    assert len(keys) == 1
    await storage.delete(keys[0])
    for body in ({"kind": "lecture"}, {"kind": "student", "submission_id": two_students["张三"]}):
        r = await auth_client.post(url_of(my_assignment), json=body)
        assert r.status_code == 201
        assert (await auth_client.get(r.json()["url"])).content.startswith(b"%PDF")


async def test_purge_keeps_row_when_delete_fails(db, storage, teacher, monkeypatch):
    now = utcnow()
    e = Export(teacher_id=teacher.id, file_key=f"exports/{teacher.id}/x.pdf", kind="lecture",
               created_at=now - timedelta(days=9))
    db.add(e)
    await db.commit()
    await storage.put(e.file_key, b"%PDF", "application/pdf")
    real = storage.delete

    async def fail(key):
        raise OSError("disk")

    monkeypatch.setattr(storage, "delete", fail)
    assert await purge_old_exports(db, storage, now) == 0
    assert len((await db.execute(select(Export))).scalars().all()) == 1
    monkeypatch.setattr(storage, "delete", real)
    assert await purge_old_exports(db, storage, now) == 1
    assert not await storage_exists(storage, e.file_key)
