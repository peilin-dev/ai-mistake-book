import pytest

from app.analytics.stats import (
    StudentQuestion,
    StudentResult,
    assignment_stats,
    build_stats,
    group_wrong_answers,
)
from app.models import KnowledgePoint, Student, Subject, Submission
from tests.conftest import make_result


def sq(no, score, max_score, answer="x", kp=None, subjective=False):
    wrong = max_score is not None and score < max_score
    return StudentQuestion(question_no=no, score=score, max_score=max_score, wrong=wrong, answer=answer,
                           is_subjective=subjective, knowledge_point_id=kp, crop_keys=[],
                           question_text="t", correct_answer="c")


def sr(name, qs, sid=None):
    sid = sid or abs(hash(name)) % 10000
    questions = [sq(*q) if isinstance(q, tuple) else q for q in qs]
    return StudentResult(student_id=sid, student_name=name, submission_id=sid + 1, score=0, max_score=0,
                         ratio=None, wrong_count=0, questions=questions)


def sr_ans(name, answer):
    return sr(name, [sq("5", 0, 2, answer=answer)])


def test_overview_numbers():
    s = build_stats([sr("张三", [("1", 2, 2), ("2", 0, 4)]), sr("李四", [("1", 2, 2), ("2", 4, 4)])],
                    roster_size=3, pending_review=1, pages_not_counted=2, kp_names={})
    assert (s.counted_students, s.roster_size, s.pending_review, s.pages_not_counted) == (2, 3, 1, 2)
    assert s.average_score == 4 and s.average_ratio == pytest.approx(4 / 6)
    assert s.pass_rate == 0.5
    assert [(q.question_no, q.wrong_count, q.accuracy) for q in s.questions] == [("2", 1, 0.5)]


def test_attention_by_ratio_and_gap():
    s = build_stats([sr("张三", [("1", 19, 20)]), sr("李四", [("1", 18, 20)]), sr("王五", [("1", 12, 20)])], 3, 0, 0, {})
    assert [a["student_name"] for a in s.attention] == ["王五"]


def test_attention_below_pass_line():
    s = build_stats([sr("张三", [("1", 1, 20)])], 1, 0, 0, {})
    assert [a["student_name"] for a in s.attention] == ["张三"]
    assert set(s.attention[0]) == {"student_id", "student_name", "submission_id", "score", "max_score",
                                   "ratio", "wrong_count"}


def test_duplicate_question_rows_count_once():
    s = build_stats([sr("王五", [("1", 2, 2), ("1", 0, 2)])], 1, 0, 0, {})
    assert s.questions[0].wrong_count == 1 and s.students[0].max_score == 4
    assert s.students[0].wrong_count == 1 and len(s.students[0].questions) == 1


def test_questions_without_max_score_are_left_out_of_rates():
    s = build_stats([sr("张三", [("1", 2, 2), ("2", 1, None)])], 1, 0, 0, {})
    assert s.students[0].max_score == 2 and s.average_ratio == 1.0


def test_weak_points_top3_by_wrong_count():
    qs = [("1", 0, 2, "x", 1), ("2", 0, 2, "x", 1), ("3", 0, 2, "x", 2), ("4", 0, 2, "x", 3),
          ("5", 0, 2, "x", 3), ("6", 0, 2, "x", 3), ("7", 0, 2, "x", 4)]
    s = build_stats([sr("张三", qs)], 1, 0, 0, {1: "加法", 2: "减法", 3: "乘法", 4: "除法"})
    assert s.weak_points == [{"name": "乘法", "wrong_count": 3}, {"name": "加法", "wrong_count": 2},
                             {"name": "减法", "wrong_count": 1}]


def test_questions_sorted_by_wrong_count_then_natural_order():
    a = sr("张三", [("10", 0, 2), ("2", 0, 2), ("3", 0, 2)])
    b = sr("李四", [("3", 0, 2), ("10", 2, 2), ("2", 2, 2)])
    s = build_stats([a, b], 2, 0, 0, {})
    assert [q.question_no for q in s.questions] == ["3", "2", "10"]


def test_blank_answers_grouped_as_unanswered():
    groups = group_wrong_answers([sr_ans("张三", "13"), sr_ans("李四", " 13 "), sr_ans("王五", None),
                                  sr_ans("赵六", "  ")], "5")
    assert [(g.answer, g.count) for g in groups] == [("13", 2), ("没写 / 没看清", 2)]
    assert groups[1].key == "" and groups[0].key == "13"
    assert set(groups[0].students[0]) == {"student_id", "student_name", "submission_id", "score", "max_score"}


def test_group_entries_carry_the_questions_own_score():
    # paper total differs from the question's score; the entry must show 1 / 4
    r = sr("张三", [sq("5", 1, 4, answer="13"), sq("6", 10, 10)])
    r.score, r.max_score = 11, 14
    groups = group_wrong_answers([r], "5")
    entry = groups[0].students[0]
    assert (entry["score"], entry["max_score"]) == (1, 4)
    assert set(entry) == {"student_id", "student_name", "submission_id", "score", "max_score"}


def test_groups_ordered_by_count_unanswered_last():
    groups = group_wrong_answers([sr_ans("a", None), sr_ans("b", None), sr_ans("c", None),
                                  sr_ans("d", "7"), sr_ans("e", "8"), sr_ans("f", "8")], "5")
    assert [g.answer for g in groups] == ["8", "7", "没写 / 没看清"]


def test_subjective_question_has_no_top_wrong_answer():
    s = build_stats([sr("张三", [("1", 0, 5, "写了一段", None, True)]), sr("李四", [("1", 0, 5, "写了一段", None, True)])],
                    2, 0, 0, {})
    assert s.questions[0].is_subjective and s.questions[0].top_wrong_answer is None


def test_top_wrong_answer_for_objective():
    s = build_stats([sr("a", [("1", 0, 2, "7")]), sr("b", [("1", 0, 2, " 7")]), sr("c", [("1", 0, 2, "8")])], 3, 0, 0, {})
    assert s.questions[0].top_wrong_answer == "7"


def test_empty_results():
    s = build_stats([], 5, 0, 0, {})
    assert s.counted_students == 0 and s.average_score is None and s.pass_rate is None and s.questions == []


async def test_assignment_stats_counts_only_done_assigned_pages(db, my_assignment, roster_zhangsan,
                                                                  make_done_page, make_page):
    done = await make_done_page(1, roster_zhangsan.id, "张三")
    await make_done_page(2, None, "不认识")
    await make_page(3)
    kp = KnowledgePoint(subject=Subject.math, grade_min=1, grade_max=6, code="t-add", name="加法")
    db.add(kp)
    await db.flush()
    sub = Submission(assignment_id=my_assignment.id, student_id=roster_zhangsan.id, total_score=2)
    db.add(sub)
    await db.flush()
    db.add_all([make_result(done.id, sub.id, "1"),
                make_result(done.id, sub.id, "2", is_correct=False, score=0, max_score=4,
                            knowledge_point_id=kp.id, needs_review=True, student_answer="9")])
    await db.commit()
    s = await assignment_stats(db, my_assignment.id)
    assert s.counted_students == 1 and s.roster_size == 1
    assert s.pages_not_counted == 2
    assert s.pending_review == 1
    assert s.students[0].score == 2 and s.students[0].max_score == 6
    assert [(q.question_no, q.knowledge_point, q.top_wrong_answer) for q in s.questions] == [("2", "加法", "9")]
    assert s.weak_points == [{"name": "加法", "wrong_count": 1}]
    assert isinstance(roster_zhangsan, Student)
