import asyncio
from datetime import datetime

import httpx
import pytest
from sqlalchemy import select

from app.models import Page
from app.quota.service import month_bounds_utc, pages_used_this_month
from app.storage.local import LocalStorage


def url_of(a):
    return f"/api/assignments/{a.id}/pages"


async def test_upload_queues_page(auth_client, my_assignment, jpeg_bytes, enqueued, storage, teacher):
    r = await auth_client.post(url_of(my_assignment),
                               files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    body = r.json()
    assert r.status_code == 201 and body["status"] == "queued" and body["duplicate"] is False
    assert body["seq"] == 1
    assert enqueued == [body["page_id"]]
    key = f"originals/{teacher.id}/{my_assignment.id}/{body['page_id']}.jpg"
    assert await storage.get(key) == jpeg_bytes


async def test_seq_increments(auth_client, my_assignment, make_jpeg, enqueued, storage):
    seqs = []
    for n in (1, 2, 3):
        r = await auth_client.post(url_of(my_assignment),
                                   files={"file": ("a.jpg", make_jpeg(n), "image/jpeg")})
        seqs.append(r.json()["seq"])
    assert seqs == [1, 2, 3]


async def test_duplicate_upload_returns_existing_page(auth_client, my_assignment, jpeg_bytes, enqueued, storage):
    url = url_of(my_assignment)
    a = (await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})).json()
    r = await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    b = r.json()
    assert r.status_code == 200
    assert b["page_id"] == a["page_id"] and b["duplicate"] is True
    assert enqueued == [a["page_id"], a["page_id"]]  # still queued -> re-enqueued (idempotent job id)


async def test_duplicate_skips_quota_check(auth_client, my_assignment, jpeg_bytes, settings, enqueued, storage):
    settings.MONTHLY_PAGE_QUOTA = 1
    url = url_of(my_assignment)
    await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    r = await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert r.status_code == 200 and r.json()["duplicate"] is True


async def test_upload_over_quota_returns_429(auth_client, my_assignment, settings, make_jpeg, enqueued, storage):
    settings.MONTHLY_PAGE_QUOTA = 1
    url = url_of(my_assignment)
    await auth_client.post(url, files={"file": ("a.jpg", make_jpeg(1), "image/jpeg")})
    r = await auth_client.post(url, files={"file": ("b.jpg", make_jpeg(2), "image/jpeg")})
    assert r.status_code == 429
    assert r.json()["detail"] == "本月批改额度已用完"
    assert len(enqueued) == 1


async def test_rejects_non_image_and_oversize(auth_client, my_assignment, enqueued, storage):
    url = url_of(my_assignment)
    assert (await auth_client.post(url, files={"file": ("a.txt", b"hi", "text/plain")})).status_code == 415
    # client claims image/jpeg but magic bytes say otherwise
    assert (await auth_client.post(url, files={"file": ("a.jpg", b"not an image", "image/jpeg")})).status_code == 415
    big = b"\xff\xd8\xff" + b"0" * (10 * 1024 * 1024 + 1)
    assert (await auth_client.post(url, files={"file": ("a.jpg", big, "image/jpeg")})).status_code == 413
    exact = b"\xff\xd8\xff" + b"0" * (10 * 1024 * 1024 - 3)
    assert (await auth_client.post(url, files={"file": ("a.jpg", exact, "image/jpeg")})).status_code == 201


async def test_png_and_heic_accepted_by_magic_bytes(auth_client, my_assignment, enqueued, storage, teacher):
    url = url_of(my_assignment)
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    heic = b"\x00\x00\x00\x18ftypheic" + b"x" * 20
    keys = []
    for name, data in (("a.bin", png), ("b.bin", heic)):
        r = await auth_client.post(url, files={"file": (name, data, "application/octet-stream")})
        assert r.status_code == 201
        keys.append(r.json()["page_id"])
    assert await storage.get(f"originals/{teacher.id}/{my_assignment.id}/{keys[0]}.png") == png
    assert await storage.get(f"originals/{teacher.id}/{my_assignment.id}/{keys[1]}.heic") == heic


async def test_foreign_assignment_404(client_for, make_teacher, my_assignment, jpeg_bytes, enqueued, storage):
    other = await make_teacher()
    r = await client_for(other).post(url_of(my_assignment),
                                     files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert r.status_code == 404


async def test_storage_failure_leaves_no_page(auth_client, my_assignment, jpeg_bytes, enqueued, app, db):
    from app.storage.base import get_storage

    class Broken:
        async def put(self, *a, **k):
            raise OSError("disk full")

    app.dependency_overrides[get_storage] = lambda: Broken()
    with pytest.raises(OSError):
        await auth_client.post(url_of(my_assignment),
                               files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    await db.rollback()
    assert (await db.execute(select(Page))).first() is None
    assert enqueued == []


async def test_quota_month_boundary_is_shanghai(db, my_assignment, teacher):
    # 2026-10-31 16:30 UTC == 2026-11-01 00:30 Shanghai -> November
    db.add(Page(assignment_id=my_assignment.id, seq=1, image_key="k", image_sha256="a" * 64,
                created_at=datetime(2026, 10, 31, 16, 30)))
    db.add(Page(assignment_id=my_assignment.id, seq=2, image_key="k", image_sha256="b" * 64,
                created_at=datetime(2026, 10, 31, 15, 59)))
    await db.commit()
    nov = datetime(2026, 11, 15, 4, 0)  # UTC, Nov 15 Shanghai
    octo = datetime(2026, 10, 15, 4, 0)
    assert month_bounds_utc(nov) == (datetime(2026, 10, 31, 16, 0), datetime(2026, 11, 30, 16, 0))
    assert await pages_used_this_month(db, teacher.id, now=nov) == 1
    assert await pages_used_this_month(db, teacher.id, now=octo) == 1


async def test_signed_url_roundtrip(client, storage):
    await storage.put("originals/1/2/3.jpg", b"DATA", "image/jpeg")
    url = storage.signed_url("originals/1/2/3.jpg")
    r = await client.get(url)
    assert r.status_code == 200 and r.content == b"DATA"


async def test_signed_url_tampered_or_expired_403(client, storage):
    await storage.put("a/b.jpg", b"DATA", "image/jpeg")
    url = storage.signed_url("a/b.jpg")
    assert (await client.get(url[:-1] + ("0" if url[-1] != "0" else "1"))).status_code == 403
    assert (await client.get(url.replace("a/b.jpg", "a/c.jpg"))).status_code == 403
    assert (await client.get(storage.signed_url("a/b.jpg", expires_s=-5))).status_code == 403
    assert (await client.get("/api/files/a/b.jpg")).status_code in (403, 422)


@pytest.mark.parametrize("raw", ["..%2Fx", "C:/x", "a%5C..%5Cb", "a/..%2F..%2Fsecret"])
async def test_files_route_rejects_unsafe_keys_400(client, storage, raw):
    r = await client.get(f"/api/files/{raw}?expires=9999999999&sig=x")
    assert r.status_code == 400


@pytest.mark.parametrize("key", ["../x", "C:/x", "C:foo", "a\\..\\b", "/abs", "a/../../b"])
async def test_local_storage_rejects_unsafe_keys(storage, key):
    with pytest.raises(ValueError):
        await storage.put(key, b"1", "x")
    with pytest.raises(ValueError):
        await storage.get(key)


async def test_concurrent_duplicate_race_returns_existing(
    auth_client, my_assignment, jpeg_bytes, enqueued, storage, db, monkeypatch
):
    """A competing identical upload lands after our dedupe lookup missed."""
    import hashlib

    import app.assignments.router as router_mod

    winner = {}

    async def racing_check_quota(db_, teacher_id):
        p = Page(assignment_id=my_assignment.id, seq=1, image_key="k",
                 image_sha256=hashlib.sha256(jpeg_bytes).hexdigest())
        db_.add(p)
        await db_.commit()
        winner["id"] = p.id

    monkeypatch.setattr(router_mod, "check_quota", racing_check_quota)
    r = await auth_client.post(url_of(my_assignment),
                               files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert r.status_code == 200
    assert r.json()["duplicate"] is True and r.json()["page_id"] == winner["id"]
    assert enqueued == [winner["id"]]  # winner is still queued

async def test_local_storage_missing_key(storage):
    with pytest.raises(FileNotFoundError):
        await storage.get("nope.jpg")
    await storage.delete("nope.jpg")  # no-op
    await storage.put("d/e.bin", b"1", "x")
    await storage.delete("d/e.bin")
    with pytest.raises(FileNotFoundError):
        await storage.get("d/e.bin")

async def test_concurrent_uploads_get_distinct_seqs(app, settings, my_assignment, teacher,
                                                    make_jpeg, enqueued, storage, db):
    """Two uploads racing on separate sessions must not share a seq."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.auth.tokens import issue_token
    from app.db import make_engine
    from app.deps import get_db

    engine = make_engine(settings.DATABASE_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def per_request_db():
        async with sessions() as s:
            yield s

    app.dependency_overrides[get_db] = per_request_db
    headers = {"Authorization": f"Bearer {issue_token(teacher.id)}"}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                     headers=headers) as c1, \
                httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                  headers=headers) as c2:
            r1, r2 = await asyncio.gather(
                c1.post(url_of(my_assignment), files={"file": ("a.jpg", make_jpeg(1), "image/jpeg")}),
                c2.post(url_of(my_assignment), files={"file": ("b.jpg", make_jpeg(2), "image/jpeg")}),
            )
    finally:
        await engine.dispose()
    assert (r1.status_code, r2.status_code) == (201, 201)
    assert sorted([r1.json()["seq"], r2.json()["seq"]]) == [1, 2]


def test_page_seq_is_unique_per_assignment():
    names = {c.name for c in Page.__table__.constraints}
    assert "uq_page_assignment_seq" in names


# --- Task 10 fix: enqueue failures and queued duplicates ---

@pytest.fixture
def failing_enqueue(app) -> list[int]:
    calls: list[int] = []

    async def _enqueue(page_id: int) -> None:
        calls.append(page_id)
        raise ConnectionError("redis down")

    from app.assignments.router import get_enqueuer
    app.dependency_overrides[get_enqueuer] = lambda: _enqueue
    return calls


async def test_enqueue_failure_returns_503_and_keeps_page(auth_client, my_assignment, jpeg_bytes,
                                                          failing_enqueue, storage, db):
    r = await auth_client.post(url_of(my_assignment), files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert r.status_code == 503 and r.json()["detail"] == "批改队列暂不可用，请稍后重试"
    page = (await db.execute(select(Page))).scalar_one()
    assert page.status == "queued" and failing_enqueue == [page.id]


async def test_retry_after_enqueue_failure_reenqueues(app, auth_client, my_assignment, jpeg_bytes,
                                                      failing_enqueue, storage):
    url = url_of(my_assignment)
    assert (await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})).status_code == 503
    calls: list[int] = []

    async def _enqueue(page_id: int) -> None:
        calls.append(page_id)

    from app.assignments.router import get_enqueuer
    app.dependency_overrides[get_enqueuer] = lambda: _enqueue
    r = await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert r.status_code == 200 and r.json()["duplicate"] is True
    assert calls == [r.json()["page_id"]]


async def test_duplicate_of_queued_page_503_when_queue_down(auth_client, my_assignment, jpeg_bytes,
                                                            failing_enqueue, storage):
    url = url_of(my_assignment)
    await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    r = await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert r.status_code == 503 and len(failing_enqueue) == 2


async def test_duplicate_of_processed_page_not_reenqueued(auth_client, my_assignment, jpeg_bytes,
                                                          enqueued, storage, db):
    url = url_of(my_assignment)
    a = (await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})).json()
    page = await db.get(Page, a["page_id"])
    page.status = "done"
    await db.commit()
    r = await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert r.status_code == 200 and r.json()["status"] == "done"
    assert enqueued == [a["page_id"]]

# --- final review fix 6: retry of failed pages ---

class _Pool:
    def __init__(self) -> None:
        self.job_ids: list[str] = []

    async def enqueue_job(self, name, *args, _job_id=None):
        self.job_ids.append(_job_id)


async def _fail(db, page_id, reason):
    page = await db.get(Page, page_id)
    page.status, page.fail_reason = "failed", reason
    await db.commit()


@pytest.mark.parametrize("reason", ["model_unavailable", "internal_error"])
async def test_duplicate_of_retryable_failed_page_requeues_with_fresh_job_id(
        app, auth_client, my_assignment, jpeg_bytes, storage, db, reason):
    pool = _Pool()
    app.state.arq_pool = pool
    url = url_of(my_assignment)
    pid = (await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})).json()["page_id"]
    for n in (1, 2):
        await _fail(db, pid, reason)
        r = await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
        assert r.status_code == 200
        assert r.json() == {"page_id": pid, "seq": 1, "status": "queued", "duplicate": True}
        db.expire_all()
        page = await db.get(Page, pid)
        assert (page.status, page.fail_reason) == ("queued", None)
    # a queued retry whose enqueue may have failed is re-enqueued under the same id
    await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert pool.job_ids == [f"grade:{pid}", f"grade:{pid}:1", f"grade:{pid}:2", f"grade:{pid}:2"]


async def test_duplicate_of_unreadable_page_is_not_retried(auth_client, my_assignment, jpeg_bytes,
                                                           enqueued, storage, db):
    url = url_of(my_assignment)
    pid = (await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})).json()["page_id"]
    await _fail(db, pid, "unreadable")
    r = await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert r.json()["status"] == "failed" and enqueued == [pid]


# --- final review fix 7: non-ASCII signature ---

async def test_non_ascii_signature_is_403(client, storage):
    await storage.put("a/b.jpg", b"DATA", "image/jpeg")
    r = await client.get("/api/files/a/b.jpg", params={"expires": 9999999999, "sig": "签名"})
    assert r.status_code == 403
