"""arq worker: `arq app.jobs.worker.WorkerSettings`."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from arq import Retry, cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.base import ModelCallError
from app.ai.registry import get_model
from app.config import get_settings
from app.db import make_engine
from app.jobs.cleanup import purge_old_originals
from app.grading.pipeline import grade_page, set_page_status
from app.models import PageStatus
from app.storage.base import get_storage

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


async def startup(ctx: dict) -> None:
    engine = make_engine(get_settings().DATABASE_URL)
    ctx["engine"] = engine
    ctx["sessionmaker"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["storage"] = get_storage()
    ctx["model"] = get_model("grading")


async def shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = [grade_page_job]
    cron_jobs = [cron(purge_originals_job, hour=3, minute=0, second=0)]
    timezone = ZoneInfo("Asia/Shanghai")  # cron times are evaluated in this zone
    max_tries = MAX_TRIES
    # Two model attempts plus image work and DB writes must fit in one job.
    job_timeout = 2 * get_settings().MODEL_TIMEOUT_S + 60
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().REDIS_URL)

