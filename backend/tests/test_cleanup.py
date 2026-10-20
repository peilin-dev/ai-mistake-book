import logging
from datetime import timedelta

from sqlalchemy import select

from app.jobs import cleanup
from app.jobs.cleanup import purge_old_originals
from app.models import Page, PageStatus
from tests.conftest import storage_exists, utcnow


async def _deleted_at(db, page_id):
    db.expire_all()
    return (await db.execute(select(Page.original_deleted_at).where(Page.id == page_id))).scalar_one()


async def test_purges_only_old_originals_keeps_crops(db, storage, page_factory):
    old = await page_factory(created_days_ago=31, with_crop=True)
    new = await page_factory(created_days_ago=5)
    now = utcnow().replace(microsecond=0)  # DATETIME column has second precision
    n = await purge_old_originals(db, storage, now=now, retention_days=30)
    assert n == 1
    assert not await storage_exists(storage, old.image_key)
    assert await storage_exists(storage, old.crop_keys[0])
    assert await storage_exists(storage, new.image_key)
    assert await _deleted_at(db, old.id) == now
    assert await _deleted_at(db, new.id) is None
    assert await purge_old_originals(db, storage, now=utcnow(), retention_days=30) == 0


async def test_boundary_is_strictly_older_than_retention(db, storage, page_factory):
    just_inside = await page_factory(created_days_ago=30 - 1 / 1440)  # 29d 23h 59m
    just_outside = await page_factory(created_days_ago=30 + 1 / 1440)  # 30d 1m
    assert await purge_old_originals(db, storage, now=utcnow(), retention_days=30) == 1
    assert await storage_exists(storage, just_inside.image_key)
    assert not await storage_exists(storage, just_outside.image_key)


async def test_purges_across_teachers_regardless_of_status(db, storage, page_factory):
    a = await page_factory(created_days_ago=40)
    b = await page_factory(created_days_ago=60, status=PageStatus.failed)
    c = await page_factory(created_days_ago=90, with_crop=True)
    assert await purge_old_originals(db, storage, now=utcnow(), retention_days=30) == 3
    for p in (a, b, c):
        assert not await storage_exists(storage, p.image_key)


async def test_storage_failure_skips_page_and_continues(db, storage, page_factory, caplog):
    bad = await page_factory(created_days_ago=40)
    good = await page_factory(created_days_ago=41)
    real_delete = storage.delete

    async def flaky(key):
        if key == bad.image_key:
            raise OSError("disk exploded")
        await real_delete(key)

    storage.delete = flaky
    with caplog.at_level(logging.WARNING):
        n = await purge_old_originals(db, storage, now=utcnow(), retention_days=30)
    assert n == 1
    assert await _deleted_at(db, bad.id) is None
    assert await _deleted_at(db, good.id) is not None
    assert not await storage_exists(storage, good.image_key)
    assert str(bad.id) in caplog.text
    assert bad.image_key not in caplog.text
    # Retried on the next run once storage recovers.
    storage.delete = real_delete
    assert await purge_old_originals(db, storage, now=utcnow(), retention_days=30) == 1
    assert await _deleted_at(db, bad.id) is not None


async def test_processes_in_batches(db, storage, page_factory, monkeypatch):
    monkeypatch.setattr(cleanup, "BATCH_SIZE", 2)
    pages = [await page_factory(created_days_ago=31) for _ in range(5)]
    assert await purge_old_originals(db, storage, now=utcnow(), retention_days=30) == 5
    for p in pages:
        assert not await storage_exists(storage, p.image_key)
        assert await _deleted_at(db, p.id) is not None


async def test_batches_do_not_loop_forever_on_persistent_failure(db, storage, page_factory, monkeypatch):
    monkeypatch.setattr(cleanup, "BATCH_SIZE", 2)
    pages = [await page_factory(created_days_ago=31) for _ in range(5)]

    async def boom(key):
        raise OSError("down")

    storage.delete = boom
    assert await purge_old_originals(db, storage, now=utcnow(), retention_days=30) == 0
    assert all([await _deleted_at(db, p.id) is None for p in pages])


async def test_cron_entry_is_daily_0300_shanghai():
    from zoneinfo import ZoneInfo

    from app.jobs.worker import WorkerSettings, purge_originals_job

    jobs = [j for j in WorkerSettings.cron_jobs if j.coroutine is purge_originals_job]
    assert len(jobs) == 1
    job = jobs[0]
    assert job.hour == 3 and job.minute == 0 and job.second == 0
    assert job.month is None and job.day is None and job.weekday is None
    assert WorkerSettings.timezone == ZoneInfo("Asia/Shanghai")


async def test_purge_originals_job_uses_ctx_and_settings(db, storage, page_factory, settings):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.jobs.worker import purge_originals_job

    settings.ORIGINAL_RETENTION_DAYS = 10
    old = await page_factory(created_days_ago=11)
    new = await page_factory(created_days_ago=9)
    ctx = {"sessionmaker": async_sessionmaker(db.bind, expire_on_commit=False), "storage": storage}
    await purge_originals_job(ctx)
    assert not await storage_exists(storage, old.image_key)
    assert await storage_exists(storage, new.image_key)


