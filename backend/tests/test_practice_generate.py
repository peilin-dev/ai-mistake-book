import pytest

from app.ai.base import ModelCallError, ModelOutputError
from app.ai.fake import FakeModel
from app.models import UsageRecord
from app.practice.generate import Draft, answers_match, dedupe, generate_drafts, verify_draft
from app.practice.sources import Source
from sqlalchemy import select

SRC = Source("3", "长方形长8cm宽5cm，面积是多少？", "40", 7, "长方形面积", 3, "math", None)


def _item(kind="calc", stem="一个长方形长10cm宽4cm，面积是多少？", options=None, answer="40"):
    return {"kind": kind, "stem": stem, "options": options, "answer": answer}


async def test_generate_drops_non_objective_and_unknown_kinds(db, teacher):
    m = FakeModel([{"objective": True, "items": [
        _item(), _item(kind="essay", stem="论述"), _item(kind="choice", stem="选哪个？", options=["38", "40", "13", "26"], answer="B"),
        _item(kind="choice", stem="坏选项", options=None, answer="A"), _item(stem="", answer="1"),
    ]}])
    out = await generate_drafts(db, m, teacher.id, SRC, 2, [])
    assert [d.kind for d in out] == ["calc", "choice"]
    assert out[1].options == ["38", "40", "13", "26"] and out[1].answer == "B"
    rows = (await db.execute(select(UsageRecord))).scalars().all()
    assert [r.purpose for r in rows] == ["practice_generate"]

    m2 = FakeModel([{"objective": False, "items": [_item()]}])
    assert await generate_drafts(db, m2, teacher.id, SRC, 2, []) == []


async def test_generate_model_error_returns_empty(db, teacher):
    assert await generate_drafts(db, FakeModel([ModelCallError("x")]), teacher.id, SRC, 2, []) == []
    assert await generate_drafts(db, FakeModel([ModelOutputError("x")]), teacher.id, SRC, 2, []) == []
    assert await generate_drafts(db, FakeModel([{"items": "oops"}]), teacher.id, SRC, 2, []) == []


async def test_verify_blind_then_local_match(db, teacher):
    d = Draft("calc", "一个长方形长10cm宽4cm，面积是多少？", None, "40")
    m = FakeModel([{"answer": "40 cm²"}])
    assert await verify_draft(db, m, teacher.id, d) is True
    assert len(m.prompts) == 1
    assert "一个长方形长10cm宽4cm" in m.prompts[0]
    assert "40" not in m.prompts[0]  # generator answer not leaked
    rows = (await db.execute(select(UsageRecord))).scalars().all()
    assert [r.purpose for r in rows] == ["practice_verify"]
    m2 = FakeModel([{"answer": "41"}])
    assert await verify_draft(db, m2, teacher.id, d) is False
    assert len(m2.prompts) == 1


async def test_verify_prompt_excludes_answer_for_choice(db, teacher):
    d = Draft("choice", "面积？", ["38", "27", "13", "26"], "B")
    m = FakeModel([{"answer": "B"}])
    assert await verify_draft(db, m, teacher.id, d) is True
    assert "27" in m.prompts[0] and "答案" in m.prompts[0]
    assert "正确答案" not in m.prompts[0]


async def test_verify_text_answer_asks_equivalence(db, teacher):
    d = Draft("blank", "光合作用的场所是什么？", None, "叶绿体")
    m = FakeModel([{"answer": "植物细胞的叶绿体"}, {"equivalent": True}])
    assert await verify_draft(db, m, teacher.id, d) is True
    assert len(m.prompts) == 2
    assert "叶绿体" in m.prompts[1] and "植物细胞的叶绿体" in m.prompts[1]
    m2 = FakeModel([{"answer": "线粒体"}, {"equivalent": False}])
    assert await verify_draft(db, m2, teacher.id, d) is False
    rows = (await db.execute(select(UsageRecord))).scalars().all()
    assert {r.purpose for r in rows} == {"practice_verify"} and len(rows) == 4


def test_choice_answer_text_maps_to_letter():
    opts = ["38", "40", "13", "26"]
    assert answers_match("choice", "B", "B", opts) is True
    assert answers_match("choice", "B", "b", opts) is True
    assert answers_match("choice", "B", "B. 40", opts) is True
    assert answers_match("choice", "B", "B、40", opts) is True
    assert answers_match("choice", "B", "40", opts) is True
    assert answers_match("choice", "B", "38", opts) is False
    assert answers_match("choice", "B", "A", opts) is False
    assert answers_match("choice", "B", "不知道", opts) is False


def test_numeric_and_judge_equivalence():
    assert answers_match("blank", "0.5", "1/2", None) is True
    assert answers_match("blank", "1/2", "50%", None) is True
    assert answers_match("calc", "0.5", "50 %", None) is True
    assert answers_match("calc", "0.5", "0.6", None) is False
    assert answers_match("calc", "40", "40 平方厘米", None) is True
    assert answers_match("calc", "40cm²", "40 cm²", None) is True
    assert answers_match("calc", "40cm", "40 kg", None) is None
    assert answers_match("calc", "３／４", "0.75", None) is True
    assert answers_match("blank", "叶绿体", "叶绿体", None) is True
    assert answers_match("blank", "叶绿体", "线粒体", None) is None
    assert answers_match("judge", "√", "正确", None) is True
    assert answers_match("judge", "对", "T", None) is True
    assert answers_match("judge", "×", "错误", None) is True
    assert answers_match("judge", "对", "false", None) is False
    assert answers_match("judge", "对", "也许", None) is False


async def test_verifier_garbage_or_error_is_unverified(db, teacher):
    d = Draft("calc", "1+1=?", None, "2")
    assert await verify_draft(db, FakeModel([{"foo": 1}]), teacher.id, d) is False
    assert await verify_draft(db, FakeModel([ModelCallError("x")]), teacher.id, d) is False
    assert await verify_draft(db, FakeModel([ModelOutputError("x")]), teacher.id, d) is False
    d2 = Draft("blank", "首都？", None, "北京")
    assert await verify_draft(db, FakeModel([{"answer": "京城"}, {"nope": 1}]), teacher.id, d2) is False
    assert await verify_draft(db, FakeModel([{"answer": "京城"}, ModelCallError("x")]), teacher.id, d2) is False


def test_dedupe_against_existing_and_within():
    a = Draft("calc", "1 + 1 = ?", None, "2")
    b = Draft("calc", "1+1=?", None, "2")
    c = Draft("calc", "2+2=?", None, "4")
    e = Draft("calc", "３+３=?", None, "6")
    assert dedupe([a, b, c], []) == [a, c]
    assert dedupe([a, c, e], ["2 + 2 = ?"]) == [a, e]
    assert dedupe([e], ["3+3=?"]) == []


async def test_prompts_have_no_student_names(db, teacher):
    m = FakeModel([{"objective": True, "items": [_item()]}, {"answer": "40"}])
    drafts = await generate_drafts(db, m, teacher.id, SRC, 2, ["已有题干"])
    await verify_draft(db, m, teacher.id, drafts[0])
    assert "学生姓名" in m.prompts[0]  # instructs the model to avoid names
    gen = m.prompts[0]
    assert SRC.text in gen and "40" in gen and "长方形面积" in gen and "已有题干" in gen
    assert "学生" not in m.prompts[1]