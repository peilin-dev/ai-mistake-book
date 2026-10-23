import pytest
from sqlalchemy import select

from app.ai.fake import FakeModel
from app.grading.pipeline import grade_page
from app.models import Page, QuestionResult
from tests.conftest import graded, make_result, q


def url_of(a):
    return f"/api/assignments/{a.id}/pages"


async def _set_sources(db, pages, sources):
    for p, s in zip(pages, sources):
        p.source = s
    await db.commit()


async def _grade_two(db, storage, pages, first_name, second_name):
    ids = [p.id for p in pages]
    model = FakeModel([graded(student_name=first_name, questions=[q(no="1")]),
                       graded(student_name=second_name, questions=[q(no="5")])])
    await grade_page(db, storage, model, ids[0])
    await grade_page(db, storage, model, ids[1])
    await db.rollback()
    db.expire_all()
    return [await db.get(Page, i) for i in ids]


async def test_upload_defaults_to_phone_and_accepts_web(auth_client, db, my_assignment, make_jpeg, enqueued):
    r1 = await auth_client.post(url_of(my_assignment), files={"file": ("a.jpg", make_jpeg(1), "image/jpeg")})
    r2 = await auth_client.post(url_of(my_assignment) + "?source=web",
                                files={"file": ("b.jpg", make_jpeg(2), "image/jpeg")})
    assert r1.status_code == 201 and r2.status_code == 201
    assert (await db.get(Page, r1.json()["page_id"])).source == "phone"
    assert (await db.get(Page, r2.json()["page_id"])).source == "web"
    bad = await auth_client.post(url_of(my_assignment) + "?source=fax",
                                 files={"file": ("c.jpg", make_jpeg(3), "image/jpeg")})
    assert bad.status_code == 422


async def test_duplicate_upload_keeps_original_source(auth_client, db, my_assignment, make_jpeg, enqueued):
    data = make_jpeg(1)
    r1 = await auth_client.post(url_of(my_assignment), files={"file": ("a.jpg", data, "image/jpeg")})
    r2 = await auth_client.post(url_of(my_assignment) + "?source=web", files={"file": ("a.jpg", data, "image/jpeg")})
    assert r2.json()["duplicate"] is True
    await db.rollback()
    assert (await db.get(Page, r1.json()["page_id"])).source == "phone"


async def test_web_nameless_page_goes_unassigned(db, storage, auth_client, two_uploaded_pages, roster_zhangsan,
                                                 my_assignment):
    zs, aid = roster_zhangsan.id, my_assignment.id
    await _set_sources(db, two_uploaded_pages, ["web", "web"])
    p1, p2 = await _grade_two(db, storage, two_uploaded_pages, "张三", None)
    assert p1.student_id == zs and p2.student_id is None
    review = (await auth_client.get(f"/api/assignments/{aid}/review")).json()
    assert [p["page_id"] for p in review["pages_unassigned"]] == [p2.id]


async def test_phone_pages_still_chain(db, storage, two_uploaded_pages, roster_zhangsan):
    zs = roster_zhangsan.id
    p1, p2 = await _grade_two(db, storage, two_uploaded_pages, "张三", None)
    assert p1.source == p2.source == "phone"
    assert p2.student_id == zs


@pytest.mark.parametrize("sources", [["web", "phone"], ["phone", "web"]])
async def test_mixed_sources_never_chain(db, storage, two_uploaded_pages, roster_zhangsan, sources):
    await _set_sources(db, two_uploaded_pages, sources)
    _, p2 = await _grade_two(db, storage, two_uploaded_pages, "张三", None)
    assert p2.student_id is None


@pytest.mark.parametrize("sources", [["web", "phone"], ["phone", "web"]])
async def test_late_mixed_sources_never_attach(db, storage, two_uploaded_pages, roster_zhangsan, sources):
    # Page 2 (nameless) finishes first, then page 1: attach_following_pages must also refuse.
    await _set_sources(db, two_uploaded_pages, sources)
    p1, p2 = two_uploaded_pages
    i1, i2 = p1.id, p2.id
    model = FakeModel([graded(student_name=None, questions=[q(no="5")]),
                       graded(student_name="张三", questions=[q(no="1")])])
    await grade_page(db, storage, model, i2)
    await grade_page(db, storage, model, i1)
    await db.rollback()
    db.expire_all()
    assert (await db.get(Page, i2)).student_id is None


async def test_assign_web_page_does_not_drag_next_web_page(db, auth_client, make_done_page, roster_zhangsan):
    pages = [await make_done_page(1), await make_done_page(2)]
    for p in pages:
        p.source = "web"
        db.add(make_result(p.id, None, str(p.seq), needs_review=True))
    await db.commit()
    i1, i2, zs = pages[0].id, pages[1].id, roster_zhangsan.id
    r = await auth_client.patch(f"/api/pages/{i1}", json={"student_id": zs})
    assert r.status_code == 200
    await db.rollback()
    db.expire_all()
    assert (await db.get(Page, i1)).student_id == zs
    assert (await db.get(Page, i2)).student_id is None


async def test_reassign_web_page_does_not_move_next_web_page(db, auth_client, make_done_page, roster_zhangsan,
                                                             my_class):
    from app.models import Student
    other = Student(class_id=my_class.id, name="李四")
    db.add(other)
    await db.commit()
    p1 = await make_done_page(1, roster_zhangsan.id, "张三")
    p2 = await make_done_page(2, roster_zhangsan.id)  # attached under the old rule / manually
    p1.source = p2.source = "web"
    await db.commit()
    i1, i2, zs, oid = p1.id, p2.id, roster_zhangsan.id, other.id
    r = await auth_client.patch(f"/api/pages/{i1}", json={"student_id": oid})
    assert r.status_code == 200
    await db.rollback()
    db.expire_all()
    assert (await db.get(Page, i2)).student_id == zs


async def test_page_list_includes_source(auth_client, db, my_assignment, make_jpeg, enqueued):
    await auth_client.post(url_of(my_assignment), files={"file": ("a.jpg", make_jpeg(1), "image/jpeg")})
    await auth_client.post(url_of(my_assignment) + "?source=web",
                           files={"file": ("b.jpg", make_jpeg(2), "image/jpeg")})
    items = (await auth_client.get(url_of(my_assignment))).json()
    assert [i["source"] for i in items] == ["phone", "web"]


