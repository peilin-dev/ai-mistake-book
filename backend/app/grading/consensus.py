"""No answer key: each question's correct answer is the class majority (spec M3 section 5, option B).

A row whose AI answer disagrees with the majority of its question number (or where the
answers tie) gets `answer_mismatch` and so needs review. Callers hold the assignment lock.
"""
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.grading.rules import needs_review
from app.models import Page, PageStatus, QuestionResult, Student

_WS = re.compile(r"\s+")


def normalize_answer(s: str | None) -> str:
    """Drop all whitespace, full-width -> half-width, lower case."""
    chars = []
    for ch in _WS.sub("", s or ""):
        code = ord(ch)
        chars.append(chr(code - 0xFEE0) if 0xFF01 <= code <= 0xFF5E else ch)
    return "".join(chars).lower()


def majority(answers: list[str]) -> str | None:
    """The strictly most frequent answer; None on a tie or no answers."""
    top = Counter(answers).most_common(2)
    if not top or (len(top) == 2 and top[0][1] == top[1][1]):
        return None
    return top[0][0]


def _student_status(student_id: int | None, recognized: str | None, roster_name: str | None) -> str:
    if student_id is None:
        return "none"
    if recognized is None:
        return "continued"
    return "exact" if _WS.sub("", recognized) == _WS.sub("", roster_name or "") else "fuzzy"


async def refresh_answer_consensus(
    db: AsyncSession, assignment_id: int, question_nos: set[str], settings: Settings
) -> set[int]:
    """Recompute answer_mismatch for unverified, unreviewed rows of done pages with these
    question numbers; rows whose flag changed get needs_review recomputed. Returns the
    submissions of changed rows."""
    if not question_nos:
        return set()
    stmt = (
        select(QuestionResult, Page.student_id, Page.recognized_name, Student.name)
        .join(Page, Page.id == QuestionResult.page_id)
        .outerjoin(Student, Student.id == Page.student_id)
        .where(
            Page.assignment_id == assignment_id,
            Page.status == PageStatus.done,
            QuestionResult.question_no.in_(question_nos),
            QuestionResult.answer_verified.is_(False),
            QuestionResult.reviewed.is_(False),
        )
        .execution_options(populate_existing=True)
    )
    groups: dict[str, list] = {}
    for row in (await db.execute(stmt)).all():
        groups.setdefault(row[0].question_no, []).append(row)

    touched: set[int] = set()
    for rows in groups.values():
        norms = [normalize_answer(r.correct_answer) for r, *_ in rows]
        top = majority(norms)
        for (r, student_id, recognized, roster_name), norm in zip(rows, norms):
            mismatch = len(rows) > 1 and (top is None or norm != top)
            if r.answer_mismatch == mismatch:
                continue
            r.answer_mismatch = mismatch
            status = _student_status(student_id, recognized, roster_name)
            r.needs_review = needs_review(r.confidence, status, settings.REVIEW_CONFIDENCE_THRESHOLD, mismatch)
            if r.submission_id is not None:
                touched.add(r.submission_id)
    return touched
