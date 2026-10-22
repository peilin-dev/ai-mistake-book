"""Class analytics for the teacher (assignment overview, question detail, student history)."""
from collections import Counter
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import VisionModel
from app.analytics.notes import get_analysis_model, question_causes, student_summary
from app.analytics.stats import assignment_stats, group_wrong_answers, load_student_results, student_history
from app.assignments.access import own_assignment
from app.deps import current_teacher, get_db
from app.models import Assignment, Class_, KnowledgePoint, Submission, Teacher
from app.storage.base import Storage, get_storage

router = APIRouter(tags=["analytics"])


@router.get("/assignments/{assignment_id}/analytics")
async def analytics_overview(
    assignment_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await own_assignment(db, teacher, assignment_id)
    body = asdict(await assignment_stats(db, assignment_id))
    body.pop("students")
    return body


def _score_buckets(questions: list) -> list[dict]:
    full = half = low = 0
    for q in questions:
        if q.max_score is None:
            continue
        if q.score >= q.max_score:
            full += 1
        elif q.score * 2 >= q.max_score:
            half += 1
        else:
            low += 1
    return [{"label": "满分", "count": full}, {"label": "一半及以上", "count": half},
            {"label": "一半以下", "count": low}]


@router.get("/assignments/{assignment_id}/analytics/questions/{question_no}")
async def question_detail(
    assignment_id: int,
    question_no: str,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> dict:
    await own_assignment(db, teacher, assignment_id)
    results = await load_student_results(db, assignment_id)
    entries = [(r, q) for r in results for q in r.questions if q.question_no == question_no]
    if not entries:
        raise HTTPException(404, "question not found")
    qs = [q for _, q in entries]
    subjective = any(q.is_subjective for q in qs)
    answered = [q for q in qs if q.max_score is not None]
    kp_ids = Counter(q.knowledge_point_id for q in qs if q.knowledge_point_id is not None)
    kp_name = None
    if kp_ids:
        kp_name = (await db.execute(
            select(KnowledgePoint.name).where(KnowledgePoint.id == kp_ids.most_common(1)[0][0])
        )).scalar_one_or_none()
    crops = [
        {"student_name": r.student_name, "submission_id": r.submission_id,
         "crop_url": storage.signed_url(key)}
        for r, q in entries if q.wrong for key in q.crop_keys
    ]
    return {
        "question_no": question_no,
        "question_text": next((q.question_text for q in qs if q.question_text), None),
        "correct_answer": next((q.correct_answer for q in qs if q.correct_answer), None),
        "is_subjective": subjective,
        "knowledge_point": kp_name,
        "wrong_count": sum(1 for q in qs if q.wrong),
        "answered_count": len(answered),
        "groups": [] if subjective else [asdict(g) for g in group_wrong_answers(results, question_no)],
        "score_buckets": _score_buckets(qs) if subjective else [],
        "crops": crops,
    }


async def _own_submission(db: AsyncSession, teacher: Teacher, submission_id: int) -> Submission:
    sub = (await db.execute(
        select(Submission)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(Class_, Class_.id == Assignment.class_id)
        .where(Submission.id == submission_id, Class_.teacher_id == teacher.id)
    )).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "submission not found")
    return sub


@router.get("/submissions/{submission_id}/history")
async def submission_history(
    submission_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _own_submission(db, teacher, submission_id)
    return await student_history(db, submission_id)


@router.post("/assignments/{assignment_id}/analytics/questions/{question_no}/causes")
async def question_cause_notes(
    assignment_id: int,
    question_no: str,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    model: VisionModel = Depends(get_analysis_model),
) -> dict:
    await own_assignment(db, teacher, assignment_id)
    results = await load_student_results(db, assignment_id)
    qs = [q for r in results for q in r.questions if q.question_no == question_no]
    if not qs:
        raise HTTPException(404, "question not found")
    if any(q.is_subjective for q in qs):
        return {"causes": {}}
    causes = await question_causes(
        db, model, teacher.id, assignment_id, question_no, group_wrong_answers(results, question_no),
        next((q.question_text for q in qs if q.question_text), None),
        next((q.correct_answer for q in qs if q.correct_answer), None))
    await db.commit()
    return {"causes": causes}


@router.post("/submissions/{submission_id}/summary")
async def submission_summary(
    submission_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    model: VisionModel = Depends(get_analysis_model),
) -> dict:
    sub = await _own_submission(db, teacher, submission_id)
    mine = await load_student_results(db, sub.assignment_id, sub.student_id)
    if not mine:
        return {"summary": None}
    history = await student_history(db, submission_id)
    summary = await student_summary(db, model, teacher.id, submission_id, mine[0], history)
    await db.commit()
    return {"summary": summary}