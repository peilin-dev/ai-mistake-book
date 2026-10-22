"""arq worker: `arq app.jobs.worker.WorkerSettings`."""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from arq import Retry, cron, func
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.base import ModelCallError
from app.ai.registry import get_model
from app.config import get_settings
from app.db import make_engine
from app.assignments.router import grade_job_id
from app.export.service import purge_old_exports
from app.jobs.cleanup import purge_old_originals
from app.jobs.requeue import STALE_AFTER, stale_queued_pages
from app.grading.pipeline import grade_page, set_page_status
from app.models import PageStatus
from app.practice.jobs import (
    paper_job_timeout_s,
    practice_paper_job,
    practice_replace_job,
    replace_job_timeout_s,
)
from app.storage.base import get_storage

log = logging.getLogger(__name__)
MAX_TRIES = 3
RETRY_DELAY_S = 10


async def grade_page_job(ctx: dict, page_id: int) -> None:
    async with ctx["sessionmaker"]() as db:
        try:
            await grade_page(db, ctx["storage"], ctx["model"], page_id)
        except ModelCallError:
            job_try = ctx.get("job_try", 1)
            if job_try < MAX_TRIES:
                # arq only re-runs a job that raises Retry; other exceptions fail it for good.
                raise Retry(defer=RETRY_DELAY_S * job_try) from None
            await set_page_status(db, page_id, PageStatus.failed, "model_unavailable")


async def purge_originals_job(ctx: dict) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, like created_at
    async with ctx["sessionmaker"]() as db:
        await purge_old_originals(db, ctx["storage"], now, get_settings().ORIGINAL_RETENTION_DAYS)


async def purge_exports_job(ctx: dict) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with ctx["sessionmaker"]() as db:
        await purge_old_exports(db, ctx["storage"], now)


async def requeue_stale_job(ctx: dict) -> None:
    """Re-enqueue pages stuck in queued (e.g. enqueue hit 503 and nobody resent them)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with ctx["sessionmaker"]() as db:
        stale = await stale_queued_pages(db, now, STALE_AFTER)
    for page_id, retry in stale:
        # Same job id as the original enqueue: arq ignores it if that job still exists.
        await ctx["redis"].enqueue_job("grade_page_job", page_id, _job_id=grade_job_id(page_id, retry))


async def startup(ctx: dict) -> None:
    engine = make_engine(get_settings().DATABASE_URL)
    ctx["engine"] = engine
    ctx["sessionmaker"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["storage"] = get_storage()
    ctx["model"] = get_model("grading")
    try:
        ctx["practice_generate_model"] = get_model("practice_generate")
        ctx["practice_verify_model"] = get_model("practice_verify")
    except ValueError:
        # A practice misconfiguration must not stop grading; practice jobs then mark their paper failed.
        log.exception("practice models are not configured")
        ctx["practice_generate_model"] = ctx["practice_verify_model"] = None


async def shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = [
        grade_page_job,
        # No arq retries: a paper job already retries per source; a failure marks the paper failed.
        func(practice_paper_job, timeout=paper_job_timeout_s(), max_tries=1),
        func(practice_replace_job, timeout=replace_job_timeout_s(), max_tries=1),
    ]
    cron_jobs = [
        cron(purge_originals_job, hour=3, minute=0, second=0),
        cron(purge_exports_job, hour=3, minute=30, second=0),
        cron(requeue_stale_job, second=0, run_at_startup=True),  # every minute, and once at startup
    ]
    timezone = ZoneInfo("Asia/Shanghai")  # cron times are evaluated in this zone
    max_tries = MAX_TRIES
    # Two model attempts plus image work and DB writes must fit in one job.
    job_timeout = 2 * get_settings().MODEL_TIMEOUT_S + 60
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().REDIS_URL)

