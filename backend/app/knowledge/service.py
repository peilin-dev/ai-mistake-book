from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgePoint


async def candidates(db: AsyncSession, subject: str, grade: int) -> list[KnowledgePoint]:
    """Leaf knowledge points of `subject` whose grade range contains `grade`, by code."""
    child = KnowledgePoint.__table__.alias("child")
    has_child = select(child.c.id).where(child.c.parent_id == KnowledgePoint.id).exists()
    stmt = (
        select(KnowledgePoint)
        .where(
            KnowledgePoint.subject == subject,
            KnowledgePoint.grade_min <= grade,
            KnowledgePoint.grade_max >= grade,
            ~has_child,
        )
        .order_by(KnowledgePoint.code)
    )
    return list((await db.execute(stmt)).scalars())
