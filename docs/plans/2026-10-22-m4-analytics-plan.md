# M4 学情与报告 + M2 知识点库 开发计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 老师打开一次作业的学情页就能知道明天先讲哪几道题、学生错成了什么样，能点进低分学生、能导出讲评单和错题单打印；同时导入 1～9 年级全科知识点库，让新批改的题带上知识点。

**Architecture:** 后端新增 `app/analytics`（统计、AI 错因与总结）和 `app/export`（PDF），统计在请求时从 `question_results` 现算，AI 结果和导出文件各有一张表记账。PDF 用 reportlab 排版、嵌入 TrueType 中文字体。小程序新增学情页、题目详情页，扩展成绩详情页；可测试的逻辑放 `src/lib/` 用 Vitest 测。知识点是仓库里每学科一个 YAML，部署时导入。

**Tech Stack:** 后端 Python 3.11 / FastAPI / SQLAlchemy async / Alembic / pytest / reportlab（运行时）/ pypdf（仅测试）；小程序 Taro 4.3 + React 18 + TypeScript + Vitest。

**Spec:** `docs/specs/2026-10-22-m4-analytics-design.md`（上游：`docs/specs/2026-10-20-ai-mistake-book-design.md` 第 9、10 节）

## Global Constraints

- 统计口径：**没拿满分就算错**（`score < max_score`，等价于现有 `is_correct=False`）；每个学生每个题号只算一次（同一学生同一题号有多行时，任一行没满分即算错，得分取各行之和、满分取各行之和）。
- 满分 = 该学生各题 `max_score` 之和；`max_score` 为空的题不计入满分和得分率，也不计入该题正确率的分母。
- 及格：得分率 ≥ 60%。关注：得分率 < 60%，或比全班平均得分率低 ≥ 20 个百分点。讲评单默认前 10 题。学生页最近 5 次作业。这四个值是 `app/analytics/rules.py` 的常量：`PASS_RATIO = 0.6`、`ATTENTION_GAP = 0.20`、`LECTURE_TOP_N = 10`、`RECENT_N = 5`。
- 统计只用 `status == done` 且 `student_id` 不为空的页上的结果。作业里还有排队中 / 批改中 / 没批成 / 没认出学生的页时，接口返回这些张数，界面在概况下提示：「还有 N 张卷子没批完或没认出学生，统计暂未包含」（排队、批改中、没批成、待选学生的页数之和）。
- 待复核数 > 0 时提示：「还有 N 题待复核，统计可能不准」，可点去复核。
- 主观题：`question_results.is_subjective` 为真的题不做错答归组、不生成错因，题目详情改为得分分布。
- AI 生成的文字一律标注「AI 推测」；AI 调用失败时该段不显示，不影响统计接口返回 200。
- 署名：存 `teachers.display_name`（已有 `PATCH /api/me`），为空时 PDF 用「老师」。
- PDF：A4 竖版；签名链接有效 600 秒；文件 7 天后由定时任务删除。
- 新接口一律按老师归属校验，他人或不存在的资源 404。
- 小程序沿用「温暖纸本风」样式变量（`app.scss`）和现有组件；文案不出现错误码或技术术语。
- Windows 环境：Bash 工具遇到中文路径会失败，用 PowerShell；后端 venv 在 `backend/.venv`；小程序编译后开发者工具可能用旧缓存，验收前清编译缓存。提交信息以空行加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 结尾。

## Review Focus

1. **同一个学生同一题号出现两次**（续页误并、重拍等）：老师期望这道题只算这个学生一次，不能把错误人数或平均分算歪。→ 任务 2 测试 `test_duplicate_question_rows_count_once`。
2. **学生没写或没看清**（`student_answer` 为空或全是空白）：应归进「没写 / 没看清」一组，不能和别的错答混在一起，也不能让接口崩掉。→ 任务 2 测试 `test_blank_answers_grouped_as_unanswered`。
3. **部分题没有满分值**（模型没给、没答案卷）：页面照常出数，只是这些题不进得分率。→ 任务 2 测试 `test_questions_without_max_score_are_left_out_of_rates`。
4. **AI 服务超时或报错**：学情和题目详情照常打开，只是没有错因 / 总结。→ 任务 4 测试 `test_cause_generation_failure_returns_groups_without_causes`。
5. **导出时某张错题截图文件已经不在存储里**：PDF 照常生成，那道题不放图、文字照常。→ 任务 6 测试 `test_missing_crop_renders_without_image`。

---

## 一、后端（任务 1–7）

### Task 1: 结果记录是否主观题

**Files:**
- Create: `backend/migrations/versions/0008_question_results_is_subjective.py`
- Modify: `backend/app/models.py`（`QuestionResult`）、`backend/app/grading/pipeline.py`（`_result_row`）、`backend/app/review/router.py`（`_result_out`）
- Test: `backend/tests/test_pipeline.py`、`backend/tests/test_review.py`

**Interfaces:**
- Produces: `QuestionResult.is_subjective: Mapped[bool]`（默认 False，`server_default="0"`）；`_result_out` 多一个键 `"is_subjective"`；有答案卷时取答案项的 `is_subjective`，否则取模型的 `GradedQuestion.is_subjective`。

- [ ] **Step 1: 写失败的测试**

```python
# test_pipeline.py
async def test_is_subjective_from_model_without_key(db, storage, uploaded_page, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[q(no="1", is_subjective=True)])])
    await grade_page(db, storage, model, uploaded_page.id)
    assert (await db.execute(select(QuestionResult))).scalar_one().is_subjective is True

async def test_is_subjective_from_answer_key(db, storage, uploaded_page, confirmed_key_q1_q2, roster_zhangsan):
    confirmed_key_q1_q2[0].is_subjective = True
    await db.commit()
    model = FakeModel([graded(student_name="张三", questions=[q(no="1", is_subjective=False)])])
    await grade_page(db, storage, model, uploaded_page.id)
    assert (await db.execute(select(QuestionResult))).scalar_one().is_subjective is True

# test_review.py
async def test_submission_detail_has_is_subjective(auth_client, graded_submission):
    body = (await auth_client.get(f"/api/submissions/{graded_submission.id}")).json()
    assert all(q["is_subjective"] is False for q in body["questions"])
```

- [ ] **Step 2: 运行确认失败**：`.venv\Scripts\python -m pytest tests/test_pipeline.py tests/test_review.py -q -k subjective` → 3 failed
- [ ] **Step 3: 加列、迁移 0008（`down_revision = "0007"`）、在 `_result_row` 与 `_result_out` 里带上**
- [ ] **Step 4: 全量测试通过**：`.venv\Scripts\python -m pytest -q`
- [ ] **Step 5: 提交** `feat(grading): record whether a question is subjective`

### Task 2: 学情统计核心

**Files:**
- Create: `backend/app/analytics/__init__.py`、`backend/app/analytics/rules.py`、`backend/app/analytics/stats.py`
- Test: `backend/tests/test_analytics_stats.py`

**Interfaces:**
- Produces（`stats.py`，全部为 dataclass，字段名就是接口 JSON 字段名）：
  - `StudentQuestion(question_no: str, score: float, max_score: float | None, wrong: bool, answer: str | None, is_subjective: bool, knowledge_point_id: int | None, crop_keys: list[str], question_text: str | None, correct_answer: str | None)`
  - `StudentResult(student_id: int, student_name: str, submission_id: int, score: float, max_score: float, ratio: float | None, wrong_count: int, questions: list[StudentQuestion])`
  - `QuestionStat(question_no: str, knowledge_point: str | None, wrong_count: int, answered_count: int, accuracy: float | None, top_wrong_answer: str | None, is_subjective: bool)`
  - `AnswerGroup(answer: str, key: str, count: int, students: list[dict])` —— `key` 是规范化后的答案，「没写 / 没看清」组 `key == ""`、`answer == "没写 / 没看清"`；`students` 元素 `{"student_id", "student_name", "submission_id", "score", "max_score"}`
  - `AssignmentStats(counted_students: int, roster_size: int, average_score: float | None, average_ratio: float | None, pass_rate: float | None, pending_review: int, pages_not_counted: int, questions: list[QuestionStat], weak_points: list[dict], attention: list[dict], students: list[StudentResult])`；`weak_points` 元素 `{"name", "wrong_count"}`（最多 3 个）；`attention` 元素 `{"student_id", "student_name", "submission_id", "score", "max_score", "ratio", "wrong_count"}`
  - `async def load_student_results(db: AsyncSession, assignment_id: int) -> list[StudentResult]`
  - `def build_stats(results: list[StudentResult], roster_size: int, pending_review: int, pages_not_counted: int, kp_names: dict[int, str]) -> AssignmentStats`（纯函数，按全局约束计算；`questions` 按 `wrong_count` 降序、题号自然序次之，只列 `wrong_count ≥ 1` 的题）
  - `async def assignment_stats(db: AsyncSession, assignment_id: int) -> AssignmentStats`
  - `def group_wrong_answers(results: list[StudentResult], question_no: str) -> list[AnswerGroup]`（用 `grading.consensus.normalize_answer` 归组，组内展示出现最多的原文；按人数降序，「没写 / 没看清」组排最后）

- [ ] **Step 1: 写失败的测试**（用纯数据构造 `StudentResult` 测 `build_stats` / `group_wrong_answers`，另用数据库夹具测 `assignment_stats`）

```python
def test_overview_numbers():
    s = build_stats([sr("张三", [("1", 2, 2), ("2", 0, 4)]), sr("李四", [("1", 2, 2), ("2", 4, 4)])],
                    roster_size=3, pending_review=1, pages_not_counted=2, kp_names={})
    assert (s.counted_students, s.roster_size, s.pending_review, s.pages_not_counted) == (2, 3, 1, 2)
    assert s.average_score == 4 and s.average_ratio == pytest.approx(4 / 6)
    assert s.pass_rate == 0.5                       # 张三 2/6 < 60%，李四 6/6
    assert [(q.question_no, q.wrong_count, q.accuracy) for q in s.questions] == [("2", 1, 0.5)]

def test_attention_by_ratio_and_gap():
    # 平均 (0.95 + 0.9 + 0.6) / 3 ≈ 0.817；王五 0.6 不低于及格线，但比平均低 ≈ 0.217 ≥ 0.20 → 关注
    s = build_stats([sr("张三", [("1", 19, 20)]), sr("李四", [("1", 18, 20)]), sr("王五", [("1", 12, 20)])], 3, 0, 0, {})
    assert [a["student_name"] for a in s.attention] == ["王五"]

def test_duplicate_question_rows_count_once():
    s = build_stats([sr("王五", [("1", 2, 2), ("1", 0, 2)])], 1, 0, 0, {})
    assert s.questions[0].wrong_count == 1 and s.students[0].max_score == 4

def test_questions_without_max_score_are_left_out_of_rates():
    s = build_stats([sr("张三", [("1", 2, 2), ("2", 1, None)])], 1, 0, 0, {})
    assert s.students[0].max_score == 2 and s.average_ratio == 1.0

def test_weak_points_top3_by_wrong_count(): ...      # 4 个知识点，取错误人次最多的 3 个，名字来自 kp_names

def test_blank_answers_grouped_as_unanswered():
    groups = group_wrong_answers([sr_ans("张三", "13"), sr_ans("李四", " 13 "), sr_ans("王五", None), sr_ans("赵六", "  ")], "5")
    assert [(g.answer, g.count) for g in groups] == [("13", 2), ("没写 / 没看清", 2)]

def test_subjective_question_has_no_top_wrong_answer(): ...

async def test_assignment_stats_counts_only_done_assigned_pages(db, my_assignment, roster_zhangsan, make_done_page, make_page): ...
    # 一张已归属 done 页 + 一张 queued 页 + 一张无学生 done 页 → counted_students == 1, pages_not_counted == 2
```

（`sr` / `sr_ans` 是测试文件内的小工厂：按 `(题号, 得分, 满分)` 构造 `StudentResult`。）

- [ ] **Step 2: 运行确认失败**：`.venv\Scripts\python -m pytest tests/test_analytics_stats.py -q`
- [ ] **Step 3: 实现 `rules.py` 常量与 `stats.py`**；`load_student_results` 一次查询取 done 且有学生的页上全部结果（join `Submission`、`Student`），`pending_review` 用现有「needs_review 且未 reviewed」口径，知识点名一次查出
- [ ] **Step 4: 通过**：同上命令全部 PASS，再跑全量
- [ ] **Step 5: 提交** `feat(analytics): assignment statistics and wrong-answer groups`

### Task 3: 学情接口与学生历史

**Files:**
- Create: `backend/app/analytics/router.py`
- Modify: `backend/app/main.py`（注册 router）
- Test: `backend/tests/test_analytics_api.py`

**Interfaces:**
- Consumes: 任务 2 的 `assignment_stats`、`group_wrong_answers`、`load_student_results`；`assignments.access.own_assignment`
- Produces:
  - `GET /api/assignments/{id}/analytics` → `AssignmentStats` 的 JSON，去掉 `students` 字段
  - `GET /api/assignments/{id}/analytics/questions/{question_no}` → `{"question_no", "question_text", "correct_answer", "is_subjective", "knowledge_point", "wrong_count", "answered_count", "groups": [AnswerGroup...] | [], "score_buckets": [{"label", "count"}] | [], "crops": [{"student_name", "submission_id", "crop_url"}]}`；主观题 `groups == []`、`score_buckets` 为「满分 / 一半及以上 / 一半以下」三档；题号不存在 404
  - `GET /api/submissions/{id}/history` → `[{"assignment_id", "title", "created_at", "score", "max_score", "ratio"}]`：同班同学科、按作业创建时间倒序、最多 `RECENT_N` 条、只含该学生有成绩的作业（包括当前这次）
  - 所有接口他人资源 404
  - `async def student_history(db: AsyncSession, submission_id: int) -> list[dict]`（放在 `app/analytics/stats.py`，history 接口和任务 4 的学生总结共用）

- [ ] **Step 1: 写失败的测试**：`test_analytics_overview`（值与任务 2 一致）、`test_question_detail_groups_and_crops`、`test_subjective_question_detail_has_buckets`、`test_unknown_question_404`、`test_history_same_class_same_subject_latest_five`、`test_other_teacher_gets_404`（三个接口各一次）
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 router**；`crop_url` 用 `storage.signed_url`
- [ ] **Step 4: 通过并跑全量**
- [ ] **Step 5: 提交** `feat(analytics): analytics, question detail and student history endpoints`

### Task 4: AI 错因与学生总结

**Files:**
- Create: `backend/app/analytics/notes.py`、`backend/migrations/versions/0009_ai_notes.py`
- Modify: `backend/app/models.py`（`AiNote`）、`backend/app/config.py`（`MODEL_FOR_ANALYSIS`）、`backend/app/ai/registry.py`（`Purpose` 加 `"analysis"`）、`backend/app/analytics/router.py`
- Test: `backend/tests/test_analytics_notes.py`

**Interfaces:**
- Produces:
  - 表 `ai_notes`：`assignment_id`（FK）、`kind`（`"cause"` | `"summary"`，String(16)）、`ref`（String(128)：错因为 `f"{question_no}:{group_key}"`，总结为 `f"submission:{id}"`）、`fingerprint`（String(64)，输入内容的 sha256）、`text`（Text）；唯一键 `(assignment_id, kind, ref)`
  - `Settings.MODEL_FOR_ANALYSIS: str = "qwen:qwen3-vl-plus"`
  - `async def question_causes(db, model: VisionModel, teacher_id: int, assignment_id: int, question_no: str, groups: list[AnswerGroup], question_text: str | None, correct_answer: str | None) -> dict[str, str]`：只为 `count ≥ 2` 且 `key != ""` 的组生成；指纹（题目、正确答案、组的答案与人数）没变就复用库里的；一次模型调用返回所有缺失组；模型 JSON 形如 `{"causes": [{"key": "...", "cause": "..."}]}`，每条 cause 截到 40 字；记用量 `purpose="analysis"`；`ModelError` 时返回已有的、不抛
  - `async def student_summary(db, model, teacher_id: int, submission_id: int, current: StudentResult, history: list[dict]) -> str | None`：两三句话（截到 120 字），指纹为该学生本次各题对错与得分加历史分数；失败返回 None
  - `POST /api/assignments/{id}/analytics/questions/{question_no}/causes` → `{"causes": {group_key: text}}`
  - `POST /api/submissions/{id}/summary` → `{"summary": str | None}`
  - 模型通过 FastAPI 依赖 `get_analysis_model()`（返回 `get_model("analysis")`）注入，测试里覆盖为 `FakeModel`

- [ ] **Step 1: 写失败的测试**：`test_causes_generated_once_and_cached`（第二次请求不再调模型：`len(fake.prompts) == 1`）、`test_causes_regenerated_when_group_changes`、`test_single_student_and_blank_groups_skipped`、`test_cause_generation_failure_returns_groups_without_causes`（FakeModel 抛 `ModelCallError` → 200，`causes == {}`）、`test_summary_cached_and_usage_recorded`、`test_notes_other_teacher_404`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现模型、迁移 0009、`notes.py`、两个接口**；提示词要求只输出 JSON、中文、面向老师、不出现学生姓名
- [ ] **Step 4: 通过并跑全量**
- [ ] **Step 5: 提交** `feat(analytics): AI wrong-answer causes and student summaries`

### Task 5: PDF 排版

**Files:**
- Create: `backend/app/export/__init__.py`、`backend/app/export/pdf.py`
- Modify: `backend/pyproject.toml`（依赖加 `reportlab`；dev 加 `pypdf`）、`backend/app/config.py`（`PDF_FONT_PATH: str = ""`）、`backend/Dockerfile`（`apt-get install -y --no-install-recommends fonts-wqy-microhei`）
- Test: `backend/tests/test_export_pdf.py`

**Interfaces:**
- Produces（`pdf.py`）：
  - `@dataclass LectureQuestion(question_no: str, question_text: str | None, correct_answer: str | None, accuracy: float | None, wrong_count: int, groups: list[tuple[str, int]], crops: list[bytes])`
  - `@dataclass LectureSheet(class_name: str, title: str, date: str, signature: str, overview: dict, questions: list[LectureQuestion])`；`overview` 键：`average_score`、`pass_rate`、`counted_students`、`roster_size`
  - `@dataclass MistakeItem(question_no: str, question_text: str | None, student_answer: str | None, correct_answer: str | None, score_text: str, crop: bytes | None)`
  - `@dataclass StudentSheet(student_name: str, class_name: str, title: str, date: str, signature: str, items: list[MistakeItem])`
  - `def render_lecture(sheet: LectureSheet) -> bytes`
  - `def render_mistakes(sheets: list[StudentSheet]) -> bytes`（每个学生另起一页；空列表抛 `ValueError`）
  - `def font_path() -> str`：`PDF_FONT_PATH` 非空就用它，否则依次找 `/usr/share/fonts/truetype/wqy/wqy-microhei.ttc`、`C:/Windows/Fonts/simhei.ttf`，都没有抛 `RuntimeError("no CJK font")`
- 排版：A4 竖版，页边距 15 mm；页眉一行（班级 · 作业 · 日期 · 署名），页脚页码；截图按宽度等比缩到版心宽、单张高度不超过 70 mm；个人错题单每题后留 30 mm 空白并印「订正：」

- [ ] **Step 1: 写失败的测试**（用 `pypdf.PdfReader` 抽文字断言）：`test_lecture_contains_header_and_top_questions`、`test_mistakes_one_student_per_page`（2 个学生 → 第 1 页只有张三、第 2 页只有李四）、`test_missing_crop_renders_without_image`（`crop=None` 与损坏的 bytes 都能出 PDF）、`test_chinese_text_extractable`（抽出的文字含「订正」）
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 用 reportlab platypus 实现**；字体用 `TTFont("CJK", font_path(), subfontIndex=0)` 注册；损坏的图片 bytes 跳过
- [ ] **Step 4: 通过并跑全量**
- [ ] **Step 5: 提交** `feat(export): lecture sheet and mistake sheet PDFs`

### Task 6: 导出接口与过期清理

**Files:**
- Create: `backend/app/export/router.py`、`backend/app/export/service.py`、`backend/migrations/versions/0010_exports.py`
- Modify: `backend/app/models.py`（`Export`）、`backend/app/main.py`、`backend/app/jobs/worker.py`（每日清理）
- Test: `backend/tests/test_export_api.py`

**Interfaces:**
- Consumes: 任务 2 `assignment_stats` / `group_wrong_answers` / `load_student_results`，任务 5 的 dataclass 与 `render_*`
- Produces:
  - 表 `exports`：`teacher_id`（FK）、`file_key`（String(255)）、`kind`（String(16)）
  - `POST /api/assignments/{id}/exports`，body `{"kind": "lecture" | "student" | "class_students", "submission_id": int | null}` → 201 `{"url": "/api/files/exports/...pdf?...", "filename": str}`；`student` 必须带本作业的 `submission_id`，该学生没有错题 → 409 `"这位同学这次全对，没有错题可以导出"`；`class_students` 没有任何学生有错题 → 409 同义文案「这次没有同学有错题」；`lecture` 取前 `LECTURE_TOP_N` 题、每题最多 3 张截图；PDF 生成用 `asyncio.to_thread`
  - 文件键 `exports/{teacher_id}/{uuid4().hex}.pdf`；签名链接 600 秒；`filename` 如 `五年级1班-10-22作业-讲评单.pdf`
  - 署名取 `teacher.display_name or "老师"`
  - `async def purge_old_exports(db, storage, now, days=7) -> int`（`app/export/service.py`）；worker 每天 3:30 跑
- 字体缺失等渲染错误 → 500 由全局处理即可，但要记日志

- [ ] **Step 1: 写失败的测试**：`test_export_lecture_returns_signed_pdf_url`（再 GET 这个 url 得到 `%PDF`）、`test_export_student_requires_own_submission`、`test_export_student_all_correct_409`、`test_export_class_students_one_page_each`、`test_export_uses_signature_or_default`、`test_export_other_teacher_404`、`test_purge_old_exports_deletes_files_and_rows`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 通过并跑全量**
- [ ] **Step 5: 提交** `feat(export): export endpoint, signature and 7-day cleanup`

### Task 7: M2 知识点库

**Files:**
- Create: `backend/data/knowledge/{chinese,math,english,politics,science,physics,chemistry,biology,history,geography}.yaml`、`backend/tests/test_knowledge_data.py`
- Move: `backend/data/knowledge/math_primary_sample.yaml` → `backend/tests/fixtures/knowledge_sample.yaml`（并改 `conftest.sample_yaml` 指向新位置）
- Modify: `backend/app/knowledge/loader.py`（`--prune`）、`deploy/remote.sh`（迁移后导入）
- Test: `backend/tests/test_knowledge.py`、`backend/tests/test_knowledge_data.py`

**Interfaces:**
- Produces:
  - 每学科一个文件，格式同现有 YAML（`subject`、`grade_band`、`nodes` 四层：领域 → 主题 → 知识点，叶子可覆写 `grade_band`）；文件头注释：「依据义务教育课程标准（2022 年版）生成，未经教师审核，待试用反馈修订」与版本日期
  - 年级范围：语文 1–9、数学 1–9、英语 3–9、道德与法治 1–9、科学 1–6、物理 8–9、化学 9、生物 7–8、历史 7–9、地理 7–8
  - code 前缀：`CN`、`MA`、`EN`、`PO`、`SC`、`PH`、`CH`、`BI`、`HI`、`GE`，形如 `MA-NA-01-03`，全库唯一
  - `import_yaml(db, path, prune: bool = False) -> int`：`prune=True` 时删除该学科中不在文件里的知识点（`question_results.knowledge_point_id` 由外键 `SET NULL` 置空）；命令行 `python -m app.knowledge.loader --prune data/knowledge/*.yaml`（Windows 下由 argparse 收到已展开的路径；脚本内对含 `*` 的参数自行 glob）
  - `deploy/remote.sh` 在 `alembic upgrade head` 之后执行 `dc run --rm api sh -c 'python -m app.knowledge.loader --prune data/knowledge/*.yaml'`

- [ ] **Step 1: 写失败的测试**
  - `test_knowledge_data.py`：每个文件能被 `_parse` 解析；学科与年级范围如上；每个（学科, 年级）的叶子数在 15～60 之间；全库 code 唯一；叶子名不重复（同学科同年级内）
  - `test_knowledge.py::test_prune_removes_missing_nodes_and_nulls_results`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 生成十个 YAML**（依据课标学段与内容领域；叶子是一节课能讲清的知识点；数学五年级应包含「小数加法」「长方形面积」这类已在测试卷里出现的内容）；实现 `--prune`；改 `remote.sh`
- [ ] **Step 4: 通过并跑全量；本地开发库执行一次导入，确认数量**
- [ ] **Step 5: 提交** `feat(knowledge): grades 1-9 knowledge points for all subjects`

## 二、小程序（任务 8–11）

### Task 8: 学情数据与文案工具

**Files:**
- Create: `miniprogram/src/lib/analytics.ts`、`miniprogram/tests/analytics.test.ts`
- Modify: `miniprogram/src/lib/types.ts`

**Interfaces:**
- Produces（`types.ts`）：`AnalyticsOut`、`QuestionStatOut`、`AnswerGroupOut`、`QuestionDetailOut`、`HistoryItem`、`AttentionStudent`、`WeakPoint`，字段名与任务 2、3 的接口 JSON 一致；`QuestionResultOut` 加 `is_subjective: boolean`
- Produces（`analytics.ts`）：
  - `percent(x: number | null): string` → `"71%"`，null → `"—"`
  - `overviewNotices(a: AnalyticsOut): { text: string; action: 'review' | null }[]` → 待复核提示（action `review`）与未计入页提示，文案见全局约束；都没有返回 `[]`
  - `questionLine(q: QuestionStatOut): string` → `"正确率 50% · 最常见错答「13」"`；主观题或没有错答时只到正确率
  - `historyLine(h: HistoryItem): string` → `"10-22 作业　9 / 14 分（64%）"`
  - `needsSignature(me: { display_name: string | null }): boolean`
  - `AI_LABEL = 'AI 推测'`

- [ ] **Step 1: 写失败的测试**（每个函数 2～3 个用例，含 null、空数组、主观题）
- [ ] **Step 2: 运行确认失败**：`npx vitest run tests/analytics.test.ts`
- [ ] **Step 3: 实现**
- [ ] **Step 4: 通过**：`npx vitest run`；`npx tsc --noEmit` 无输出
- [ ] **Step 5: 提交** `feat(miniprogram): analytics types and text helpers`

### Task 9: 学情页与题目详情页

**Files:**
- Create: `miniprogram/src/pages/analytics/index.tsx`、`index.config.ts`；`miniprogram/src/pages/analytics/question/index.tsx`、`index.config.ts`
- Modify: `miniprogram/src/app.config.ts`（注册两页）、`miniprogram/src/pages/assignment/index.tsx`（底部「看学情」按钮，有成绩时显示）

**Interfaces:**
- Consumes: 任务 3、4 的接口；任务 8 的工具
- 学情页（`/pages/analytics/index?assignmentId=`）：概况三格（平均分、及格率、已出成绩 x/y），`overviewNotices` 提示条（待复核那条可点进复核页）；「错得最多的题」卡片列表（左侧色带：正确率 < 60% 红、< 85% 橙、其余绿；条形进度），点进题目详情；「薄弱知识点」一行（没有就隐藏）；「需要关注的学生」卡片（姓名、分数 / 满分、错 N 题），点进成绩详情页；右上导出按钮先占位，任务 11 接上
- 题目详情页（`/pages/analytics/question/index?assignmentId=&no=`）：题目与正确答案卡片；非主观题显示错答分布（每组卡片：答案、人数、学生名单，下面一行 AI 错因带「AI 推测」小字），进入页面后异步 `POST .../causes` 填上错因；主观题显示得分三档；截图三列网格，点开 `previewImage`；学生名可点进成绩详情
- 加载、找不到、加载失败三种状态沿用现有页面写法

- [ ] **Step 1: 实现两页与入口按钮**
- [ ] **Step 2: `npx tsc --noEmit` 无输出，`npm run build:weapp` 成功**
- [ ] **Step 3: 开发者工具里用测试卷作业打开学情页与第 5 题详情，截图核对**（数字与 `scores` 接口一致；错因异步出现）
- [ ] **Step 4: 提交** `feat(miniprogram): class analytics and question detail pages`

### Task 10: 学生页：最近成绩与 AI 总结

**Files:**
- Modify: `miniprogram/src/pages/results/detail/index.tsx`

**Interfaces:**
- Consumes: `GET /api/submissions/{id}/history`、`POST /api/submissions/{id}/summary`；任务 8 的 `historyLine`、`AI_LABEL`
- 页面顶部在学生姓名卡下加：「最近几次」列表（`historyLine`，当前这次加粗）；「AI 总结」卡（异步加载，失败不显示，标「AI 推测」）；题目列表里部分得分的题显示「得 x / y 分」（已有 `scoreText`）

- [ ] **Step 1: 实现**
- [ ] **Step 2: `tsc` 与 `build:weapp` 通过**
- [ ] **Step 3: 开发者工具核对张三页面**
- [ ] **Step 4: 提交** `feat(miniprogram): student history and AI summary`

### Task 11: 导出与署名

**Files:**
- Create: `miniprogram/src/lib/export.ts`、`miniprogram/src/components/ExportSheet.tsx`、`miniprogram/tests/export.test.ts`
- Modify: `miniprogram/src/pages/analytics/index.tsx`、`miniprogram/src/pages/results/detail/index.tsx`

**Interfaces:**
- Produces（`export.ts`）：
  - `type ExportKind = 'lecture' | 'student' | 'class_students'`
  - `async function exportPdf(assignmentId: number, kind: ExportKind, submissionId?: number): Promise<void>`：`POST .../exports` → `Taro.downloadFile({ url: API_BASE + url })` → `Taro.openDocument({ filePath, fileType: 'pdf', showMenu: true })`
  - `exportErrorText(e: unknown): string`：409 原样显示后端文案，其余走 `errorText`
- `ExportSheet`：底部面板，列出可选导出项（学情页：「班级讲评单」「全班错题单」；学生页：「这位同学的错题单」）和当前署名「署名：王老师　修改」；首次（`needsSignature`）点任一导出项时先弹输入署名（`Taro.showModal` 的 `editable`），保存走 `PATCH /api/me` 后再导出；生成中按钮显示「正在生成…」并防连点

- [ ] **Step 1: 写失败的测试**：`exportErrorText` 对 409 返回后端文案、对网络错误返回现有通用文案；`exportPdf` 依次调用请求、下载、打开（mock `Taro`）
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现并接到两个页面**
- [ ] **Step 4: `vitest`、`tsc`、`build:weapp` 通过；开发者工具里三种导出都能打开 PDF，首次会问署名**
- [ ] **Step 5: 提交** `feat(miniprogram): PDF export with signature`

## 三、收尾（任务 12）

### Task 12: 部署与验收清单

**Files:**
- Create: `docs/benchmark/m4-acceptance.md`

- [ ] **Step 1: 写验收清单**：逐条对应设计第 8 节与本计划 Review Focus，表头同 `m3-acceptance.md`
- [ ] **Step 2: 本地全量**：后端 `pytest -q` 全过；小程序 `vitest`、`tsc`、`build:weapp` 通过
- [ ] **Step 3: 部署**：`powershell -File deploy\deploy.ps1`，日志里出现知识点导入数量与 `{"ok":true}`
- [ ] **Step 4: 在开发者工具里用测试卷作业逐条走验收清单，填写结果**（PDF 下载需关闭域名校验）
- [ ] **Step 5: 提交** `docs: M4 acceptance results`
