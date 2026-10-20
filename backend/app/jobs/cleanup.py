"""Privacy: original photos of (minors') papers are deleted after the retention period.

Crops are kept; only Page.image_key objects are removed.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Page
from app.storage.base import Storage

logger = logging.getLogger(__name__)

BATCH_SIZE = 200


async def purge_old_originals(
    db: AsyncSession, storage: Storage, now: datetime, retention_days: int
) -> int:
    """Delete originals of pages created before now - retention_days; return how many.

    `now` is naive UTC, like created_at. A page whose storage delete fails keeps
    original_deleted_at NULL so the next run retries it.
    """
    cutoff = now - timedelta(days=retention_days)
    purged = 0
    last_id = 0  # keyset paging: failed pages stay NULL and must not be re-selected forever
    while True:
        rows = (
            await db.execute(
                select(Page)
                .where(
                    Page.created_at < cutoff,
                    Page.original_deleted_at.is_(None),
                    Page.id > last_id,
                )
                .order_by(Page.id)
                .limit(BATCH_SIZE)
            )
        ).scalars().all()
        if not rows:
            return purged
        for page in rows:
            last_id = page.id
            try:
                await storage.delete(page.image_key)
            except Exception:
                logger.warning("failed to delete original for page %s; will retry", page.id, exc_info=False)
                continue
            page.original_deleted_at = now
            purged += 1
        await db.commit()
