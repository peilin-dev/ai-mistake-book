from app.models import Student
from tests.conftest import make_result


async def _students(db, my_class, *names):
    out = []
    for n in names:
        s = Student(class_id=my_class.id, name=n)
        db.add(s)
        await db.flush()
        out.append(s)
    await db.commit()
    return out


async def test_candidates_missing_all_first_then_roster_order(db, auth_client, my_class, make_done_page):
    s1, s2, s3, s4 = await _students(db, my_class, "甲", "乙", "丙", "丁")
    target = await make_done_page(1, None, None)
    db.add_all([make_result(target.id, None, "2"), make_result(target.id, None, "1"),
                make_result(target.id, None, "10"), make_result(target.id, None, "1")])
    # 乙 already has question 1; 丙 has other questions only; 丁 has two pages (thumb = smallest seq)
    p_b = await make_done_page(2, s2.id, "乙")
    db.add(make_result(p_b.id, None, "1"))
    p_c = await make_done_page(3, s3.id, "丙")
    db.add(make_result(p_c.id, None, "7"))
    p_d2 = await make_done_page(5, s4.id, "丁")
    p_d1 = await make_done_page(4, s4.id, "丁")
    db.add_all([make_result(p_d1.id, None, "8"), make_result(p_d2.id, None, "9")])
    await db.commit()

    r = await auth_client.get(f"/api/pages/{target.id}/claim-candidates")
    assert r.status_code == 200
    body = r.json()
    assert body["page_id"] == target.id and body["image_url"].startswith("/api/files/")
    assert body["question_nos"] == ["1", "2", "10"]
    assert [c["student_id"] for c in body["candidates"]] == [s1.id, s3.id, s4.id, s2.id]
    by_id = {c["student_id"]: c for c in body["candidates"]}
    assert [by_id[s.id]["missing_all"] for s in (s1, s2, s3, s4)] == [True, False, True, True]
    assert [by_id[s.id]["page_count"] for s in (s1, s2, s3, s4)] == [0, 1, 1, 2]
    assert by_id[s1.id]["thumb_url"] is None
    assert p_d1.image_key in by_id[s4.id]["thumb_url"]


async def test_candidates_409_until_done(auth_client, make_page):
    page = await make_page(1)
    r = await auth_client.get(f"/api/pages/{page.id}/claim-candidates")
    assert r.status_code == 409 and r.json()["detail"] == "页面尚未批改完成"


async def test_candidates_other_teacher_404(auth_client, other_teacher_failed_page):
    r = await auth_client.get(f"/api/pages/{other_teacher_failed_page.id}/claim-candidates")
    assert r.status_code == 404
