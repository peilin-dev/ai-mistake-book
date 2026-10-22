from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.stats import _counted_pages, assignment_stats, load_student_results
from app.models import (
    AnswerItem,
    Assignment,
    AnswerKeyStatus,
    Class_,
    KnowledgePoint,
    Page,
    QuestionResult,
    Submission,
)
from app.practice.rules import ACCURACY_BELOW, MAX_SOURCES


@dataclass
class Source:
    question_no: str
    text: str
    correct_answer: str
    knowledge_point_id: int | None
    knowledge_point: str | None
    grade: int
    subject: str
    lost: float | None  # points lost (single student); None for class sources or unknown max


def _most_common(values) -> str | None:
    cleaned = [v.strip() for v in values if v and v.strip()]
    return Counter(cleaned).most_common(1)[0][0] if cleaned else None


async def _usable(db: AsyncSession, assignment: Assignment) -> dict[str, tuple[str, str]]:
    """question_no -> (text, correct answer) for questions that may be practice sources."""
    rows = (await db.execute(
        select(QuestionResult.question_no, QuestionResult.question_text, QuestionResult.correct_answer,
               QuestionResult.answer_mismatch, QuestionResult.needs_review, QuestionResult.reviewed)
        .join(Page, Page.id == QuestionResult.page_id)
        .where(_counted_pages(assignment.id))
    )).all()
    key: dict[str, str] = {}
    if assignment.answer_key_status == AnswerKeyStatus.confirmed:
        items = (await db.execute(
            select(AnswerItem).where(AnswerItem.assignment_id == assignment.id).order_by(AnswerItem.id)
        )).scalars()
        key = {i.question_no: i.answer.strip() for i in items if i.answer and i.answer.strip()}
    keyed = assignment.answer_key_status == AnswerKeyStatus.confirmed

    by_no: dict[str, list] = {}
    for r in rows:
        by_no.setdefault(r.question_no, []).append(r)
    usable: dict[str, tuple[str, str]] = {}
    for no, rs in by_no.items():
        if any(r.needs_review and not r.reviewed for r in rs):
            continue
        if not keyed and any(r.answer_mismatch for r in rs):
            continue
        text = _most_common(r.question_text for r in rs)
        answer = key.get(no) if keyed and no in key else _most_common(r.correct_answer for r in rs)
        if text and answer:
            usable[no] = (text, answer)
    return usable


async def _kp_names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict((await db.execute(
        select(KnowledgePoint.id, KnowledgePoint.name).where(KnowledgePoint.id.in_(ids)))).all())


async def class_sources(db: AsyncSession, assignment_id: int) -> list[Source]:
    assignment = await db.get(Assignment, assignment_id)
    cls = await db.get(Class_, assignment.class_id)
    stats = await assignment_stats(db, assignment_id)
    usable = await _usable(db, assignment)
    # knowledge point id per question: most common across students
    kp_by_no: dict[str, Counter] = {}
    for s in stats.students:
        for q in s.questions:
            if q.knowledge_point_id is not None:
                kp_by_no.setdefault(q.question_no, Counter())[q.knowledge_point_id] += 1
    picked = []
    for q in stats.questions:  # already by wrong count desc
        if q.is_subjective or q.accuracy is None or q.accuracy >= ACCURACY_BELOW or q.question_no not in usable:
            continue
        picked.append(q)
        if len(picked) == MAX_SOURCES:
            break
    out = []
    for q in picked:
        counter = kp_by_no.get(q.question_no)
        kp_id = counter.most_common(1)[0][0] if counter else None
        text, answer = usable[q.question_no]
        out.append(Source(question_no=q.question_no, text=text, correct_answer=answer, knowledge_point_id=kp_id,
                          knowledge_point=q.knowledge_point, grade=cls.grade, subject=assignment.subject.value,
                          lost=None))
    return out


async def student_sources(db: AsyncSession, submission_id: int) -> list[Source]:
    sub = await db.get(Submission, submission_id)
    assignment = await db.get(Assignment, sub.assignment_id)
    cls = await db.get(Class_, assignment.class_id)
    results = await load_student_results(db, assignment.id, sub.student_id)
    if not results:
        return []
    usable = await _usable(db, assignment)
    cands = []
    for q in results[0].questions:
        if q.is_subjective or not q.wrong or q.question_no not in usable:
            continue
        lost = q.max_score - q.score if q.max_score is not None else None
        cands.append((q, lost))
    # stable sort keeps natural question order among ties; unknown max goes last
    cands.sort(key=lambda c: (c[1] is None, -(c[1] or 0)))
    cands = cands[:MAX_SOURCES]
    names = await _kp_names(db, {q.knowledge_point_id for q, _ in cands if q.knowledge_point_id is not None})
    out = []
    for q, lost in cands:
        text, answer = usable[q.question_no]
        out.append(Source(question_no=q.question_no, text=text, correct_answer=answer,
                          knowledge_point_id=q.knowledge_point_id,
                          knowledge_point=names.get(q.knowledge_point_id), grade=cls.grade,
                          subject=assignment.subject.value, lost=lost))
    return out
