"""Checks on the shipped curriculum files in data/knowledge (no database needed)."""
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest
import yaml

from app.knowledge.loader import _parse
from app.models import Subject

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"

# subject -> (code prefix, first grade, last grade)
EXPECTED = {
    "chinese": ("CN", 1, 9),
    "math": ("MA", 1, 9),
    "english": ("EN", 3, 9),
    "politics": ("PO", 1, 9),
    "science": ("SC", 1, 6),
    "physics": ("PH", 8, 9),
    "chemistry": ("CH", 9, 9),
    "biology": ("BI", 7, 8),
    "history": ("HI", 7, 9),
    "geography": ("GE", 7, 8),
}
HEADER = "依据义务教育课程标准（2022 年版）生成，未经教师审核，待试用反馈修订"
LEAF_CODE = re.compile(r"^[A-Z]{2}-[A-Z]{2}-\d{2}-\d{2}$")


def _path(subject: str) -> Path:
    return DATA_DIR / f"{subject}.yaml"


def _leaves(subject: str):
    _, nodes = _parse(_path(subject))
    parents = {n.parent_code for n in nodes}
    return nodes, [n for n in nodes if n.code not in parents]


def test_exactly_the_expected_files_exist():
    assert {p.stem for p in DATA_DIR.glob("*.yaml")} == set(EXPECTED)


@pytest.mark.parametrize("subject", sorted(EXPECTED))
def test_header_names_source_review_status_and_version(subject):
    head = "\n".join(_path(subject).read_text(encoding="utf-8").splitlines()[:5])
    assert HEADER in head
    assert re.search(r"版本[:：]\s*\d{4}-\d{2}-\d{2}", head)


@pytest.mark.parametrize("subject", sorted(EXPECTED))
def test_subject_band_and_codes(subject):
    prefix, lo, hi = EXPECTED[subject]
    parsed_subject, nodes = _parse(_path(subject))
    assert parsed_subject == Subject(subject)
    doc = yaml.safe_load(_path(subject).read_text(encoding="utf-8"))
    assert doc["grade_band"] == [lo, hi]
    for n in nodes:
        assert n.code.startswith(prefix + "-"), n.code
        assert lo <= n.grade_min <= n.grade_max <= hi, n.code
    _, leaves = _leaves(subject)
    by_code = {n.code: n for n in nodes}
    for leaf in leaves:
        assert LEAF_CODE.match(leaf.code), leaf.code
        # 领域 → 主题 → 知识点: every leaf sits exactly three levels deep
        depth, cur = 0, leaf
        while cur.parent_code is not None:
            depth, cur = depth + 1, by_code[cur.parent_code]
        assert depth == 2, leaf.code


@pytest.mark.parametrize("subject", sorted(EXPECTED))
def test_every_grade_has_15_to_60_leaves(subject):
    _, lo, hi = EXPECTED[subject]
    _, leaves = _leaves(subject)
    for grade in range(lo, hi + 1):
        n = sum(1 for leaf in leaves if leaf.grade_min <= grade <= leaf.grade_max)
        assert 15 <= n <= 60, f"{subject} grade {grade}: {n} leaves"


@pytest.mark.parametrize("subject", sorted(EXPECTED))
def test_leaf_names_unique_within_grade(subject):
    _, leaves = _leaves(subject)
    names = defaultdict(list)
    for leaf in leaves:
        for grade in range(leaf.grade_min, leaf.grade_max + 1):
            names[grade].append(leaf.name)
    for grade, items in names.items():
        dupes = [name for name, c in Counter(items).items() if c > 1]
        assert not dupes, f"{subject} grade {grade}: {dupes}"


def test_codes_unique_across_all_files():
    codes = Counter(n.code for s in EXPECTED for n in _parse(_path(s))[1])
    assert [c for c, k in codes.items() if k > 1] == []


def test_grade5_math_has_points_used_by_test_papers():
    _, leaves = _leaves("math")
    names = [leaf.name for leaf in leaves if leaf.grade_min <= 5 <= leaf.grade_max]
    assert any("小数" in n and "加" in n for n in names), names
    assert any("长方形" in n and "面积" in n for n in names), names
