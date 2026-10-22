from datetime import timedelta

from sqlalchemy import select

from app.models import PracticeItem, PracticePaper
from tests.conftest import utcnow
from tests.test_practice_jobs import build_sources

NO_CLASS_SOURCES = "这次大家做得不错，没有需要练习的题"
NO_STUDENT_SOURCES = "这位同学这次没有需要练习的题"


async def _add_items(db, paper_id: int, n: int = 2) -> list[PracticeItem]:
    items = [PracticeItem(paper_id=paper_id, position=i + 1, source_no="1", kind="calc", stem=f"旧题{i}",
                          options=None, answer="1") for i in range(n)]
    db.add_all(items)
    await db.commit()
    return items


async def test_generate_creates_paper_and_enqueues(db, auth_client, my_assignment, practice_enqueued):
    await build_sources(db, my_assignment, n_sources=3)
    assert (await auth_client.get(f"/api/assignments/{my_assignment.id}/practice")).status_code == 404

    r = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["scope"] == "class" and body["student_name"] is None
    assert (body["status"], body["partial"], body["sources_total"], body["sources_done"]) == ("queued", False, 3, 0)
    assert (body["error"], body["generated_at"], body["items"], body["last_replace_failed_item"]) == (None, None, [], None)
    assert practice_enqueued == [("practice_paper_job", body["id"])]
    paper = await db.get(PracticePaper, body["id"])
    assert (paper.student_id, paper.student_key) == (None, 0)

    got = await auth_client.get(f"/api/assignments/{my_assignment.id}/practice")
    assert got.status_code == 200 and got.json()["id"] == body["id"]
    assert (await auth_client.get(f"/api/practice/{body['id']}")).json()["status"] == "queued"


async def test_student_generate_and_get(db, auth_client, my_assignment, practice_enqueued):
    students, subs, kp = await build_sources(db, my_assignment, n_sources=2)
    assert (await auth_client.get(f"/api/submissions/{subs[0].id}/practice")).status_code == 404
    r = await auth_client.post(f"/api/submissions/{subs[0].id}/practice")
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["scope"], body["student_name"], body["sources_total"]) == ("student", "王小明0", 2)
    paper = await db.get(PracticePaper, body["id"])
    assert (paper.student_id, paper.student_key) == (students[0].id, students[0].id)
    # The class paper and another student's paper are separate rows.
    r2 = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    r3 = await auth_client.post(f"/api/submissions/{subs[1].id}/practice")
    assert len({body["id"], r2.json()["id"], r3.json()["id"]}) == 3

    paper.status = "done"
    await db.commit()
    await _add_items(db, paper.id, 1)
    item = (await db.execute(select(PracticeItem).where(PracticeItem.paper_id == paper.id))).scalar_one()
    item.knowledge_point_id = kp.id
    await db.commit()
    got = (await auth_client.get(f"/api/submissions/{subs[0].id}/practice")).json()
    assert got["items"] == [{"id": item.id, "position": 1, "source_no": "1", "knowledge_point": "面积",
                             "kind": "calc", "stem": "旧题0", "options": None, "answer": "1", "replacing": False}]


async def test_second_generate_while_running_returns_same_paper(db, auth_client, my_assignment, practice_enqueued):
    await build_sources(db, my_assignment)
    first = (await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")).json()
    again = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    assert again.status_code == 200 and again.json()["id"] == first["id"]
    paper = await db.get(PracticePaper, first["id"])
    paper.status, paper.sources_done = "running", 2
    await db.commit()
    third = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    assert third.status_code == 200 and third.json()["sources_done"] == 2
    assert len(practice_enqueued) == 1


async def test_regenerate_resets_done_paper(db, auth_client, my_assignment, practice_enqueued):
    await build_sources(db, my_assignment)
    first = (await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")).json()
    paper = await db.get(PracticePaper, first["id"])
    items = await _add_items(db, paper.id)
    paper.status, paper.partial, paper.sources_done, paper.generated_at = "done", True, 3, utcnow()
    paper.last_replace_failed_item = items[0].id
    await db.commit()
    assert len((await auth_client.get(f"/api/practice/{paper.id}")).json()["items"]) == 2

    r = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == paper.id
    assert (body["status"], body["partial"], body["sources_done"], body["items"]) == ("queued", False, 0, [])
    assert (body["generated_at"], body["last_replace_failed_item"]) == (None, None)
    assert practice_enqueued == [("practice_paper_job", paper.id)] * 2
    # The old questions stay stored (hidden) until the job replaces them.
    stored = (await db.execute(select(PracticeItem).where(PracticeItem.paper_id == paper.id))).scalars().all()
    assert len(stored) == 2

    # A failed paper is regenerated the same way.
    await db.refresh(paper)
    paper.status, paper.error = "failed", "这次没出成题，请稍后重试"
    await db.commit()
    r = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    assert r.status_code == 201 and r.json()["error"] is None
    assert len(practice_enqueued) == 3


async def test_no_sources_409_class_and_student(db, auth_client, my_assignment, practice_enqueued):
    _, subs, _ = await build_sources(db, my_assignment, n_sources=0)
    r = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    assert (r.status_code, r.json()["detail"]) == (409, NO_CLASS_SOURCES)
    r = await auth_client.post(f"/api/submissions/{subs[0].id}/practice")
    assert (r.status_code, r.json()["detail"]) == (409, NO_STUDENT_SOURCES)
    assert practice_enqueued == []
    assert (await db.execute(select(PracticePaper))).scalars().all() == []


async def test_enqueue_failure_marks_paper_failed_and_503(db, app, auth_client, my_assignment):
    from app.practice.router import get_practice_enqueuer

    async def broken(function, obj_id):
        raise ConnectionError("redis down")

    app.dependency_overrides[get_practice_enqueuer] = lambda: broken
    await build_sources(db, my_assignment)
    r = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    assert r.status_code == 503
    paper = (await db.execute(select(PracticePaper))).scalar_one()
    await db.refresh(paper)
    assert paper.status == "failed"


async def test_stale_running_paper_is_failed_on_read(db, auth_client, my_assignment, practice_enqueued):
    await build_sources(db, my_assignment)
    first = (await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")).json()
    paper = await db.get(PracticePaper, first["id"])
    paper.status = "running"
    await db.commit()
    paper.updated_at = utcnow() - timedelta(hours=2)  # the job died without finishing
    await db.commit()
    body = (await auth_client.get(f"/api/practice/{paper.id}")).json()
    assert (body["status"], body["error"]) == ("failed", "这次没出成题，请稍后重试")
    r = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    assert r.status_code == 201 and len(practice_enqueued) == 2


async def test_replace_endpoint_marks_replacing_and_enqueues(db, auth_client, my_assignment, practice_enqueued):
    await build_sources(db, my_assignment)
    paper_id = (await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")).json()["id"]
    paper = await db.get(PracticePaper, paper_id)
    paper.status = "done"
    await db.commit()
    items = await _add_items(db, paper_id)
    r = await auth_client.post(f"/api/practice-items/{items[0].id}/replace")
    assert (r.status_code, r.json()) == (202, {"queued": True})
    assert practice_enqueued[-1] == ("practice_replace_job", items[0].id)
    body = (await auth_client.get(f"/api/practice/{paper_id}")).json()
    assert [i["replacing"] for i in body["items"]] == [True, False]
    # A second tap while it is still replacing does not enqueue again.
    r = await auth_client.post(f"/api/practice-items/{items[0].id}/replace")
    assert r.status_code == 202 and len(practice_enqueued) == 2


async def test_replace_rejected_while_running_or_failed(db, auth_client, my_assignment, practice_enqueued):
    await build_sources(db, my_assignment)
    paper_id = (await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")).json()["id"]
    items = await _add_items(db, paper_id)
    paper = await db.get(PracticePaper, paper_id)
    for status in ("queued", "running"):
        paper.status = status
        await db.commit()
        r = await auth_client.post(f"/api/practice-items/{items[0].id}/replace")
        assert (r.status_code, r.json()["detail"]) == (409, "还在出题，请稍等")
    paper.status = "failed"
    await db.commit()
    r = await auth_client.post(f"/api/practice-items/{items[0].id}/replace")
    assert (r.status_code, r.json()["detail"]) == (409, "这张练习纸没出成，请重新生成")
    assert len(practice_enqueued) == 1


async def test_practice_endpoints_other_teacher_404(db, client_for, make_teacher, auth_client, my_assignment,
                                                    practice_enqueued):
    _, subs, _ = await build_sources(db, my_assignment)
    paper_id = (await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")).json()["id"]
    paper = await db.get(PracticePaper, paper_id)
    paper.status = "done"
    await db.commit()
    items = await _add_items(db, paper_id)
    other = client_for(await make_teacher())
    for method, url in [
        ("post", f"/api/assignments/{my_assignment.id}/practice"),
        ("get", f"/api/assignments/{my_assignment.id}/practice"),
        ("post", f"/api/submissions/{subs[0].id}/practice"),
        ("get", f"/api/submissions/{subs[0].id}/practice"),
        ("get", f"/api/practice/{paper_id}"),
        ("post", f"/api/practice-items/{items[0].id}/replace"),
        ("get", "/api/practice/999999"),
        ("post", "/api/practice-items/999999/replace"),
        ("post", "/api/assignments/999999/practice"),
        ("post", "/api/submissions/999999/practice"),
    ]:
        r = await getattr(other, method)(url)
        assert r.status_code == 404, (method, url, r.status_code)
    assert len(practice_enqueued) == 1


# --- fix round 1 ---

async def _insert_winner(settings, assignment_id: int) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import make_engine

    engine = make_engine(settings.DATABASE_URL)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            p = PracticePaper(assignment_id=assignment_id, student_id=None, student_key=0, status="queued",
                              sources_total=3, sources_done=0)
            s.add(p)
            await s.commit()
            return p.id
    finally:
        await engine.dispose()


def _deadlock():
    from sqlalchemy.exc import OperationalError
    return OperationalError("INSERT", {}, Exception(1213, "Deadlock found when trying to get lock"))


async def test_first_tap_deadlock_victim_returns_winner(db, settings, auth_client, my_assignment,
                                                        practice_enqueued, monkeypatch):
    await build_sources(db, my_assignment)
    aid = my_assignment.id
    real_commit = db.commit
    state = {"n": 0, "winner": None}

    async def commit():
        state["n"] += 1
        if state["n"] == 1:
            await db.rollback()  # the victim's locks go away; the other tap commits its paper
            state["winner"] = await _insert_winner(settings, aid)
            raise _deadlock()
        await real_commit()

    monkeypatch.setattr(db, "commit", commit)
    r = await auth_client.post(f"/api/assignments/{aid}/practice")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == state["winner"]
    assert practice_enqueued == []


async def test_first_tap_deadlock_twice_is_409(db, auth_client, my_assignment, practice_enqueued, monkeypatch):
    await build_sources(db, my_assignment)
    aid = my_assignment.id
    real_commit = db.commit
    state = {"n": 0}

    async def commit():
        state["n"] += 1
        if any(isinstance(o, PracticePaper) for o in db.new):  # every insert attempt loses; re-query finds none
            raise _deadlock()
        await real_commit()

    monkeypatch.setattr(db, "commit", commit)
    r = await auth_client.post(f"/api/assignments/{aid}/practice")
    assert (r.status_code, r.json()["detail"]) == (409, "还在出题，请稍等")
    assert practice_enqueued == []


async def test_other_operational_errors_are_not_swallowed(db, auth_client, my_assignment, practice_enqueued,
                                                         monkeypatch):
    import pytest
    from sqlalchemy.exc import OperationalError

    await build_sources(db, my_assignment)
    aid = my_assignment.id

    async def commit():
        raise OperationalError("INSERT", {}, Exception(2013, "Lost connection"))

    monkeypatch.setattr(db, "commit", commit)
    with pytest.raises(OperationalError):
        await auth_client.post(f"/api/assignments/{aid}/practice")

# --- final review fixes ---

async def test_regenerate_enqueue_failure_keeps_the_old_sheet(db, app, auth_client, my_assignment,
                                                              practice_enqueued):
    from app.practice.router import get_practice_enqueuer

    await build_sources(db, my_assignment)
    first = (await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")).json()
    paper = await db.get(PracticePaper, first["id"])
    items = await _add_items(db, paper.id)
    done_at = utcnow().replace(microsecond=0)
    paper.status, paper.partial, paper.sources_done, paper.generated_at = "done", True, 3, done_at
    paper.last_replace_failed_item = items[1].id
    await db.commit()

    async def broken(function, obj_id):
        raise ConnectionError("redis down")

    app.dependency_overrides[get_practice_enqueuer] = lambda: broken
    r = await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")
    assert r.status_code == 503
    body = (await auth_client.get(f"/api/practice/{paper.id}")).json()
    assert (body["status"], body["partial"], body["sources_done"], body["error"]) == ("done", True, 3, None)
    assert body["last_replace_failed_item"] == items[1].id
    assert [i["stem"] for i in body["items"]] == ["旧题0", "旧题1"]


async def test_stale_cutoffs_running_vs_queued(db, auth_client, my_assignment, practice_enqueued, settings):
    from app.practice.jobs import stale_after_queued, stale_after_running

    assert stale_after_running() == timedelta(seconds=3 * settings.MODEL_TIMEOUT_S)
    await build_sources(db, my_assignment)
    paper_id = (await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")).json()["id"]
    paper = await db.get(PracticePaper, paper_id)
    quiet = stale_after_running() + timedelta(seconds=30)
    assert quiet < stale_after_queued()

    # Queued that long: still waiting for the worker, not stale yet.
    paper.updated_at = utcnow() - quiet
    await db.commit()
    assert (await auth_client.get(f"/api/practice/{paper_id}")).json()["status"] == "queued"

    # Running with no progress for that long: the job is gone.
    paper.status = "running"
    await db.commit()
    paper.updated_at = utcnow() - quiet
    await db.commit()
    assert (await auth_client.get(f"/api/practice/{paper_id}")).json()["status"] == "failed"

    # Running with recent progress is left alone.
    paper.status = "running"
    await db.commit()
    assert (await auth_client.get(f"/api/practice/{paper_id}")).json()["status"] == "running"


async def test_stuck_replacing_item_expires(db, auth_client, my_assignment, practice_enqueued):
    from app.practice.jobs import stale_after_running

    await build_sources(db, my_assignment)
    paper_id = (await auth_client.post(f"/api/assignments/{my_assignment.id}/practice")).json()["id"]
    paper = await db.get(PracticePaper, paper_id)
    paper.status = "done"
    await db.commit()
    items = await _add_items(db, paper_id)
    for it in items:
        it.replacing = True
    await db.commit()
    items[0].updated_at = utcnow() - stale_after_running() - timedelta(seconds=30)  # its job died
    await db.commit()

    body = (await auth_client.get(f"/api/practice/{paper_id}")).json()
    assert [i["replacing"] for i in body["items"]] == [False, True]  # the live one is untouched
    assert body["last_replace_failed_item"] == items[0].id
    # The expired item can be replaced again.
    r = await auth_client.post(f"/api/practice-items/{items[0].id}/replace")
    assert r.status_code == 202 and practice_enqueued[-1] == ("practice_replace_job", items[0].id)
