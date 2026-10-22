from app.models import AnswerItem, AnswerKeyStatus, KnowledgePoint, Student, Subject, Submission
from app.practice.rules import ACCURACY_BELOW, CONCURRENCY, MAX_SOURCES, VARIANTS_PER_SOURCE
from app.practice.sources import Source, class_sources, student_sources
from tests.conftest import make_result


async def _students(db, my_class, n):
    out = []
    for i in range(n):
        s = Student(class_id=my_class.id, name=f"学生{i}")
        db.add(s)
        out.append(s)
    await db.commit()
    return out


async def _grade(db, my_assignment, make_done_page, students, rows_by_student):
    """rows_by_student: list (per student) of {no: kwargs}. Returns submissions."""
    subs = []
    for i, (stu, rows) in enumerate(zip(students, rows_by_student)):
        page = await make_done_page(100 + i, stu.id, stu.name)
        sub = Submission(assignment_id=my_assignment.id, student_id=stu.id, total_score=0)
        db.add(sub)
        await db.flush()
        for no, kw in rows.items():
            db.add(make_result(page.id, sub.id, no, **kw))
        subs.append(sub)
    await db.commit()
    return subs


WRONG = dict(is_correct=False, score=0, max_score=2)
RIGHT = dict(is_correct=True, score=2, max_score=2)


def test_constants():
    assert (ACCURACY_BELOW, MAX_SOURCES, VARIANTS_PER_SOURCE, CONCURRENCY) == (0.85, 5, 2, 5)


async def test_class_sources_below_accuracy_sorted_and_capped(db, my_class, my_assignment, make_done_page):
    kp = KnowledgePoint(subject=Subject.math, grade_min=1, grade_max=6, code="p-add", name="加法")
    db.add(kp)
    await db.flush()
    studs = await _students(db, my_class, 10)
    rows = []
    for i in range(10):
        r = {}
        for n in range(1, 8):  # q1..q7: q1 wrong by 7, q2 by 6, ... q7 by 1
            r[str(n)] = dict(WRONG if i < 8 - n else RIGHT, question_text=f"题{n}", correct_answer="a",
                             knowledge_point_id=kp.id)
        r["8"] = dict(RIGHT)  # accurate, never wrong
        r["9"] = dict(WRONG if i == 0 else RIGHT, question_text="高正确率")  # 90% accuracy
        rows.append(r)
    await _grade(db, my_assignment, make_done_page, studs, rows)
    out = await class_sources(db, my_assignment.id)
    assert [s.question_no for s in out] == ["1", "2", "3", "4", "5"]
    first = out[0]
    assert isinstance(first, Source)
    assert (first.text, first.correct_answer, first.knowledge_point_id, first.knowledge_point) == (
        "题1", "a", kp.id, "加法")
    assert (first.grade, first.subject, first.lost) == (5, "math", None)


async def test_sources_skip_subjective_and_blank_text(db, my_class, my_assignment, make_done_page):
    studs = await _students(db, my_class, 2)
    rows = [{"1": dict(WRONG, is_subjective=True), "2": dict(WRONG, question_text=None),
             "3": dict(WRONG, question_text="  "), "4": dict(WRONG)} for _ in studs]
    await _grade(db, my_assignment, make_done_page, studs, rows)
    assert [s.question_no for s in await class_sources(db, my_assignment.id)] == ["4"]


async def test_sources_skip_answer_mismatch_without_key(db, my_class, my_assignment, make_done_page):
    studs = await _students(db, my_class, 2)
    rows = [{"1": dict(WRONG, answer_mismatch=(i == 1)), "2": dict(WRONG)} for i in range(2)]
    await _grade(db, my_assignment, make_done_page, studs, rows)
    assert [s.question_no for s in await class_sources(db, my_assignment.id)] == ["2"]


async def test_confirmed_key_overrides_mismatch_and_supplies_answer(db, my_class, my_assignment,
                                                                    make_done_page, confirmed_key_q1_q2):
    studs = await _students(db, my_class, 2)
    rows = [{"1": dict(WRONG, answer_mismatch=True, correct_answer="zz")} for _ in range(2)]
    await _grade(db, my_assignment, make_done_page, studs, rows)
    out = await class_sources(db, my_assignment.id)
    assert [(s.question_no, s.correct_answer) for s in out] == [("1", "7")]


async def test_sources_skip_unreviewed_needs_review(db, my_class, my_assignment, make_done_page):
    studs = await _students(db, my_class, 2)
    rows = [{"1": dict(WRONG, needs_review=(i == 0)),
             "2": dict(WRONG, needs_review=(i == 0), reviewed=(i == 0)),
             "3": dict(WRONG)} for i in range(2)]
    await _grade(db, my_assignment, make_done_page, studs, rows)
    assert [s.question_no for s in await class_sources(db, my_assignment.id)] == ["2", "3"]


async def test_student_sources_by_points_lost_null_max_last(db, my_class, my_assignment, make_done_page):
    studs = await _students(db, my_class, 2)
    rows = [{"1": dict(is_correct=False, score=1, max_score=2), "2": dict(is_correct=False, score=0, max_score=5),
             "3": dict(is_correct=False, score=0, max_score=None), "4": dict(RIGHT),
             "5": dict(WRONG, is_subjective=True), "6": dict(is_correct=False, score=0, max_score=3)},
            {"1": dict(RIGHT), "2": dict(RIGHT), "3": dict(RIGHT), "4": dict(RIGHT), "5": dict(RIGHT),
             "6": dict(RIGHT)}]
    subs = await _grade(db, my_assignment, make_done_page, studs, rows)
    out = await student_sources(db, subs[0].id)
    assert [(s.question_no, s.lost) for s in out] == [("2", 5), ("6", 3), ("1", 1), ("3", None)]
    assert await student_sources(db, subs[1].id) == []


async def test_source_text_is_most_common_nonempty(db, my_class, my_assignment, make_done_page):
    studs = await _students(db, my_class, 4)
    texts = [None, "甲", "乙", "乙"]
    answers = [None, "x", "y", "y"]
    rows = [{"1": dict(WRONG, question_text=t, correct_answer=a)} for t, a in zip(texts, answers)]
    await _grade(db, my_assignment, make_done_page, studs, rows)
    out = await class_sources(db, my_assignment.id)
    assert (out[0].text, out[0].correct_answer) == ("乙", "y")
