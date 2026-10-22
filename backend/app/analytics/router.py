"""Class analytics for the teacher (assignment overview, question detail, student history)."""
from collections import Counter
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


@router.get("/submissions/{submission_id}/history")
async def submission_history(
    submission_id: int,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    owned = (await db.execute(
        select(Submission.id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(Class_, Class_.id == Assignment.class_id)
        .where(Submission.id == submission_id, Class_.teacher_id == teacher.id)
    )).first()
    if owned is None:
        raise HTTPException(404, "submission not found")
    return await student_history(db, submission_id)
