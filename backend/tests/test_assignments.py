from sqlalchemy import select

from app.models import Page, PageStatus, QuestionResult


async def _create(c, class_id, subject="math", title="第三单元测验"):
    return await c.post(
        "/api/assignments", json={"class_id": class_id, "subject": subject, "title": title}
    )


async def test_create_assignment_remembers_subject(auth_client, my_class):
    r = await _create(auth_client, my_class.id)
    assert r.status_code == 201
    assert r.json()["answer_key_status"] == "none"
    assert r.json()["subject"] == "math"
    me = (await auth_client.get("/api/me")).json()
    assert me["last_subject"] == "math"
    await _create(auth_client, my_class.id, subject="english")
    assert (await auth_client.get("/api/me")).json()["last_subject"] == "english"


async def test_unknown_subject_422(auth_client, my_class):
    r = await _create(auth_client, my_class.id, subject="art_x", title="t")
    assert r.status_code == 422


async def test_title_validation(auth_client, my_class):
    assert (await _create(auth_client, my_class.id, title="   ")).status_code == 422
    assert (await _create(auth_client, my_class.id, title="x" * 65)).status_code == 422
    r = await _create(auth_client, my_class.id, title="  hi  ")
    assert r.json()["title"] == "hi"
    assert (await _create(auth_client, my_class.id, title="x" * 64)).status_code == 201


async def test_create_in_foreign_class_404_and_no_subject_change(
    auth_client, other_teacher_class
):
    r = await _create(auth_client, other_teacher_class.id)
    assert r.status_code == 404
    assert (await auth_client.get("/api/me")).json()["last_subject"] is None


async def test_list_assignments_newest_first(auth_client, my_class):
    a = (await _create(auth_client, my_class.id, title="a")).json()["id"]
    b = (await _create(auth_client, my_class.id, title="b")).json()["id"]
    r = await auth_client.get(f"/api/classes/{my_class.id}/assignments")
    assert [x["id"] for x in r.json()] == [b, a]


async def test_list_foreign_class_404(auth_client, other_teacher_class):
    r = await auth_client.get(f"/api/classes/{other_teacher_class.id}/assignments")
    assert r.status_code == 404


async def test_get_assignment_and_ownership(auth_client, my_class, make_assignment):
    aid = (await _create(auth_client, my_class.id)).json()["id"]
    r = await auth_client.get(f"/api/assignments/{aid}")
    assert r.status_code == 200 and r.json()["id"] == aid
    foreign = await make_assignment()
    assert (await auth_client.get(f"/api/assignments/{foreign.id}")).status_code == 404
    assert (await auth_client.get(f"/api/assignments/{foreign.id}/progress")).status_code == 404
    assert (await auth_client.get("/api/assignments/999999")).status_code == 404
    assert (await auth_client.get("/api/assignments/999999/progress")).status_code == 404


async def test_progress_counts(auth_client, my_class, db):
    aid = (await _create(auth_client, my_class.id)).json()["id"]
    empty = (await auth_client.get(f"/api/assignments/{aid}/progress")).json()
    assert empty == dict(total=0, queued=0, processing=0, done=0, failed=0, needs_review=0)

    pages = []
    for i, st in enumerate(
        [PageStatus.queued, PageStatus.processing, PageStatus.done, PageStatus.done, PageStatus.failed]
    ):
        p = Page(assignment_id=aid, seq=i + 1, image_key=f"k{i}", image_sha256=f"s{i}", status=st)
        db.add(p)
        pages.append(p)
    await db.flush()

    def qr(page, n, nr, rev):
        return QuestionResult(page_id=page.id, question_no=n, needs_review=nr, reviewed=rev)

    db.add_all(
        [
            qr(pages[2], "1", True, False),
            qr(pages[2], "2", True, True),  # already reviewed: excluded
            qr(pages[3], "1", True, False),
            qr(pages[3], "2", False, False),  # not flagged
        ]
    )
    await db.commit()

    r = (await auth_client.get(f"/api/assignments/{aid}/progress")).json()
    assert r == dict(total=5, queued=1, processing=1, done=2, failed=1, needs_review=2)


async def test_progress_ignores_other_assignments(auth_client, my_class, make_assignment, db):
    aid = (await _create(auth_client, my_class.id)).json()["id"]
    other = await make_assignment()
    p = Page(assignment_id=other.id, seq=1, image_key="k", image_sha256="s", status=PageStatus.done)
    db.add(p)
    await db.flush()
    db.add(QuestionResult(page_id=p.id, question_no="1", needs_review=True))
    await db.commit()
    r = (await auth_client.get(f"/api/assignments/{aid}/progress")).json()
    assert r["total"] == 0 and r["needs_review"] == 0
