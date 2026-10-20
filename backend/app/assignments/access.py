from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment, Class_, Teacher


async def own_assignment(db: AsyncSession, teacher: Teacher, assignment_id: int) -> Assignment:
    """Resolve assignment -> class -> teacher; 404 for missing or foreign assignments."""
    a = (
        await db.execute(
            select(Assignment)
            .join(Class_, Class_.id == Assignment.class_id)
            .where(Assignment.id == assignment_id, Class_.teacher_id == teacher.id)
        )
    ).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="assignment not found")
    return a
