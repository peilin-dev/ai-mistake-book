"""Generate objective variant questions (Qwen) and verify them blind (DeepSeek).

Local answer comparison (`answers_match`) supports:
- choice: letters A..; a verifier answer may be a letter ("B"), a letter with the
  option text ("B. 40"), or the option text itself ("40").
- judge: 对/正确/√/T/true/是 vs 错/错误/×/F/false/否.
- blank/calc: equal after normalization, or both parse as numbers (integer, decimal,
  fraction a/b, percentage) within 1e-9. A unit may follow the number; numbers are
  compared; if both sides carry different units the result is None.
  Anything else (text answers, mismatched units) returns None -> ask the model.
"""
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelError, VisionModel
from app.ai.usage import record_usage
from app.grading.consensus import normalize_answer
from app.practice.sources import Source

KINDS = ("choice", "blank", "judge", "calc")
_KIND_NAMES = {"choice": "选择题", "blank": "填空题", "judge": "判断题", "calc": "计算题"}
_TOL = 1e-9
_LETTERS = "ABCDEFGH"


@dataclass
class Draft:
    kind: str
    stem: str
    options: list[str] | None
    answer: str


# ---------- local comparison ----------

_TRUE = {"对", "正确", "√", "✓", "t", "true", "是", "yes", "y"}
_FALSE = {"错", "错误", "×", "✗", "x", "f", "false", "否", "不对", "no", "n"}
_NUM = re.compile(r"^([+-]?\d+(?:\.\d+)?|[+-]?\.\d+)(?:/(\d+(?:\.\d+)?))?(%?)(.*)$")
# A unit is a pure token: letters, CJK characters, superscript 2/3; no digits, operators or connectives.
_UNIT = re.compile(r"^[A-Za-z\u4e00-\u9fffµμ²³]+$")
_CONNECTIVES = set("又或和且与及")


def _judge_value(s: str) -> bool | None:
    n = normalize_answer(s).strip("。.")
    if n in _TRUE:
        return True
    if n in _FALSE:
        return False
    return None


def _parse_number(s: str) -> tuple[float, str, str] | None:
    """(value, unit, form) for '40', '0.5', '1/2', '50%', '40平方厘米', '40cm²'; else None."""
    m = _NUM.match(normalize_answer(s).replace("−", "-"))
    if not m:
        return None
    num, den, pct, unit = m.groups()
    try:
        value = float(num)
        if den is not None:
            if float(den) == 0:
                return None
            value /= float(den)
    except ValueError:
        return None
    if pct:
        value /= 100
    if unit[:1] in ("。", "."):
        unit = unit[1:]  # at most one sentence-final dot; ".." or "..." stays and is rejected below
    if unit and (not _UNIT.match(unit) or _CONNECTIVES & set(unit)):
        return None  # trailing text is not a plain unit: not safely comparable
    form = "pct" if pct else ("frac" if den is not None else "num")
    return value, unit, form


def _choice_letter(s: str, options: list[str]) -> str | None:
    raw = (s or "").strip()
    n = len(options)
    key = normalize_answer(raw)
    for i, opt in enumerate(options):
        if key and normalize_answer(opt) == key:
            return _LETTERS[i]
    m = re.match(r"^\(?([A-Za-zＡ-Ｚａ-ｚ])\)?(?:[\s.、．:：)）]+(.*)|())$", raw, re.S)
    if m:
        idx = _LETTERS.find(normalize_answer(m.group(1)).upper())
        if 0 <= idx < n:
            rest = normalize_answer(m.group(2) or "")
            if rest in ("", normalize_answer(options[idx])):
                return _LETTERS[idx]
    return None


def answers_match(kind: str, expected: str, got: str, options: list[str] | None) -> bool | None:
    """True/False when decidable locally, None when a model must judge equivalence."""
    if kind == "choice":
        opts = options or []
        a, b = _choice_letter(expected, opts), _choice_letter(got, opts)
        return a is not None and a == b
    if kind == "judge":
        a, b = _judge_value(expected), _judge_value(got)
        if a is None or b is None:
            return False if (a is None) != (b is None) else None
        return a == b
    if normalize_answer(expected) == normalize_answer(got):
        return True
    a, b = _parse_number(expected), _parse_number(got)
    if a and b:
        if a[1] != b[1] or a[2] != b[2]:
            return None  # different/one-sided units or notations (decimal vs fraction vs %): model decides
        if a[2] == "frac":
            return None  # identical spellings were handled above; "1/2" vs "2/4" is for the model
        return abs(a[0] - b[0]) < _TOL
    return None


def same_answer(draft: Draft, answer: str) -> bool:
    """A fill-in/calculation draft whose answer certainly equals `answer` (a variant should not just
    reuse the source's answer). Choice letters and 对/错 say nothing about the question, so never."""
    return draft.kind in ("blank", "calc") and answers_match(draft.kind, answer, draft.answer, None) is True


# ---------- prompts ----------

def _generate_prompt(source: Source, count: int, avoid_stems: list[str],
                     replacing: tuple[str, str] | None = None) -> str:
    kp = source.knowledge_point or "（未标注）"
    parts = [
        "你是一位小学/中学老师，请根据下面这道学生做错的题，出同类型的变式题。",
        f"年级：{source.grade}年级；学科：{source.subject}；知识点：{kp}",
        f"原题：{source.text}",
        f"原题正确答案：{source.correct_answer}",
        "",
        f"请出 {count} 道题，要求：",
        "1. 与原题考查同一知识点、难度相当，只换数字、情境或问法；答案也应与原题不同。",
        "2. 只出客观题，类型限于 choice（选择）、blank（填空）、judge（判断）、calc（计算）。",
        "3. 纯文字即可作答，不要依赖图片、图表；数学式用纯文本书写。",
        "4. 题目中不得出现任何学生姓名。",
        "5. 选择题给出 options（不含字母的选项文字列表），answer 填字母 A/B/C/D；判断题 answer 填“对”或“错”；填空和计算题 answer 填最终答案。",
        "6. 如果原题无法改写成客观题（如需画图、写作文、简答论述），objective 返回 false，items 为空。",
    ]
    n = 7
    if replacing is not None:
        old_stem, old_answer = replacing
        parts.append(f"{n}. 这道题用来替换下面这道题，题中的数字和答案都必须与它不同，也不能只是交换数字的顺序：")
        parts.append(f"- 被替换的题：{old_stem}（答案：{old_answer}）")
        n += 1
    if avoid_stems:
        parts.append(f"{n}. 不要与下列已有题目重复，也不要只是交换其中数字的顺序：")
        parts.extend(f"- {s}" for s in avoid_stems)
    parts += [
        "",
        '只输出 JSON，不要其他文字：{"objective": true, "items": [{"kind": "choice|blank|judge|calc", "stem": "题干", "options": ["选项1", "选项2"] 或 null, "answer": "答案"}]}',
    ]
    return "\n".join(parts)


def _verify_prompt(draft: Draft) -> str:
    parts = [f"请独立解答下面这道{_KIND_NAMES.get(draft.kind, '题')}，只给出最终答案。", f"题目：{draft.stem}"]
    if draft.kind == "choice":
        for i, opt in enumerate(draft.options or []):
            parts.append(f"{_LETTERS[i]}. {opt}")
        parts.append("答案请只写选项字母。")
    elif draft.kind == "judge":
        parts.append("答案请只写“对”或“错”。")
    else:
        parts.append("如果题目在空格或问句后面已经写出了单位，答案只写数字，不要再写单位。")
    parts.append('只输出 JSON，不要其他文字：{"answer": "你的答案"}')
    return "\n".join(parts)


def _equivalence_prompt(draft: Draft, got: str) -> str:
    return "\n".join([
        "下面是同一道题的两个答案，请严格判断它们是否等价：数值相同且单位相同或等价（如 1米 = 100厘米 等价，40cm 与 40m 不等价），答案必须完整（所有根/解都要有），不能多也不能少；只有书写格式上的差异可以忽略。",
        f"题目：{draft.stem}",
        f"答案一：{draft.answer}",
        f"答案二：{got}",
        '只输出 JSON，不要其他文字：{"equivalent": true 或 false}',
    ])


# ---------- model calls ----------

def _clean_item(raw: object) -> Draft | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    stem = str(raw.get("stem") or "").strip()
    answer = str(raw.get("answer") if raw.get("answer") is not None else "").strip()
    if kind not in KINDS or not stem or not answer:
        return None
    if kind == "judge" and _judge_value(answer) is None:
        return None
    options = None
    if kind == "choice":
        opts = raw.get("options")
        if not isinstance(opts, list) or len(opts) < 2 or len(opts) > len(_LETTERS):
            return None
        options = [str(o).strip() for o in opts]
        if len({normalize_answer(o) for o in options}) != len(options):
            return None
        if _choice_letter(answer, options) is None:
            return None
        answer = _choice_letter(answer, options)
    return Draft(kind, stem, options, answer)


async def generate_drafts(db: AsyncSession, model: VisionModel, teacher_id: int, source: Source,
                          count: int, avoid_stems: list[str],
                          replacing: tuple[str, str] | None = None) -> list[Draft]:
    try:
        result = await model.complete_json(_generate_prompt(source, count, avoid_stems, replacing), [])
    except ModelError:
        return []
    await record_usage(db, teacher_id, "practice_generate", result)
    data = result.data
    if not isinstance(data, dict) or data.get("objective") is False:
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [d for d in map(_clean_item, items) if d]


async def verify_draft(db: AsyncSession, model: VisionModel, teacher_id: int, draft: Draft) -> bool:
    try:
        first = await model.complete_json(_verify_prompt(draft), [])
        await record_usage(db, teacher_id, "practice_verify", first)
        got = first.data.get("answer") if isinstance(first.data, dict) else None
        if got is None or not str(got).strip():
            return False
        got = str(got).strip()
        match = answers_match(draft.kind, draft.answer, got, draft.options)
        if match is not None:
            return match
        second = await model.complete_json(_equivalence_prompt(draft, got), [])
        await record_usage(db, teacher_id, "practice_verify", second)
        eq = second.data.get("equivalent") if isinstance(second.data, dict) else None
        return eq is True
    except ModelError:
        return False


_STEM_NUM = re.compile(r"\d+(?:\.\d+)?(?:/\d+)?", re.ASCII)


def near_key(stem: str) -> tuple[str, ...] | None:
    """The sorted numbers of a stem: '0.7 × 0.4 =' and '0.4×0.7=' share one. None below two numbers,
    where the numbers alone say too little about the question."""
    nums = sorted(_STEM_NUM.findall(normalize_answer(stem)))
    return tuple(nums) if len(nums) >= 2 else None


def dedupe(drafts: list[Draft], existing: list) -> list[Draft]:
    """Drafts that repeat neither each other nor `existing`, in order.

    A repeat is the same stem after normalization, or a near-duplicate: same kind and the same
    numbers (swapped operands, reworded). `existing` holds stems (str, compared with any kind)
    or (kind, stem) pairs.
    """
    exact: set[str] = set()
    near_any: set[tuple[str, ...]] = set()
    near_kind: set[tuple[str, tuple[str, ...]]] = set()

    def remember(kind: str | None, stem: str) -> None:
        exact.add(normalize_answer(stem))
        key = near_key(stem)
        if key is not None and kind is None:
            near_any.add(key)
        elif key is not None:
            near_kind.add((kind, key))

    for e in existing:
        kind, stem = (None, e) if isinstance(e, str) else e
        remember(kind, stem)
    out = []
    for d in drafts:
        key = near_key(d.stem)
        if normalize_answer(d.stem) in exact or (key is not None and (key in near_any or (d.kind, key) in near_kind)):
            continue
        remember(d.kind, d.stem)
        out.append(d)
    return out
