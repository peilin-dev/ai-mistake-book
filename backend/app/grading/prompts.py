from app.models import AnswerItem, KnowledgePoint

SUBJECT_NAMES = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "history": "历史",
    "geography": "地理",
    "politics": "政治",
    "science": "科学",
    "other": "其他",
}

# Shape of spec section 7.1; values are placeholders, not an answer to copy.
OUTPUT_SHAPE = """{
  "student_name": "卷头姓名，识别不到填 null",
  "questions": [
    {
      "no": "题号，字符串",
      "question_text": "题目原文",
      "student_answer": "学生作答，未作答填 null",
      "correct_answer": "正确答案",
      "is_subjective": false,
      "is_correct": false,
      "score": 0,
      "max_score": 4,
      "confidence": 0.92,
      "bbox": [0.08, 0.31, 0.92, 0.45],
      "knowledge_point_id": 1234,
      "error_reason": "做错时简述错因，做对填 null"
    }
  ]
}"""


def _fmt_score(value: float | None) -> str:
    if value is None:
        return ""
    return f"（满分 {value:g} 分）"


def build_grading_prompt(
    subject: str, grade: int, answer_items: list[AnswerItem], kps: list[KnowledgePoint]
) -> str:
    subject_name = SUBJECT_NAMES.get(subject, subject)
    lines = [
        f"你是一名{grade}年级{subject_name}老师。图片是一张学生作业或试卷的照片，请逐题批改。",
        "",
        "要求：",
        "1. 识别卷头的学生姓名填入 student_name，识别不到填 null。",
        "2. 逐题识别题号 no、题目 question_text、学生作答 student_answer（未作答填 null）。",
        "3. 判断 is_correct，给出得分 score 与满分 max_score，score 不得超过 max_score；主观题 is_subjective 填 true。",
        "4. confidence 为你对本题判断的把握程度，取值 0 到 1。",
        "5. bbox 为该题（题目加作答）在图片中的位置，相对坐标 [x1, y1, x2, y2]，取值 0 到 1，"
        "以图片左上角为原点，且 x1 < x2、y1 < y2。",
        "6. 做错的题在 error_reason 中简述错因，做对填 null。",
        "",
    ]
    if answer_items:
        lines.append("本作业已确认的标准答案（按题号）：")
        for item in answer_items:
            lines.append(f"第 {item.question_no} 题：{item.answer}{_fmt_score(item.max_score)}")
        lines.append("有标准答案的题以标准答案为准判断对错，correct_answer 填标准答案；其余题请你自行解答。")
    else:
        lines.append("本作业没有提供标准答案，请你自行解题，correct_answer 填你的解答。")
    lines.append("")
    lines.append("知识点候选（id: 名称）：")
    if kps:
        lines.extend(f"{kp.id}: {kp.name}" for kp in kps)
    else:
        lines.append("（无候选）")
    lines.append("knowledge_point_id 必须是上面候选中的一个 id；没有合适的候选时填 null。")
    lines.append("")
    lines.append("只输出一个 JSON 对象，不要输出任何其他文字，也不要使用 Markdown 代码块。格式严格如下：")
    lines.append(OUTPUT_SHAPE)
    return "\n".join(lines)
