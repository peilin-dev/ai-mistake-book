import pytest
from pydantic import ValidationError

from app.grading.rules import filter_knowledge_point, needs_review
from app.grading.schema import GradedPage, GradedQuestion

VALID_Q = {
    "no": "3",
    "question_text": "一个圆柱形水桶，底面半径 2dm，高 5dm",
    "student_answer": "157dm³",
    "correct_answer": "62.8dm³",
    "is_subjective": False,
    "is_correct": False,
    "score": 0,
    "max_score": 4,
    "confidence": 0.92,
    "bbox": [0.08, 0.31, 0.92, 0.45],
    "knowledge_point_id": 1234,
    "error_reason": "把侧面积公式当成体积公式",
}


@pytest.mark.parametrize("conf,status,mismatch,expected", [
    (0.95, "exact", False, False),
    (0.79, "exact", False, True),
    (0.95, "exact", True, True),
    (0.95, "fuzzy", False, True),
    (0.95, "ambiguous", False, True),
    (0.95, "none", False, True),
    (0.95, "continued", False, False),
    (0.95, "continued", True, True),
    (0.8, "exact", False, False),
])
def test_needs_review(conf, status, mismatch, expected):
    assert needs_review(conf, status, 0.8, answer_mismatch=mismatch) is expected


def test_unverified_alone_not_reviewed():
    assert needs_review(0.95, "exact", 0.8) is False
    assert needs_review(0.95, "exact", 0.8, answer_mismatch=True) is True


def test_bbox_must_be_ordered():
    with pytest.raises(ValidationError):
        GradedQuestion(**{**VALID_Q, "bbox": [0.5, 0.1, 0.4, 0.2]})
    with pytest.raises(ValidationError):
        GradedQuestion(**{**VALID_Q, "bbox": [0.1, 0.5, 0.4, 0.2]})


def test_bbox_out_of_range_rejected():
    with pytest.raises(ValidationError):
        GradedQuestion(**{**VALID_Q, "bbox": [0.1, 0.1, 1.2, 0.2]})
    with pytest.raises(ValidationError):
        GradedQuestion(**{**VALID_Q, "bbox": [0.1, 0.1, 0.5]})


def test_valid_question_parses_and_defaults():
    q = GradedQuestion(**VALID_Q)
    assert q.bbox == (0.08, 0.31, 0.92, 0.45)
    minimal = {k: v for k, v in VALID_Q.items()
               if k not in {"is_subjective", "knowledge_point_id", "error_reason"}}
    q2 = GradedQuestion(**minimal)
    assert q2.is_subjective is False and q2.knowledge_point_id is None and q2.error_reason is None


def test_int_no_is_coerced_to_str():
    assert GradedQuestion(**{**VALID_Q, "no": 3}).no == "3"


def test_score_above_max_rejected():
    with pytest.raises(ValidationError):
        GradedQuestion(**{**VALID_Q, "score": 5, "max_score": 4})


def test_negative_score_rejected():
    with pytest.raises(ValidationError):
        GradedQuestion(**{**VALID_Q, "score": -1})


@pytest.mark.parametrize("conf", [1.2, -0.1])
def test_confidence_out_of_range_rejected(conf):
    with pytest.raises(ValidationError):
        GradedQuestion(**{**VALID_Q, "confidence": conf})


def test_unknown_extra_keys_ignored():
    q = GradedQuestion(**{**VALID_Q, "foo": "bar"})
    assert not hasattr(q, "foo")


def test_page_may_have_no_questions_or_name():
    p = GradedPage.model_validate({"student_name": None, "questions": []})
    assert p.questions == [] and p.student_name is None
    p2 = GradedPage.model_validate({"student_name": "张三", "questions": [VALID_Q]})
    assert p2.questions[0].no == "3"


def test_unknown_knowledge_point_dropped():
    assert filter_knowledge_point(999, {1, 2}) is None and filter_knowledge_point(2, {1, 2}) == 2
    assert filter_knowledge_point(None, {1, 2}) is None
