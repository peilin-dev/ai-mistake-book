import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.rules import ATTENTION_GAP, PASS_RATIO, RECENT_N
from app.grading.consensus import normalize_answer
from app.models import (
    Assignment,
    KnowledgePoint,
    Page,
    PageStatus,
    QuestionResult,
    Student,
    Submission,
)

UNANSWERED = "没写 / 没看清"
_EPS = 1e-9


@dataclass
class StudentQuestion:
    question_no: str
    score: float
    max_score: float | None
    wrong: bool
    answer: str | None
    is_subjective: bool
    knowledge_point_id: int | None
    crop_keys: list[str]
    question_text: str | None
    correct_answer: str | None


@dataclass
class StudentResult:
    student_id: int
    student_name: str
    submission_id: int
    score: float
    max_score: float
    ratio: float | None
    wrong_count: int
    questions: list[StudentQuestion]


@dataclass
class QuestionStat:
    question_no: str
    knowledge_point: str | None
    wrong_count: int
    student_count: int  # everyone with a row for this question (headcount)
    answered_count: int  # those with a max_score (accuracy denominator)
    accuracy: float | None
    top_wrong_answer: str | None
    is_subjective: bool


@dataclass
class AnswerGroup:
    answer: str
    key: str
    count: int
    students: list[dict] = field(default_factory=list)


@dataclass
class AssignmentStats:
    counted_students: int
    roster_size: int
    average_score: float | None
    average_ratio: float | None
    pass_rate: float | None
    pending_review: int
    pages_not_counted: int
    questions: list[QuestionStat]
    weak_points: list[dict]
    attention: list[dict]
    students: list[StudentResult]


def _natural(no: str) -> list:
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"(\d+)", no) if p]


def _first(values):
    return next((v for v in values if v is not None), None)


def _merge_question(rows: list[StudentQuestion]) -> StudentQuestion:
    """Several rows for one question number count as one: scores add up, any miss is wrong."""
    maxes = [r.max_score for r in rows if r.max_score is not None]
    wrong_rows = [r for r in rows if r.wrong]
    lead = wrong_rows[0] if wrong_rows else rows[0]
    return StudentQuestion(
        question_no=rows[0].question_no,
        score=sum(r.score for r in rows),
        max_score=sum(maxes) if maxes else None,
        wrong=bool(wrong_rows),
        answer=lead.answer,
        is_subjective=any(r.is_subjective for r in rows),
        knowledge_point_id=_first(r.knowledge_point_id for r in rows),
        crop_keys=[k for r in rows for k in r.crop_keys],
        question_text=_first(r.question_text for r in rows),
        correct_answer=_first(r.correct_answer for r in rows),
    )


def _normalize_student(r: StudentResult) -> StudentResult:
    by_no: dict[str, list[StudentQuestion]] = {}
    for q in r.questions:
        by_no.setdefault(q.question_no, []).append(q)
    questions = sorted((_merge_question(rows) for rows in by_no.values()), key=lambda q: _natural(q.question_no))
    graded = [q for q in questions if q.max_score is not None]
    score = sum(q.score for q in graded)
    max_score = sum(q.max_score for q in graded)
    return StudentResult(
        student_id=r.student_id, student_name=r.student_name, submission_id=r.submission_id,
        score=score, max_score=max_score, ratio=score / max_score if max_score > 0 else None,
        wrong_count=sum(1 for q in questions if q.wrong), questions=questions,
    )


def _student_ref(r: StudentResult) -> dict:
    return {"student_id": r.student_id, "student_name": r.student_name, "submission_id": r.submission_id,
            "score": r.score, "max_score": r.max_score}


def _answer_student_ref(r: StudentResult, q: StudentQuestion) -> dict:
    """Group entries carry this question's own score, not the paper total."""
    return {"student_id": r.student_id, "student_name": r.student_name, "submission_id": r.submission_id,
            "score": q.score, "max_score": q.max_score if q.max_score is not None else 0.0}


def _group_answers(entries: list[tuple[StudentResult, StudentQuestion]]) -> list[AnswerGroup]:
    buckets: dict[str, list[tuple[StudentResult, StudentQuestion, str]]] = {}
    for r, q in entries:
        buckets.setdefault(normalize_answer(q.answer), []).append((r, q, (q.answer or "").strip()))
    groups = []
    for key, items in buckets.items():
        shown = UNANSWERED if key == "" else Counter(raw for _, _, raw in items).most_common(1)[0][0]
        groups.append(AnswerGroup(answer=shown, key=key, count=len(items),
                                  students=[_answer_student_ref(r, q) for r, q, _ in items]))
    groups.sort(key=lambda g: (g.key == "", -g.count))
    return groups


def group_wrong_answers(results: list[StudentResult], question_no: str) -> list[AnswerGroup]:
    entries = []
    for r in map(_normalize_student, results):
        for q in r.questions:
            if q.question_no == question_no and q.wrong:
                entries.append((r, q))
    return _group_answers(entries)


def build_stats(results: list[StudentResult], roster_size: int, pending_review: int, pages_not_counted: int,
                kp_names: dict[int, str]) -> AssignmentStats:
    students = [_normalize_student(r) for r in results]
    with_ratio = [s for s in students if s.ratio is not None]
    average_ratio = sum(s.ratio for s in with_ratio) / len(with_ratio) if with_ratio else None
    pass_rate = (sum(1 for s in with_ratio if s.ratio >= PASS_RATIO - _EPS) / len(with_ratio)
                 if with_ratio else None)

    attention = sorted(
        (s for s in with_ratio
         if s.ratio < PASS_RATIO - _EPS or average_ratio - s.ratio >= ATTENTION_GAP - _EPS),
        key=lambda s: (s.ratio, s.student_name),
    )

    by_no: dict[str, list[tuple[StudentResult, StudentQuestion]]] = {}
    for s in students:
        for q in s.questions:
            by_no.setdefault(q.question_no, []).append((s, q))

    stats: list[QuestionStat] = []
    kp_wrong: Counter = Counter()
    for no, entries in by_no.items():
        wrong = [(s, q) for s, q in entries if q.wrong]
        if not wrong:
            continue
        kp_ids = Counter(q.knowledge_point_id for _, q in entries if q.knowledge_point_id is not None)
        kp_id = kp_ids.most_common(1)[0][0] if kp_ids else None
        kp_name = kp_names.get(kp_id) if kp_id is not None else None
        for _, q in wrong:
            name = kp_names.get(q.knowledge_point_id) if q.knowledge_point_id is not None else None
            if name:
                kp_wrong[name] += 1
        answered = [q for _, q in entries if q.max_score is not None]
        correct = sum(1 for q in answered if not q.wrong)
        subjective = any(q.is_subjective for _, q in entries)
        top = None
        if not subjective:
            groups = [g for g in _group_answers(wrong) if g.key != ""]
            top = groups[0].answer if groups else None
        stats.append(QuestionStat(
            question_no=no, knowledge_point=kp_name, wrong_count=len(wrong), student_count=len(entries),
            answered_count=len(answered),
            accuracy=correct / len(answered) if answered else None, top_wrong_answer=top,
            is_subjective=subjective,
        ))
    stats.sort(key=lambda q: (-q.wrong_count, _natural(q.question_no)))

    weak = sorted(kp_wrong.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return AssignmentStats(
        counted_students=len(students), roster_size=roster_size,
        # only students with gradable questions; the others have no score to average
        average_score=sum(s.score for s in with_ratio) / len(with_ratio) if with_ratio else None,
        average_ratio=average_ratio, pass_rate=pass_rate,
        pending_review=pending_review, pages_not_counted=pages_not_counted,
        questions=stats,
        weak_points=[{"name": n, "wrong_count": c} for n, c in weak],
        attention=[{**_student_ref(s), "ratio": s.ratio, "wrong_count": s.wrong_count} for s in attention],
        students=students,
    )


def _counted_pages(assignment_id: int):
    return and_(Page.assignment_id == assignment_id, Page.status == PageStatus.done, Page.student_id.is_not(None))


async def load_student_results(db: AsyncSession, assignment_id: int,
                               student_id: int | None = None) -> list[StudentResult]:
    stmt = (
        select(QuestionResult, Submission.id, Student.id, Student.name)
        .join(Page, Page.id == QuestionResult.page_id)
        .join(Submission, Submission.id == QuestionResult.submission_id)
        .join(Student, Student.id == Submission.student_id)
        .where(_counted_pages(assignment_id))
        .order_by(QuestionResult.id)
    )
    if student_id is not None:
        stmt = stmt.where(Student.id == student_id)
    rows = (await db.execute(stmt)).all()
    per_student: dict[int, StudentResult] = {}
    for qr, sub_id, stu_id, stu_name in rows:
        res = per_student.setdefault(stu_id, StudentResult(
            student_id=stu_id, student_name=stu_name, submission_id=sub_id,
            score=0, max_score=0, ratio=None, wrong_count=0, questions=[]))
        wrong = (qr.score < qr.max_score) if qr.max_score is not None else not qr.is_correct
        res.questions.append(StudentQuestion(
            question_no=qr.question_no, score=qr.score, max_score=qr.max_score, wrong=wrong,
            answer=qr.student_answer, is_subjective=qr.is_subjective, knowledge_point_id=qr.knowledge_point_id,
            crop_keys=[qr.crop_key] if qr.crop_key else [], question_text=qr.question_text,
            correct_answer=qr.correct_answer))
    return [_normalize_student(r) for r in per_student.values()]


async def assignment_stats(db: AsyncSession, assignment_id: int) -> AssignmentStats:
    results = await load_student_results(db, assignment_id)
    assignment = await db.get(Assignment, assignment_id)
    roster = (await db.execute(
        select(func.count()).select_from(Student).where(Student.class_id == assignment.class_id)
    )).scalar_one()
    not_counted = (await db.execute(
        select(func.count()).select_from(Page).where(
            Page.assignment_id == assignment_id,
            ~and_(Page.status == PageStatus.done, Page.student_id.is_not(None)))
    )).scalar_one()
    pending = (await db.execute(
        select(func.count()).select_from(QuestionResult)
        .join(Page, Page.id == QuestionResult.page_id)
        .where(_counted_pages(assignment_id), QuestionResult.needs_review.is_(True),
               QuestionResult.reviewed.is_(False))
    )).scalar_one()
    kp_ids = {q.knowledge_point_id for r in results for q in r.questions if q.knowledge_point_id is not None}
    kp_names = {}
    if kp_ids:
        kp_names = dict((await db.execute(
            select(KnowledgePoint.id, KnowledgePoint.name).where(KnowledgePoint.id.in_(kp_ids))
        )).all())
    return build_stats(results, roster, pending, not_counted, kp_names)


async def student_history(db: AsyncSession, submission_id: int) -> list[dict]:
    """Recent assignments (same class and subject, newest first) this student has results for,
    with scores computed by the same merging rules as the statistics."""
    sub = await db.get(Submission, submission_id)
    if sub is None:
        return []
    current = await db.get(Assignment, sub.assignment_id)
    candidates = (await db.execute(
        select(Assignment)
        .join(Submission, Submission.assignment_id == Assignment.id)
        .where(Assignment.class_id == current.class_id, Assignment.subject == current.subject,
               Submission.student_id == sub.student_id)
        .order_by(Assignment.created_at.desc(), Assignment.id.desc())
    )).scalars().all()
    history: list[dict] = []
    for a in candidates:
        mine = await load_student_results(db, a.id, sub.student_id)
        if not mine:
            continue
        r = mine[0]
        history.append({"assignment_id": a.id, "title": a.title, "created_at": a.created_at,
                        "score": r.score, "max_score": r.max_score, "ratio": r.ratio})
        if len(history) == RECENT_N:
            break
    return history
