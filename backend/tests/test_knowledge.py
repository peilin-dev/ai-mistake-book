import asyncio

import pytest
from sqlalchemy import func, select

from app.knowledge.loader import import_yaml, main
from app.knowledge.service import candidates
from app.models import KnowledgePoint


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
