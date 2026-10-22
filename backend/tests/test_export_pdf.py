import io

import pytest
from PIL import Image
from pypdf import PdfReader

from app.export.pdf import (
    LectureQuestion,
    LectureSheet,
    MistakeItem,
    StudentSheet,
    font_path,
    render_lecture,
    render_mistakes,
)


def _jpeg(w=800, h=1200) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "JPEG")
    return buf.getvalue()


def _pages(pdf: bytes) -> list[str]:
    return [p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages]


def _lecture(n=3) -> LectureSheet:
    qs = [
        LectureQuestion(
            question_no=f"{i + 1}",
            question_text=f"求 x 的值 第{i + 1}题",
            correct_answer="x=2",
            accuracy=0.4,
            wrong_count=12 - i,
            groups=[("x=3", 5), ("x=4", 3)],
            crops=[_jpeg()],
        )
        for i in range(n)
    ]
    return LectureSheet(
        class_name="七年级三班",
        title="期中数学",
        date="2026-10-22",
        signature="王老师",
        overview={"average_score": 78.5, "pass_rate": 0.85, "counted_students": 40, "roster_size": 42},
        questions=qs,
    )


def test_lecture_contains_header_and_top_questions():
    pdf = render_lecture(_lecture())
    assert pdf.startswith(b"%PDF")
    text = "".join(_pages(pdf))
    assert "七年级三班" in text
    assert "期中数学" in text
    assert "王老师" in text
    assert "x=3" in text


def test_mistakes_one_student_per_page():
    def sheet(name):
        return StudentSheet(
            student_name=name, class_name="七年级三班", title="期中数学", date="2026-10-22",
            signature="王老师",
            items=[MistakeItem("1", "题干", "错答", "x=2", "0/5", _jpeg())],
        )

    pages = _pages(render_mistakes([sheet("张三"), sheet("李四")]))
    assert len(pages) == 2
    assert "张三" in pages[0] and "李四" not in pages[0]
    assert "李四" in pages[1] and "张三" not in pages[1]


def test_mistake_header_follows_each_students_sheet():
    def sheet(name):
        return StudentSheet(name, "一班", "作业", "2026-10-22", "王老师", [MistakeItem("1", "题", "a", "b", "0/5", None)])

    pages = _pages(render_mistakes([sheet("张三"), sheet("李四")]))
    assert "张三" in pages[0] and "李四" not in pages[0]
    assert "李四" in pages[1] and "张三" not in pages[1]


def test_mistake_header_names_the_student_on_continuation_pages():
    from app.export import pdf as m

    m._register_font()
    assert m._header_text("一班", "作业", "2026-10-22", "王老师", "张三").startswith("张三 · 一班")
    items = [MistakeItem(str(i), "题干", "a", "b", "得 0 / 5 分", _jpeg()) for i in range(1, 5)]
    pages = _pages(render_mistakes([StudentSheet("张三", "一班", "作业", "2026-10-22", "王老师", items)]))
    assert len(pages) > 1
    # the title paragraph is only on page 1, so the name on later pages comes from the header
    assert all("张三" in p for p in pages)
    assert "张三 的错题单" not in pages[1]


def test_mistake_item_heading_has_no_extra_prefix():
    items = [MistakeItem("1", "题", "a", "b", "得 1 / 2 分", None)]
    text = "".join(_pages(render_mistakes([StudentSheet("张三", "一班", "作业", "2026-10-22", "王老师", items)])))
    assert "得 1 / 2 分" in text and "得分" not in text


def test_lecture_notice_when_stats_incomplete():
    lec = _lecture(1)
    assert "统计可能不准" not in "".join(_pages(render_lecture(lec)))
    lec.overview = {**lec.overview, "pending_review": 2, "pages_not_counted": 1}
    text = "".join(_pages(render_lecture(lec))).replace("\n", "")
    assert "还有 2 题待复核，统计可能不准" in text
    assert "还有 1 张卷子没批完或没认出学生，统计暂未包含" in text
    lec.overview = {**lec.overview, "pending_review": 0}
    text = "".join(_pages(render_lecture(lec))).replace("\n", "")
    assert "待复核" not in text and "没认出学生" in text


def test_missing_crop_renders_without_image():
    items = [
        MistakeItem("1", "题干", "a", "b", "0/5", None),
        MistakeItem("2", "题干", "a", "b", "0/5", b"not a jpeg"),
    ]
    pdf = render_mistakes([StudentSheet("张三", "三班", "作业", "2026-10-22", "老师", items)])
    assert pdf.startswith(b"%PDF")
    lec = _lecture(1)
    lec.questions[0].crops = [b"garbage", _jpeg()]
    assert render_lecture(lec).startswith(b"%PDF")


def test_chinese_text_extractable():
    items = [MistakeItem("1", "题干", "a", "b", "0/5", None)]
    pdf = render_mistakes([StudentSheet("张三", "三班", "作业", "2026-10-22", "", items)])
    text = "".join(_pages(pdf))
    assert "订正" in text
    assert "老师" in text  # empty signature falls back to 「老师」


def test_long_chinese_paragraph_wraps_within_page():
    from reportlab.pdfbase import pdfmetrics

    from app.export import pdf as m

    text = "这是一段没有任何空格的很长的中文题干" * 20
    pdf = render_mistakes([
        StudentSheet("张三", "三班", "作业", "2026-10-22", "老师", [MistakeItem("1", text, "a", "b", "0/5", None)])
    ])
    page = PdfReader(io.BytesIO(pdf)).pages[0]
    assert text in page.extract_text().replace("\n", "")
    m._register_font()
    para = m._p(text, m._styles()["body"])
    _, h = para.wrap(m.CONTENT_W, 10000)
    assert h > 3 * 10 * 1.45  # several lines
    assert pdfmetrics.stringWidth(text, m.FONT_NAME, 10) > m.CONTENT_W


def test_header_is_truncated_to_content_width():
    from reportlab.pdfbase import pdfmetrics

    from app.export import pdf as m

    m._register_font()
    long = m._header_text("七年级三班", "很长的作业标题" * 10, "2026-10-22", "王老师")
    fitted = m.fit_header(long)
    assert fitted.endswith("…")
    assert pdfmetrics.stringWidth(fitted, m.FONT_NAME, 9) <= m.CONTENT_W
    assert m.fit_header("短") == "短"
    assert render_lecture(_lecture(1).__class__(**{**_lecture(1).__dict__, "title": "很长的作业标题" * 10})).startswith(b"%PDF")


def test_empty_mistakes_raises():
    with pytest.raises(ValueError):
        render_mistakes([])


def test_many_questions_paginate():
    assert len(_pages(render_lecture(_lecture(10)))) > 1


def test_font_path_setting_and_missing(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "PDF_FONT_PATH", "X:/custom.ttf")
    assert font_path() == "X:/custom.ttf"
    monkeypatch.setattr(settings, "PDF_FONT_PATH", "")
    monkeypatch.setattr("os.path.exists", lambda p: False)
    with pytest.raises(RuntimeError, match="no CJK font"):
        font_path()


@pytest.mark.parametrize(
    "score, max_score, expected",
    [(1, 2, "得 1 / 2 分"), (0, 2, "得 0 / 2 分"), (1.5, 4, "得 1.5 / 4 分"), (3, None, "得 3 分"),
     (0, None, "得 0 分")],
)
def test_score_text(score, max_score, expected):
    from app.analytics.stats import StudentQuestion
    from app.export.service import _score_text

    q = StudentQuestion(question_no="1", score=score, max_score=max_score, wrong=True, answer=None,
                        is_subjective=False, knowledge_point_id=None, crop_keys=[], question_text=None,
                        correct_answer=None)
    assert _score_text(q) == expected


def _practice(include_answers=True, student_name=None):
    from app.export.pdf import PracticeItem, PracticeSheet
    items = [
        PracticeItem(1, "choice", "下列哪个数最大？", ["12", "40", "7", "9"], "B"),
        PracticeItem(2, "calc", "计算 25 × 16", None, "400"),
        PracticeItem(3, "judge", "0.5 等于二分之一。", None, "对"),
    ]
    return PracticeSheet("五年级1班", "10-22作业", "2026-10-22", "王老师", student_name, items, include_answers)


def test_practice_pdf_with_and_without_answer_page():
    from app.export.pdf import render_practice
    without = _pages(render_practice(_practice(include_answers=False)))
    assert "同类题练习" in without[0]
    assert not any("参考答案" in t for t in without)
    with_ans = _pages(render_practice(_practice(include_answers=True)))
    assert len(with_ans) == len(without) + 1
    assert not any("参考答案" in t for t in with_ans[:-1])
    last = with_ans[-1]
    assert "参考答案" in last
    for line in ("1. B", "2. 400", "3. 对"):
        assert line in last


def test_practice_pdf_choice_options_and_student_header():
    from app.export.pdf import render_practice
    pages = _pages(render_practice(_practice(student_name="张三")))
    first = pages[0]
    for line in ("A. 12", "B. 40", "C. 7", "D. 9"):
        assert line in first
    assert "张三 · 五年级1班" in first
    assert "张三" not in _pages(render_practice(_practice()))[0]
