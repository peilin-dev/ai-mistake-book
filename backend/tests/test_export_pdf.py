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
    def sheet(name, cls):
        return StudentSheet(name, cls, "作业", "2026-10-22", "王老师", [MistakeItem("1", "题", "a", "b", "0/5", None)])

    pages = _pages(render_mistakes([sheet("张三", "一班"), sheet("李四", "二班")]))
    assert "一班" in pages[0] and "二班" not in pages[0]
    assert "二班" in pages[1] and "一班" not in pages[1]


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
