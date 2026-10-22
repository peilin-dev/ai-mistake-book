"""Export PDFs (lecture sheet, mistake sheets) for the teacher."""
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.stats import load_student_results
from app.assignments.access import own_assignment
from app.deps import current_teacher, get_db
from app.export.service import NothingToExport, build_export, build_practice_export, store_export
from app.models import Submission, Teacher
from app.storage.base import Storage, get_storage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["export"])

LINK_TTL_S = 600


class ExportIn(BaseModel):
    kind: Literal["lecture", "student", "class_students", "practice", "practice_student"]
    submission_id: int | None = None
    include_answers: bool = True


@router.post("/assignments/{assignment_id}/exports", status_code=201)
async def create_export(
    assignment_id: int,
    body: ExportIn,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> dict:
    assignment = await own_assignment(db, teacher, assignment_id)
    results = []
    practice_student_id = None
    if body.kind in ("student", "practice_student"):
        if body.submission_id is None:
            raise HTTPException(422, "submission_id required")
        sub = (await db.execute(
            select(Submission).where(Submission.id == body.submission_id,
                                     Submission.assignment_id == assignment_id)
        )).scalar_one_or_none()
        if sub is None:
            raise HTTPException(404, "submission not found")
        if body.kind == "student":
            results = await load_student_results(db, assignment_id, sub.student_id)
        else:
            practice_student_id = sub.student_id
    elif body.kind == "class_students":
        results = await load_student_results(db, assignment_id)
    try:
        if body.kind in ("practice", "practice_student"):
            pdf, filename = await build_practice_export(
                db, teacher, assignment, practice_student_id, body.include_answers)
        else:
            pdf, filename = await build_export(db, storage, teacher, assignment, body.kind, results)
    except NothingToExport as e:
        raise HTTPException(409, str(e)) from None
    except Exception:
        logger.exception("export failed for assignment %s (%s)", assignment_id, body.kind)
        raise
    key = await store_export(db, storage, teacher.id, body.kind, pdf)
    return {"url": storage.signed_url(key, expires_s=LINK_TTL_S), "filename": filename}
