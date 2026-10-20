import pytest

from app.grading.matching import MatchResult, match_student

ROSTER = [(1, "张三"), (2, "李四"), (3, "王小明"), (4, "李四")]


def test_exact_unique_match():
    assert match_student("张三", ROSTER, None, 0.8) == MatchResult(1, "exact")


def test_duplicate_names_in_roster_are_ambiguous():
    assert match_student("李四", ROSTER, None, 0.8) == MatchResult(None, "ambiguous")


def test_fuzzy_match():
    assert match_student("王小朋", ROSTER, None, 0.6) == MatchResult(3, "fuzzy")


def test_no_name_continues_previous_page():
    assert match_student(None, ROSTER, 3, 0.8) == MatchResult(3, "continued")


def test_no_name_no_previous():
    assert match_student("", ROSTER, None, 0.8) == MatchResult(None, "none")


def test_blank_name_continues_previous_page():
    assert match_student("  ", ROSTER, 2, 0.8) == MatchResult(2, "continued")


def test_whitespace_in_names_is_ignored():
    assert match_student("张 三", ROSTER, None, 0.8) == MatchResult(1, "exact")
    assert match_student("张三", [(9, " 张　三 ")], None, 0.8) == MatchResult(9, "exact")


def test_fuzzy_tie_is_ambiguous():
    roster = [(1, "王小明"), (2, "王小朋")]
    assert match_student("王小红", roster, None, 0.6) == MatchResult(None, "ambiguous")


def test_fuzzy_tie_between_same_name_students_is_ambiguous():
    roster = [(1, "王小明"), (2, "王小明")]
    assert match_student("王小朋", roster, None, 0.6) == MatchResult(None, "ambiguous")


def test_below_threshold_is_none():
    assert match_student("赵六六", ROSTER, None, 0.8) == MatchResult(None, "none")


def test_unmatched_name_does_not_continue_previous_page():
    assert match_student("赵六六", ROSTER, 3, 0.8) == MatchResult(None, "none")


def test_empty_roster():
    assert match_student("张三", [], None, 0.8) == MatchResult(None, "none")
    assert match_student(None, [], 5, 0.8) == MatchResult(5, "continued")


def test_match_result_is_frozen():
    with pytest.raises(Exception):
        MatchResult(1, "exact").student_id = 2  # type: ignore[misc]
