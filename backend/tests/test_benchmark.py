import csv
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.ai.base import ModelCallError
from app.ai.fake import FakeModel
from app.ai.registry import build_model
from app.grading.schema import GradedPage, GradedQuestion
from scripts.benchmark_models import CaseScore, run_benchmark, score_case


def make_q(no="1", is_correct=True, score=1.0, max_score=2.0):
    return GradedQuestion(
        no=no, question_text="q", student_answer="a", correct_answer="b",
        is_correct=is_correct, score=score, max_score=max_score, confidence=0.9,
        bbox=(0.1, 0.1, 0.5, 0.2),
    )


def page(*qs):
    return GradedPage(student_name=None, questions=list(qs))


def test_score_case_alignment():
    truth = {"questions": [{"no": "1", "is_correct": True, "score": 2},
                           {"no": "2", "is_correct": False, "score": 0}]}
    graded = GradedPage(student_name=None, questions=[make_q(no="1", is_correct=False, score=0)])
    assert score_case(truth, graded) == CaseScore(matched=1, total=2, correct_agree=0, score_abs_err=2.0)


def test_score_case_all_agree():
    truth = {"questions": [{"no": "1", "is_correct": True, "score": 1}, {"no": "2", "is_correct": False, "score": 0}]}
    graded = page(make_q("1", True, 1), make_q("2", False, 0))
    assert score_case(truth, graded) == CaseScore(2, 2, 2, 0.0)


def test_score_case_ignores_extra_model_questions():
    truth = {"questions": [{"no": "1", "is_correct": True, "score": 1}]}
    graded = page(make_q("1", True, 1), make_q("9", False, 0))
    assert score_case(truth, graded) == CaseScore(1, 1, 1, 0.0)


def test_score_case_sums_score_errors():
    truth = {"questions": [{"no": "1", "is_correct": True, "score": 2}, {"no": "2", "is_correct": True, "score": 2}]}
    graded = page(make_q("1", True, 1.5), make_q("2", True, 0.5))
    assert score_case(truth, graded) == CaseScore(2, 2, 2, 2.0)


def _jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "JPEG")
    return buf.getvalue()


def _case(root: Path, cid: str, subject: str, questions: list[dict]):
    d = root / cid
    d.mkdir()
    (d / "page.jpg").write_bytes(_jpeg())
    (d / "truth.json").write_text(
        json.dumps({"subject": subject, "grade": 3, "questions": questions}, ensure_ascii=False), encoding="utf-8")


def _valid(no="1", is_correct=True, score=1.0):
    return page(make_q(no, is_correct, score)).model_dump(mode="json")


@pytest.fixture
def bench(tmp_path):
    root = tmp_path / "bench"
    root.mkdir()
    _case(root, "c1", "math", [{"no": "1", "is_correct": True, "score": 1}, {"no": "2", "is_correct": True, "score": 1}])
    _case(root, "c2", "chinese", [{"no": "1", "is_correct": False, "score": 0}])
    (root / "incomplete").mkdir()  # no files: skipped
    return root


async def test_run_benchmark_rows_and_summary(bench, tmp_path, caplog):
    good = FakeModel([_valid(), _valid(is_correct=False, score=0)])
    flaky = FakeModel([_valid(), ModelCallError("boom")])
    out = tmp_path / "report.csv"
    rows = await run_benchmark(bench, {"good": good, "flaky": flaky}, out)

    by = {(r["model"], r["case_id"]): r for r in rows}
    assert len(rows) == 4
    assert [by[("good", c)]["status"] for c in ("c1", "c2")] == ["ok", "ok"]
    assert by[("flaky", "c1")]["status"] == "ok"
    assert by[("flaky", "c2")]["status"] == "call_error"
    assert by[("good", "c1")]["matched"] == 1 and by[("good", "c1")]["total"] == 2
    assert by[("good", "c2")]["correct_agree"] == 1

    with out.open(encoding="utf-8-sig", newline="") as f:
        per_case = list(csv.DictReader(f))
    assert len(per_case) == 4
    assert list(per_case[0]) == ["case_id", "model", "subject", "status", "matched", "total", "correct_agree",
                                 "score_abs_err", "latency_s", "input_tokens", "output_tokens", "cost_fen"]
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")

    summary_path = tmp_path / "report_summary.csv"
    assert summary_path.read_bytes().startswith(b"\xef\xbb\xbf")
    with summary_path.open(encoding="utf-8-sig", newline="") as f:
        summ = {(r["model"], r["subject"]): r for r in csv.DictReader(f)}
    g = summ[("good", "ALL")]
    assert g["cases"] == "2" and g["ok_cases"] == "2"
    assert float(g["agree_rate"]) == pytest.approx(2 / 2)
    assert float(g["coverage"]) == pytest.approx(2 / 3)
    f_all = summ[("flaky", "ALL")]
    assert f_all["cases"] == "2" and f_all["ok_cases"] == "1"
    assert float(f_all["agree_rate"]) == pytest.approx(1.0)
    assert float(f_all["coverage"]) == pytest.approx(1 / 3)
    assert summ[("flaky", "chinese")]["agree_rate"] == ""  # no matched questions -> empty
    assert summ[("flaky", "chinese")]["coverage"] == "0.0" or float(summ[("flaky", "chinese")]["coverage"]) == 0
    assert "incomplete" in caplog.text


async def test_run_benchmark_invalid_output_and_cost(bench, tmp_path, monkeypatch):
    from app.config import get_settings
    monkeypatch.setitem(get_settings().PRICE_FEN_PER_1K, "fake", (1.0, 1.0))
    bad = FakeModel([{"student_name": None, "questions": "nope"}, _valid()])
    rows = await run_benchmark(bench, {"bad": bad}, tmp_path / "r.csv")
    assert [r["status"] for r in rows] == ["invalid_output", "ok"]
    assert rows[0]["matched"] is None


def test_build_model_validation():
    assert build_model("qwen:qwen-vl-max").provider == "qwen"
    for bad in ("qwen", "qwen:", "gpt:x", ":x", ""):
        with pytest.raises(ValueError):
            build_model(bad)


def test_cli_end_to_end(bench, tmp_path, monkeypatch, capsys):
    import scripts.benchmark_models as bm
    monkeypatch.setattr(bm, "build_model", lambda spec: FakeModel([_valid(), _valid()]))
    out = tmp_path / "cli.csv"
    bm.main(["--dir", str(bench), "--models", "qwen:a", "--out", str(out)])
    assert out.exists() and (tmp_path / "cli_summary.csv").exists()
    assert "qwen:a" in capsys.readouterr().out


async def test_run_benchmark_cost_from_price_table(bench, tmp_path, monkeypatch):
    from app.ai.base import ModelResult
    from app.config import get_settings
    monkeypatch.setitem(get_settings().PRICE_FEN_PER_1K, "m1", (2.0, 4.0))

    class Priced:
        provider = "fake"

        def __init__(self, name):
            self.name = name

        async def complete_json(self, prompt, images):
            return ModelResult(_valid(), 1000, 500, self.name, "fake")

    rows = await run_benchmark(bench, {"p": Priced("m1"), "u": Priced("unknown")}, tmp_path / "c.csv", concurrency=3)
    assert {r["cost_fen"] for r in rows if r["model"] == "p"} == {4.0}
    assert {r["cost_fen"] for r in rows if r["model"] == "u"} == {0.0}
