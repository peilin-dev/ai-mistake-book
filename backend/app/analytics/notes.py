"""AI-written notes for the teacher: why a group of students got a question wrong, and a short
summary per student. Cached in ai_notes by a fingerprint of the inputs; AI failures never raise."""
import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelError, VisionModel
from app.ai.registry import get_model
from app.ai.usage import record_usage
from app.analytics.stats import AnswerGroup, StudentQuestion, StudentResult
from app.models import AiNote, KnowledgePoint, Submission

log = logging.getLogger(__name__)

CAUSE_MAX = 40
SUMMARY_MAX = 120
EXCERPT_MAX = 30
MIN_GROUP = 2


def get_analysis_model() -> VisionModel:
    """FastAPI dependency; tests override it."""
    return get_model("analysis")


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


async def _get_note(db: AsyncSession, assignment_id: int, kind: str, ref: str) -> AiNote | None:
    return (await db.execute(
        select(AiNote).where(AiNote.assignment_id == assignment_id, AiNote.kind == kind, AiNote.ref == ref)
    )).scalar_one_or_none()


async def _save_note(db: AsyncSession, assignment_id: int, kind: str, ref: str, fingerprint: str,
                     text: str, existing: AiNote | None) -> None:
    if existing is not None:
        existing.fingerprint = fingerprint
        existing.text = text
        await db.flush()
        return
    try:
        # savepoint: a concurrent request may have stored the same ref first; that must not fail ours
        async with db.begin_nested():
            db.add(AiNote(assignment_id=assignment_id, kind=kind, ref=ref, fingerprint=fingerprint, text=text))
    except IntegrityError:
        log.info("note %s/%s was stored concurrently", kind, ref)


def _cause_ref(question_no: str, key: str) -> str:
    """Bounded and collision-safe: the key is free-text student input of any length."""
    return f"{question_no}:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"

def _clip(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _cause_prompt(question_text: str | None, correct_answer: str | None, groups: list[AnswerGroup]) -> str:
    lines = [f"{i + 1}. 错误答案：{g.answer}（{g.count} 人）" for i, g in enumerate(groups)]
    keys = [g.key for g in groups]
    return (
        "你是一位经验丰富的老师的助手。下面是一道题，以及学生常见的错误答案。"
        "请推测每种错误答案最可能的错因（例如概念混淆、计算失误、审题不清），写给老师看。\n"
        f"题目：{question_text or '（未识别）'}\n"
        f"正确答案：{correct_answer or '（未提供）'}\n"
        "常见错误答案：\n" + "\n".join(lines) + "\n"
        "要求：只输出 JSON，不要输出其他文字；用中文；每条错因不超过 40 个字；"
        "不要出现任何学生姓名。\n"
        f"每种错误答案对应的 key 依次为：{json.dumps(keys, ensure_ascii=False)}。\n"
        '输出格式：{"causes": [{"key": "<上面的 key>", "cause": "<错因>"}]}'
    )


async def question_causes(db: AsyncSession, model: VisionModel, teacher_id: int, assignment_id: int,
                          question_no: str, groups: list[AnswerGroup], question_text: str | None,
                          correct_answer: str | None) -> dict[str, str]:
    eligible = [g for g in groups if g.count >= MIN_GROUP and g.key != ""]
    result: dict[str, str] = {}
    missing: list[AnswerGroup] = []
    pending: dict[str, tuple[str, AiNote | None]] = {}
    for g in eligible:
        ref = _cause_ref(question_no, g.key)
        fp = _fingerprint([question_text, correct_answer, g.answer, g.count])
        note = await _get_note(db, assignment_id, "cause", ref)
        if note is not None and note.fingerprint == fp:
            result[g.key] = note.text
        else:
            missing.append(g)
            pending[g.key] = (fp, note)
    if not missing:
        return result
    try:
        res = await model.complete_json(_cause_prompt(question_text, correct_answer, missing), [])
    except ModelError:
        log.warning("cause generation failed", exc_info=True)
        return result
    await record_usage(db, teacher_id, "analysis", res)
    items = res.data.get("causes") if isinstance(res.data, dict) else None
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("key") not in pending:
            continue
        text = _clip(item.get("cause"), CAUSE_MAX)
        if not text:
            continue
        key = item["key"]
        fp, note = pending.pop(key)
        await _save_note(db, assignment_id, "cause", _cause_ref(question_no, key), fp, text, note)
        result[key] = text
    return result


def _excerpt(text: str | None) -> str | None:
    """Question text squeezed to one line of at most EXCERPT_MAX characters."""
    flat = " ".join((text or "").split())
    if not flat:
        return None
    return flat if len(flat) <= EXCERPT_MAX else flat[:EXCERPT_MAX - 1] + "…"


def _question_facts(q: StudentQuestion, kp_names: dict[int, str]) -> dict:
    """What the summary may know about one question; wrong ones carry 知识点 and a 题目 excerpt."""
    facts = {"no": q.question_no, "wrong": q.wrong, "score": q.score, "max": q.max_score}
    if q.wrong:
        facts["kp"] = kp_names.get(q.knowledge_point_id) if q.knowledge_point_id is not None else None
        facts["text"] = _excerpt(q.question_text)
    return facts


def _question_line(f: dict) -> str:
    line = f"第{f['no']}题{'错' if f['wrong'] else '对'}（{f['score']:g}/{'?' if f['max'] is None else format(f['max'], 'g')}"
    if f.get("kp"):
        line += f"，知识点：{f['kp']}"
    if f.get("text"):
        line += f"，题目：{f['text']}"
    return line + "）"


def _summary_prompt(current: StudentResult, history: list[dict], kp_names: dict[int, str] | None = None) -> str:
    qs = "；".join(_question_line(_question_facts(q, kp_names or {})) for q in current.questions)
    past = "；".join(
        f"{h['score']:g}/{h['max_score']:g}" for h in history if h.get("max_score")) or "无"
    return (
        "你是一位经验丰富的老师的助手。请根据下面一名学生本次作业的情况，用两三句话总结，写给老师看："
        "指出哪类题、哪个知识点容易错，并结合历次成绩说明趋势。\n"
        f"本次总分：{current.score:g}/{current.max_score:g}\n"
        f"各题情况：{qs}\n"
        f"最近几次作业得分（新到旧，含本次）：{past}\n"
        "要求：只输出 JSON，不要输出其他文字；用中文；不超过 120 个字；不要出现学生姓名。\n"
        '输出格式：{"summary": "<总结>"}'
    )


async def _kp_names(db: AsyncSession, current: StudentResult) -> dict[int, str]:
    ids = {q.knowledge_point_id for q in current.questions if q.wrong and q.knowledge_point_id is not None}
    if not ids:
        return {}
    return dict((await db.execute(
        select(KnowledgePoint.id, KnowledgePoint.name).where(KnowledgePoint.id.in_(ids))
    )).all())


async def student_summary(db: AsyncSession, model: VisionModel, teacher_id: int, submission_id: int,
                          current: StudentResult, history: list[dict]) -> str | None:
    sub = await db.get(Submission, submission_id)
    if sub is None:
        return None
    assignment_id = sub.assignment_id
    ref = f"submission:{submission_id}"
    kp_names = await _kp_names(db, current)
    fp = _fingerprint([
        [_question_facts(q, kp_names) for q in current.questions],
        [[h["assignment_id"], h["score"], h["max_score"]] for h in history],
    ])
    note = await _get_note(db, assignment_id, "summary", ref)
    if note is not None and note.fingerprint == fp:
        return note.text
    try:
        res = await model.complete_json(_summary_prompt(current, history, kp_names), [])
    except ModelError:
        log.warning("summary generation failed", exc_info=True)
        return None
    await record_usage(db, teacher_id, "analysis", res)
    text = _clip(res.data.get("summary") if isinstance(res.data, dict) else None, SUMMARY_MAX)
    if not text:
        return None
    await _save_note(db, assignment_id, "summary", ref, fp, text, note)
    return text