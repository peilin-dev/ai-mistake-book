from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, StringConstraints, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classes.access import own_class
from app.classes.roster import parse_roster
from app.deps import current_teacher, get_db
from app.models import Class_, Student, Teacher

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
):
    cls = await own_class(db, teacher, class_id)
    await db.delete(cls)
    await db.commit()
    return Response(status_code=204)
