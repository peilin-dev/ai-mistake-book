import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, StringConstraints, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classes.access import own_class
from app.classes.roster import parse_roster
from app.deps import current_teacher, get_db
from app.models import Assignment, Class_, Page, QuestionResult, Student, Teacher
from app.storage.base import Storage, get_storage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/classes", tags=["classes"])


class ClassIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    grade: int = Field(ge=1, le=12)


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    grade: int


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    student_no: str | None


class ImportIn(BaseModel):
    text: str


class ImportOut(BaseModel):
    created: int
    students: list[StudentOut]


async def _roster(class_id: int, db: AsyncSession) -> list[Student]:
    result = await db.execute(
        select(Student).where(Student.class_id == class_id).order_by(Student.id)
    )
    return list(result.scalars())


@router.post("", response_model=ClassOut, status_code=201)
async def create_class(
    body: ClassIn,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    cls = Class_(teacher_id=teacher.id, name=body.name, grade=body.grade)
    db.add(cls)
    await db.commit()
    return cls


@router.get("", response_model=list[ClassOut])
async def list_classes(
    teacher: Teacher = Depends(current_teacher), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Class_).where(Class_.teacher_id == teacher.id).order_by(Class_.id)
    )
    return list(result.scalars())


@router.post("/{class_id}/students:import", response_model=ImportOut)
async def import_students(
    class_id: int,
    body: ImportIn,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    await own_class(db, teacher, class_id)
    existing = {(s.name, s.student_no) for s in await _roster(class_id, db)}
    created = 0
    for entry in parse_roster(body.text):
        if (entry.name, entry.student_no) in existing:
            continue
        db.add(Student(class_id=class_id, name=entry.name, student_no=entry.student_no))
        created += 1
    await db.commit()
    return ImportOut(created=created, students=await _roster(class_id, db))


@router.get("/{class_id}/students", response_model=list[StudentOut])
async def list_students(
    class_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    await own_class(db, teacher, class_id)
    return await _roster(class_id, db)


@router.delete("/{class_id}", status_code=204)
async def delete_class(
    class_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    cls = await own_class(db, teacher, class_id)
    pages = (
        select(Page.id).join(Assignment, Assignment.id == Page.assignment_id)
        .where(Assignment.class_id == class_id)
    )
    originals = (await db.execute(
        select(Page.id, Page.image_key).where(Page.id.in_(pages), Page.original_deleted_at.is_(None))
    )).all()
    crops = (await db.execute(
        select(QuestionResult.id, QuestionResult.crop_key)
        .where(QuestionResult.page_id.in_(pages), QuestionResult.crop_key.is_not(None))
    )).all()
    await db.delete(cls)
    await db.commit()  # rows cascade; files are removed best-effort afterwards
    for kind, files in (("page", originals), ("question_result", crops)):
        for row_id, key in files:
            try:
                await storage.delete(key)
            except Exception:
                log.warning("delete_class %s: failed to delete file of %s %s", class_id, kind, row_id)
    return Response(status_code=204)
