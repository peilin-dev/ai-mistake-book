from datetime import timedelta

from sqlalchemy import update

from app.jobs.requeue import STALE_AFTER, stale_queued_pages
from app.models import Page, PageStatus
from tests.conftest import utcnow


async def _age(db, page_id: int, minutes: float) -> None:
    """Set both timestamps; a plain ORM update would bump updated_at to now."""
    t = utcnow() - timedelta(minutes=minutes)
    await db.execute(update(Page).where(Page.id == page_id).values(created_at=t, updated_at=t))
    await db.commit()


async def test_picks_only_stale_queued_pages(db, page_factory):
    stale = await page_factory(created_days_ago=0, status=PageStatus.queued, retry_count=2)
    fresh = await page_factory(created_days_ago=0, status=PageStatus.queued)
    done = await page_factory(created_days_ago=0, status=PageStatus.done)
    failed = await page_factory(created_days_ago=0, status=PageStatus.failed)
    processing = await page_factory(created_days_ago=0, status=PageStatus.processing)
    await _age(db, stale.id, 3)
    await _age(db, fresh.id, 1)
    for p in (done, failed, processing):
        await _age(db, p.id, 10)
    got = await stale_queued_pages(db, utcnow(), timedelta(minutes=2))
    assert got == [(stale.id, 2)]


async def test_recent_update_counts_as_fresh(db, page_factory):
    p = await page_factory(created_days_ago=1, status=PageStatus.queued)
    t_old = utcnow() - timedelta(days=1)
    await db.execute(update(Page).where(Page.id == p.id).values(created_at=t_old, updated_at=utcnow()))
    await db.commit()
    assert await stale_queued_pages(db, utcnow(), timedelta(minutes=2)) == []


async def test_requeue_job_enqueues_with_grade_job_id(db, page_factory):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.jobs.worker import requeue_stale_job

    a = await page_factory(created_days_ago=0, status=PageStatus.queued)
    b = await page_factory(created_days_ago=0, status=PageStatus.queued, retry_count=1)
    await _age(db, a.id, 5)
    await _age(db, b.id, 5)

    calls = []

    class FakeRedis:
        async def enqueue_job(self, fn, *args, _job_id=None):
            calls.append((fn, args, _job_id))
            return None  # arq returns None when the job id already exists

    ctx = {"sessionmaker": async_sessionmaker(db.bind, expire_on_commit=False), "redis": FakeRedis()}
    await requeue_stale_job(ctx)
    assert sorted(calls) == sorted([
        ("grade_page_job", (a.id,), f"grade:{a.id}"),
        ("grade_page_job", (b.id,), f"grade:{b.id}:1"),
    ])


async def test_cron_runs_every_minute_and_at_startup():
    from app.jobs.worker import WorkerSettings, requeue_stale_job

    jobs = [j for j in WorkerSettings.cron_jobs if j.coroutine is requeue_stale_job]
    assert len(jobs) == 1
    job = jobs[0]
    assert job.minute is None and job.hour is None and job.second == 0
    assert job.run_at_startup is True
    assert STALE_AFTER == timedelta(minutes=2)
