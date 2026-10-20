"""arq worker: `arq app.jobs.worker.WorkerSettings`."""
from arq import Retry
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.base import ModelCallError
from app.ai.registry import get_model
from app.config import get_settings
from app.db import make_engine
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
    max_tries = MAX_TRIES
    # Two model attempts plus image work and DB writes must fit in one job.
    job_timeout = 2 * get_settings().MODEL_TIMEOUT_S + 60
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().REDIS_URL)
