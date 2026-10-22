import asyncio

import pytest
from sqlalchemy import func, select

from app.knowledge.loader import import_yaml, main
from app.knowledge.service import candidates
from app.models import KnowledgePoint, QuestionResult


async def test_import_is_idempotent(db, sample_yaml, count_nodes):
    assert await import_yaml(db, sample_yaml) == await import_yaml(db, sample_yaml)
    total = (await db.execute(select(func.count(KnowledgePoint.id)))).scalar()
    assert total == count_nodes(sample_yaml)


async def test_candidates_are_leaves_in_grade(db, sample_yaml):
    await import_yaml(db, sample_yaml)
    names = {k.name for k in await candidates(db, "math", 5)}
    assert "分数加减法" in names and "数与运算" not in names
    assert await candidates(db, "math", 1) == []
    assert await candidates(db, "physics", 5) == []


async def test_sample_has_about_thirty_leaves(db, sample_yaml):
    await import_yaml(db, sample_yaml)
    leaves = await candidates(db, "math", 6)
    assert 28 <= len(leaves) <= 36
    assert [k.code for k in leaves] == sorted(k.code for k in leaves)


def _write(tmp_path, text):
    p = tmp_path / "kp.yaml"
    p.write_text(text, encoding="utf-8")
    return p


async def test_band_inheritance_and_override(db, tmp_path):
    p = _write(
        tmp_path,
        """
subject: math
grade_band: [5, 6]
nodes:
  - code: A
    name: a
    children:
      - {code: A-1, name: inherits}
      - {code: A-2, name: narrower, grade_band: [6, 6]}
""",
    )
    await import_yaml(db, p)
    assert {k.code for k in await candidates(db, "math", 5)} == {"A-1"}
    assert {k.code for k in await candidates(db, "math", 6)} == {"A-1", "A-2"}


async def test_reimport_updates_existing_and_keeps_absent(db, tmp_path):
    v1 = """
subject: math
grade_band: [5, 6]
nodes:
  - code: A
    name: old
    children:
      - {code: A-1, name: one}
  - code: B
    name: other
    children:
      - {code: B-1, name: two}
"""
    v2 = """
subject: math
grade_band: [3, 4]
nodes:
  - code: B
    name: other
    children:
      - {code: A-1, name: renamed}
"""
    await import_yaml(db, _write(tmp_path, v1))
    assert await import_yaml(db, _write(tmp_path, v2)) == 2
    rows = {k.code: k for k in (await db.execute(select(KnowledgePoint))).scalars()}
    assert set(rows) == {"A", "A-1", "B", "B-1"}  # absent codes are kept
    assert rows["A-1"].name == "renamed"
    assert rows["A-1"].parent_id == rows["B"].id  # moved
    assert (rows["A-1"].grade_min, rows["A-1"].grade_max) == (3, 4)


async def test_prune_removes_missing_nodes_and_nulls_results(db, tmp_path, make_done_page):
    v1 = """
subject: math
grade_band: [5, 6]
nodes:
  - code: A
    name: kept
    children:
      - {code: A-1, name: one}
      - {code: A-2, name: dropped leaf}
  - code: B
    name: dropped branch
    children:
      - {code: B-1, name: two}
"""
    v2 = """
subject: math
grade_band: [5, 6]
nodes:
  - code: A
    name: kept
    children:
      - {code: A-1, name: one}
"""
    other = "subject: physics\ngrade_band: [8, 9]\nnodes:\n  - {code: P, name: p}\n"
    await import_yaml(db, _write(tmp_path, other))
    await import_yaml(db, _write(tmp_path, v1))
    ids = {k.code: k.id for k in (await db.execute(select(KnowledgePoint))).scalars()}
    page = await make_done_page(1)
    db.add_all([
        QuestionResult(page_id=page.id, question_no=no, knowledge_point_id=ids[code])
        for no, code in [("1", "A-1"), ("2", "A-2"), ("3", "B-1")]
    ])
    await db.commit()

    assert await import_yaml(db, _write(tmp_path, v2), prune=True) == 2

    codes = {k.code for k in (await db.execute(select(KnowledgePoint))).scalars()}
    assert codes == {"A", "A-1", "P"}  # other subjects untouched
    rows = (
        await db.execute(
            select(QuestionResult.question_no, QuestionResult.knowledge_point_id)
            .order_by(QuestionResult.question_no)
            .execution_options(populate_existing=True)
        )
    ).all()
    assert [tuple(r) for r in rows] == [("1", ids["A-1"]), ("2", None), ("3", None)]


async def test_without_prune_absent_nodes_stay(db, tmp_path):
    await import_yaml(db, _write(tmp_path, "subject: math\ngrade_band: [5, 6]\nnodes:\n  - {code: X, name: x}\n"))
    await import_yaml(db, _write(tmp_path, "subject: math\ngrade_band: [5, 6]\nnodes:\n  - {code: Y, name: y}\n"))
    assert {k.code for k in (await db.execute(select(KnowledgePoint))).scalars()} == {"X", "Y"}


async def test_cli_prune_expands_globs(db, settings, tmp_path, capsys):
    files = tmp_path / "set"
    files.mkdir()
    (files / "a.yaml").write_text("subject: math\ngrade_band: [5, 6]\nnodes:\n  - {code: X, name: x}\n",
                                  encoding="utf-8")
    (files / "b.yaml").write_text("subject: physics\ngrade_band: [8, 9]\nnodes:\n  - {code: P, name: p}\n",
                                  encoding="utf-8")
    await import_yaml(db, _write(tmp_path, "subject: math\ngrade_band: [5, 6]\nnodes:\n  - {code: OLD, name: o}\n"))
    assert await asyncio.to_thread(main, ["--prune", str(files / "*.yaml")]) == 0
    codes = {k.code for k in (await db.execute(select(KnowledgePoint).execution_options(populate_existing=True)))
             .scalars()}
    assert codes == {"X", "P"}
    out = capsys.readouterr().out
    assert "a.yaml" in out and "b.yaml" in out


@pytest.mark.parametrize(
    "body, offender",
    [
        ("subject: nope\ngrade_band: [5, 6]\nnodes:\n  - {code: X1, name: x}\n", "nope"),
        ("subject: math\ngrade_band: [0, 6]\nnodes:\n  - {code: X1, name: x}\n", "X1"),
        ("subject: math\ngrade_band: [5, 13]\nnodes:\n  - {code: X1, name: x}\n", "X1"),
        ("subject: math\ngrade_band: [6, 5]\nnodes:\n  - {code: X1, name: x}\n", "X1"),
        ("subject: math\ngrade_band: [5, 6]\nnodes:\n  - {code: X1, name: x, grade_band: [2, 99]}\n", "X1"),
        (
            "subject: math\ngrade_band: [5, 6]\nnodes:\n  - {code: X1, name: x}\n  - {code: X1, name: y}\n",
            "X1",
        ),
    ],
)
async def test_invalid_yaml_raises_with_offender(db, tmp_path, body, offender):
    with pytest.raises(ValueError, match=offender):
        await import_yaml(db, _write(tmp_path, body))
    assert (await db.execute(select(func.count(KnowledgePoint.id)))).scalar() == 0


async def test_cli_imports_files(db, settings, sample_yaml, capsys):
    # main() runs its own event loop, so call it from a worker thread.
    assert await asyncio.to_thread(main, [str(sample_yaml)]) == 0
    assert "分数加减法" in {k.name for k in await candidates(db, "math", 5)}
    assert "imported" in capsys.readouterr().out
