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
    assert len(enqueued) == 1


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


async def test_files_route_rejects_traversal(client, storage):
    r = await client.get("/api/files/a/..%2f..%2fsecret?expires=9999999999&sig=x")
    assert r.status_code in (400, 403)
    assert storage.signed_url("x") .startswith("/api/files/x?expires=")


async def test_local_storage_missing_key(storage):
    with pytest.raises(FileNotFoundError):
        await storage.get("nope.jpg")
    await storage.delete("nope.jpg")  # no-op
    await storage.put("d/e.bin", b"1", "x")
    await storage.delete("d/e.bin")
    with pytest.raises(FileNotFoundError):
        await storage.get("d/e.bin")