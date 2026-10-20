from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Class_, Teacher


async def own_class(db: AsyncSession, teacher: Teacher, class_id: int) -> Class_:
    """Resolve a class owned by `teacher`; 404 for missing or foreign classes."""
    cls = (
        await db.execute(
            select(Class_).where(Class_.id == class_id, Class_.teacher_id == teacher.id)
        )
    ).scalar_one_or_none()
    if cls is None:
        raise HTTPException(status_code=404, detail="class not found")
    return cls