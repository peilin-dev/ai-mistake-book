"""Pure rendering of the class lecture sheet and per-student mistake sheets to A4 PDF bytes."""

import io
import os
import threading
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

from app.config import get_settings

FONT_NAME = "CJK"
MARGIN = 15 * mm
CONTENT_W = A4[0] - 2 * MARGIN
MAX_CROP_H = 70 * mm
CORRECTION_SPACE = 30 * mm
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "C:/Windows/Fonts/simhei.ttf",
)


@dataclass
class LectureQuestion:
    question_no: str
    question_text: str | None
    correct_answer: str | None
    accuracy: float | None
    wrong_count: int
    groups: list[tuple[str, int]] = field(default_factory=list)
    crops: list[bytes] = field(default_factory=list)


@dataclass
class LectureSheet:
    class_name: str
    title: str
    date: str
    signature: str
    overview: dict
    questions: list[LectureQuestion]


@dataclass
class MistakeItem:
    question_no: str
    question_text: str | None
    student_answer: str | None
    correct_answer: str | None
    score_text: str
    crop: bytes | None


@dataclass
class StudentSheet:
    student_name: str
    class_name: str
    title: str
    date: str
    signature: str
    items: list[MistakeItem]


def font_path() -> str:
    configured = get_settings().PDF_FONT_PATH
    if configured:
        return configured
    for candidate in _FONT_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    raise RuntimeError("no CJK font")


_font_lock = threading.Lock()


def _register_font() -> None:
    with _font_lock:
        if FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return
        pdfmetrics.registerFont(TTFont(FONT_NAME, font_path(), subfontIndex=0))


def _style(name: str, size: float, leading: float | None = None, **kw) -> ParagraphStyle:
    return ParagraphStyle(
        name, fontName=FONT_NAME, fontSize=size, leading=leading or size * 1.45, wordWrap="CJK", **kw
    )


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": _style("title", 16, spaceAfter=3 * mm),
        "h": _style("h", 12, spaceBefore=4 * mm, spaceAfter=1.5 * mm),
        "body": _style("body", 10),
        "small": _style("small", 9, textColor="#444444"),
    }


def _p(text: str | None, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def _image(data: bytes | None) -> RLImage | None:
    """Scale to the content width, at most MAX_CROP_H high; None when the bytes are unusable."""
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            w, h = im.size
            if not w or not h:
                return None
            rgb = im.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=85)
        buf.seek(0)
    except Exception:
        return None
    scale = min(CONTENT_W / w, MAX_CROP_H / h)
    return RLImage(buf, width=w * scale, height=h * scale)


def fit_header(text: str, size: float = 9, max_width: float = CONTENT_W) -> str:
    """Truncate with an ellipsis so the header never runs past the content width."""
    if pdfmetrics.stringWidth(text, FONT_NAME, size) <= max_width:
        return text
    while text and pdfmetrics.stringWidth(text + "…", FONT_NAME, size) > max_width:
        text = text[:-1]
    return text + "…"


def _doc(buf: io.BytesIO, header: str, header_fn=None) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
        title=header,
    )
    frame = Frame(
        MARGIN, MARGIN + 6 * mm, CONTENT_W, A4[1] - 2 * MARGIN - 12 * mm,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )

    def decorate(canvas, d):
        canvas.saveState()
        canvas.setFont(FONT_NAME, 9)
        canvas.drawString(MARGIN, A4[1] - MARGIN, fit_header(header_fn(d) if header_fn else header))
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN, A4[1] - MARGIN - 2 * mm, A4[0] - MARGIN, A4[1] - MARGIN - 2 * mm)
        canvas.drawCentredString(A4[0] / 2, MARGIN - 3 * mm, f"- {d.page} -")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPageEnd=decorate)])
    return doc


def _header_text(class_name: str, title: str, date: str, signature: str, student_name: str | None = None) -> str:
    parts = [class_name, title, date, signature or "老师"]
    return " · ".join([student_name, *parts] if student_name else parts)


def _notice(ov: dict) -> str | None:
    """The same caveats the analytics page shows, so a printed sheet isn't read as complete."""
    parts = []
    if ov.get("pending_review", 0) > 0:
        parts.append(f"还有 {ov['pending_review']} 题待复核，统计可能不准")
    if ov.get("pages_not_counted", 0) > 0:
        parts.append(f"还有 {ov['pages_not_counted']} 张卷子没批完或没认出学生，统计暂未包含")
    return "；".join(parts) if parts else None


def _pct(v) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def render_lecture(sheet: LectureSheet) -> bytes:
    _register_font()
    st = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, _header_text(sheet.class_name, sheet.title, sheet.date, sheet.signature))
    ov = sheet.overview
    avg = ov.get("average_score")
    story = [
        _p(f"{sheet.class_name} 班级错题讲评单", st["title"]),
        _p(
            f"平均分 {'—' if avg is None else f'{avg:.1f}'}　及格率 {_pct(ov.get('pass_rate'))}　"
            f"统计 {ov.get('counted_students', 0)} 人 / 名册 {ov.get('roster_size', 0)} 人",
            st["body"],
        ),
    ]
    notice = _notice(ov)
    if notice:
        story.append(_p(f"注意：{notice}", st["small"]))
    for q in sheet.questions:
        block = [
            _p(f"第 {q.question_no} 题　正确率 {_pct(q.accuracy)}　错 {q.wrong_count} 人", st["h"]),
        ]
        if q.question_text:
            block.append(_p(q.question_text, st["body"]))
        if q.correct_answer:
            block.append(_p(f"参考答案：{q.correct_answer}", st["body"]))
        if q.groups:
            block.append(_p("常见错答：" + "；".join(f"{a}（{n} 人）" for a, n in q.groups), st["body"]))
        story.append(KeepTogether(block))
        for crop in q.crops:
            img = _image(crop)
            if img is not None:
                story.extend([Spacer(1, 1.5 * mm), img])
    doc.build(story)
    return buf.getvalue()


def render_mistakes(sheets: list[StudentSheet]) -> bytes:
    if not sheets:
        raise ValueError("no student sheets")
    _register_font()
    st = _styles()
    buf = io.BytesIO()
    by_page: dict[int, StudentSheet] = {}

    def header(d):
        s = by_page.get(d.page, sheets[0])
        return _header_text(s.class_name, s.title, s.date, s.signature, s.student_name)

    doc = _doc(buf, "", header)
    story = []
    for i, sheet in enumerate(sheets):
        if i:
            story.append(PageBreak())
        story.append(_p(f"{sheet.student_name} 的错题单", st["title"]))
        if not sheet.items:
            story.append(_p("本次没有错题。", st["body"]))
        for it in sheet.items:
            block = [_p(f"第 {it.question_no} 题　{it.score_text}", st["h"])]
            if it.question_text:
                block.append(_p(it.question_text, st["body"]))
            img = _image(it.crop)
            if img is not None:
                block.append(Spacer(1, 1.5 * mm))
                block.append(img)
            block.append(_p(f"我的答案：{it.student_answer or '—'}", st["body"]))
            block.append(_p(f"参考答案：{it.correct_answer or '—'}", st["body"]))
            block.append(_p("订正：", st["body"]))
            block.append(Spacer(1, CORRECTION_SPACE))
            story.append(KeepTogether(block))
    _SheetTracker.install(doc, sheets, by_page)
    doc.build(story)
    return buf.getvalue()


class _SheetTracker:
    """Records which student each page belongs to so the header is right on every page."""

    @staticmethod
    def install(doc: BaseDocTemplate, sheets: list[StudentSheet], by_page: dict[int, StudentSheet]) -> None:
        by_name_marker = {f"{s.student_name} 的错题单": s for s in sheets}
        current = {"s": sheets[0]}
        orig = doc.afterFlowable

        def after(flowable):
            orig(flowable)
            if isinstance(flowable, Paragraph):
                s = by_name_marker.get(flowable.getPlainText())
                if s is not None:
                    current["s"] = s
            by_page[doc.page] = current["s"]

        doc.afterFlowable = after
