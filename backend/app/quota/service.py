from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Assignment, Class_, Page

SHANGHAI = ZoneInfo("Asia/Shanghai")


class QuotaExceeded(Exception):
    pass


def month_bounds_utc(now_utc: datetime | None = None) -> tuple[datetime, datetime]:
    """[start, end) of the current Asia/Shanghai natural month, as naive UTC."""
    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    local = now_utc.replace(tzinfo=timezone.utc).astimezone(SHANGHAI)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)

    def to_naive_utc(d: datetime) -> datetime:
        return d.astimezone(timezone.utc).replace(tzinfo=None)

    return to_naive_utc(start), to_naive_utc(end)


async def pages_used_this_month(
    db: AsyncSession, teacher_id: int, now: datetime | None = None
) -> int:
    start, end = month_bounds_utc(now)
    return (
        await db.execute(
            select(func.count(Page.id))
            .join(Assignment, Assignment.id == Page.assignment_id)
            .join(Class_, Class_.id == Assignment.class_id)
            .where(Class_.teacher_id == teacher_id, Page.created_at >= start, Page.created_at < end)
        )
    ).scalar_one()


async def check_quota(db: AsyncSession, teacher_id: int) -> None:
    if await pages_used_this_month(db, teacher_id) >= get_settings().MONTHLY_PAGE_QUOTA:
        raise QuotaExceeded()