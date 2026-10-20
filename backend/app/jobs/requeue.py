"""Safety net: a page left `queued` with no arq job (enqueue failed with 503 and the
client's resend never happened) is re-enqueued by a worker cron.

Re-enqueueing uses the same job id as the original (grade_job_id(page_id, retry_count)),
so a page whose job is still waiting in Redis is not graded twice.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Page, PageStatus

STALE_AFTER = timedelta(minutes=2)


async def stale_queued_pages(db: AsyncSession, now: datetime, older_than: timedelta) -> list[tuple[int, int]]:
    """(page_id, retry_count) of queued pages not touched since now - older_than (naive UTC)."""
    cutoff = now - older_than
    rows = await db.execute(
        select(Page.id, Page.retry_count)
        .where(Page.status == PageStatus.queued, Page.updated_at < cutoff)
        .order_by(Page.id)
    )
    return [(pid, retry) for pid, retry in rows.all()]
