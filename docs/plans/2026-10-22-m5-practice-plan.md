# M5 举一反三（练习纸）开发计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 老师在学情页（或学生页）一键生成一张同类题练习纸：通义千问出客观题，DeepSeek 独立验算，只放验算通过的题；可预览、单题「换一道」、导出 PDF（可附答案页）。

**Architecture:** 后端新增 `app/practice`：选源题（`sources.py`）、出题与验算（`generate.py`，纯逻辑 + 模型调用）、后台任务（`jobs.py`，arq）、接口（`router.py`）。练习纸和题目各一张表（迁移 0011）。PDF 在 `export/pdf.py` 增加 `render_practice`，导出走 M4 的导出接口新增两种类型。小程序新增练习纸页（生成进度、预览、换一道、导出），入口在学情页和学生页。

**Tech Stack:** 后端 Python 3.11 / FastAPI / SQLAlchemy async / Alembic / arq / reportlab / pytest；小程序 Taro 4.3 + React 18 + TypeScript + Vitest。

**Spec:** `docs/specs/2026-10-22-m5-practice-design.md`（上游：`docs/specs/2026-10-22-m4-analytics-design.md`）

## Global Constraints

- 只出客观题：选择、填空、判断、计算（`kind` 取值 `choice` / `blank` / `judge` / `calc`）；全学科；主观题（`is_subjective`）和非客观源题跳过。
- 全班选题：正确率 < 85%，按错误人数从多到少，最多 5 道源题；单人选题：本次失分（满分 − 得分）从多到少，满分为空的排最后，最多 5 道源题。每道源题出 2 道同类题。常量放 `app/practice/rules.py`：`ACCURACY_BELOW = 0.85`、`MAX_SOURCES = 5`、`VARIANTS_PER_SOURCE = 2`、`CONCURRENCY = 4`。
- 源题可用条件：有非空题目原文（取全班该题号出现最多的非空 `question_text`）；正确答案可靠——没有确认的答案卷且该题号任一行 `answer_mismatch` 为真则跳过；该题号还有 `needs_review` 且未 `reviewed` 的行则跳过。
- 验算：第一步验算模型只看题干（选择题含选项）独立作答；第二步本地比对，判断不了再调用验算模型只问「两个答案是否等价」。两步都通过才算已验算。只有已验算的题进入练习纸。
- 本地比对规则：规范化（`grading.consensus.normalize_answer`）后相等为一致；都能解析为数值（整数、小数、分数 a/b、百分数）且相差 < 1e-9 为一致；选择题比较选项字母（答案若是选项原文，先映射成字母）；判断题把「对/正确/√/T/true」与「错/错误/×/F/false」归一。
- 出题失败或没验过：该源题自动重出一次，仍不足就少放。至少 1 道已验算题 → 练习纸 `done`（不足时 `partial = true`）；0 道 → `failed`，文案「这次没出成题，请稍后重试」。验算调用失败等同未验算。
- 同一张纸内题干规范化后相同的题不放；「换一道」时把这张纸已有题干传给出题模型并再查重。
- 生成与换题都走 arq 后台任务；同一张纸生成进行中再请求生成 → 不新开任务，直接返回当前这张。
- 保存：全班练习纸每份作业一张（`student_id` 为空），单人每个学生每份作业一张；重新生成覆盖对应那一张。
- 文案：没有可出题的源题 → 409「这次大家做得不错，没有需要练习的题」（单人：「这位同学这次没有需要练习的题」）；部分没出成 → 「部分题目没出成，可以重新生成」；生成中「正在出题…（已完成 x / y 道源题）」。
- 提示词不传学生姓名；用量记录 `purpose` 为 `practice_generate` / `practice_verify`；DeepSeek 单价先按 0（价格表可配置）。
- DeepSeek：新提供方 `deepseek`（`DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`，`DEEPSEEK_API_KEY`）；`MODEL_FOR_PRACTICE_VERIFY` 默认 `deepseek:deepseek-v4-pro`；验算不传图片；只解析最终回复里的 JSON，解析失败按未验算。
- PDF：A4 竖版；页眉同 M4（单人时学生姓名在前）；标题「同类题练习」；每题后留作答空白（同 M4「订正」留白 30 mm）；附答案时从最后另起一页「参考答案」；数学式纯文本。
- 新接口按老师归属校验，他人或不存在的资源 404。小程序沿用温暖纸本风；新代码行内尺寸用 rpx（Taro 不转换行内 px）。
- Windows 环境：Bash 工具遇到中文路径会失败，用 PowerShell；后端 venv 在 `backend/.venv`；小程序用开发构建（生产构建会写入占位地址）；开发者工具改完需清编译缓存。提交信息以空行加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 结尾，多行信息用无 BOM 的文件 `git commit -F`。

## Review Focus

1. **选择题答案写成了选项原文**（模型答「40」而正确选项是「B. 40」）：应判为一致，不能误杀。→ 任务 3 测试 `test_choice_answer_text_maps_to_letter`。
2. **等价写法**（「0.5」「1/2」「50%」；判断题「√」与「正确」）：应判为一致。→ 任务 3 测试 `test_numeric_and_judge_equivalence`。
3. **验算模型回了一段推理文字而不是 JSON / 调用超时**：这道题算未验算，不进纸，任务不崩。→ 任务 3 测试 `test_verifier_garbage_or_error_is_unverified`。
4. **老师快速连点两次「生成练习纸」**：只开一个任务，两次都看到同一张纸的进度。→ 任务 4 测试 `test_second_generate_while_running_returns_same_paper`。
5. **生成还没结束就点「换一道」，或对失败的纸点「换一道」**：明确拒绝（409「还在出题，请稍等」/「这张练习纸没出成，请重新生成」），不打乱进行中的任务。→ 任务 4 测试 `test_replace_rejected_while_running_or_failed`。

---

## 一、后端（任务 1–5）

### Task 1: 接入 DeepSeek 验算模型

**Files:**
- Modify: `backend/app/ai/registry.py`（`_PROVIDERS` 加 `"deepseek": ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY")`）、`backend/app/config.py`（`DEEPSEEK_BASE_URL`、`DEEPSEEK_API_KEY`、`MODEL_FOR_PRACTICE_VERIFY = "deepseek:deepseek-v4-pro"`）、`deploy/.env.example`（加 `DEEPSEEK_API_KEY=`）
- Test: `backend/tests/test_ai.py`

**Interfaces:**
- Produces: `get_model("practice_verify")` 返回 provider 为 `deepseek` 的模型；`get_model("practice_generate")` 仍为 qwen；两者同厂商时仍抛 `ValueError`。

- [ ] **Step 1: 写失败的测试**：`test_deepseek_provider_builds_model`（base_url 默认 `https://api.deepseek.com`、key 来自设置）、`test_practice_verify_defaults_to_deepseek`、`test_practice_verify_same_provider_still_rejected`
- [ ] **Step 2: 运行确认失败**：`.venv\Scripts\python -m pytest tests/test_ai.py -q -k "deepseek or practice_verify"`
- [ ] **Step 3: 实现**
- [ ] **Step 4: 真实冒烟（不进测试套件）**：用本地 `backend/.env` 里的 key，经 `build_model("deepseek:deepseek-v4-pro").complete_json('只输出 JSON：{"answer": "2"}。1+1=?', [])` 调一次；若因 `response_format` 或推理模型限制报错，就在适配层按提供方关闭 `response_format`（或改默认模型为 `deepseek-flash`），把结果与改动写进报告。
- [ ] **Step 5: 全量测试通过并提交** `feat(ai): DeepSeek provider for practice verification`

### Task 2: 练习纸数据与选源题

**Files:**
- Create: `backend/app/practice/__init__.py`、`backend/app/practice/rules.py`、`backend/app/practice/sources.py`、`backend/migrations/versions/0011_practice.py`
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_practice_sources.py`

**Interfaces:**
- Produces:
  - 表 `practice_papers`：`assignment_id`（FK CASCADE）、`student_id`（可空，FK CASCADE）、`status`（String(16)：`queued` / `running` / `done` / `failed`）、`partial`（Boolean，默认 False）、`sources_total` / `sources_done`（Integer）、`error`（String(128) 可空）、`generated_at`（DateTime 可空，任务结束时写入）；唯一键 `(assignment_id, student_key)`，其中 `student_key` 为 Integer 非空（全班 0，单人为 student_id）——MySQL 唯一键不认 NULL 相等。
  - 表 `practice_items`：`paper_id`（FK CASCADE）、`position`（Integer）、`source_no`（String(32)）、`knowledge_point_id`（可空，FK SET NULL）、`kind`（String(8)）、`stem`（Text）、`options`（Text，JSON 数组字符串，非选择题为 null）、`answer`（Text）
  - `rules.py` 常量见全局约束
  - `@dataclass Source(question_no: str, text: str, correct_answer: str, knowledge_point_id: int | None, knowledge_point: str | None, grade: int, subject: str, lost: float | None)`
  - `async def class_sources(db, assignment_id: int) -> list[Source]`：用 M4 `assignment_stats` 的 `questions`（已按错误人数排序），按全局约束过滤、取前 `MAX_SOURCES`
  - `async def student_sources(db, submission_id: int) -> list[Source]`：该学生没拿满分的非主观题，按失分降序（满分为空排最后），同样过滤、取前 `MAX_SOURCES`
  - 正确答案：有确认答案卷用答案项，否则用该题号行上出现最多的非空 `correct_answer`

- [ ] **Step 1: 写失败的测试**：`test_class_sources_below_accuracy_sorted_and_capped`、`test_sources_skip_subjective_and_blank_text`、`test_sources_skip_answer_mismatch_without_key`、`test_sources_skip_unreviewed_needs_review`、`test_student_sources_by_points_lost_null_max_last`、`test_source_text_is_most_common_nonempty`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 加模型、迁移 0011（`down_revision = "0010"`，本地 `alembic upgrade head` 跑通）、实现 `sources.py`**
- [ ] **Step 4: 全量测试通过**
- [ ] **Step 5: 提交** `feat(practice): practice tables and source question selection`

### Task 3: 出题与验算

**Files:**
- Create: `backend/app/practice/generate.py`
- Test: `backend/tests/test_practice_generate.py`

**Interfaces:**
- Consumes: 任务 2 的 `Source`；`app.ai.base.VisionModel` / `ModelError`；`app.ai.usage.record_usage`
- Produces:
  - `@dataclass Draft(kind: str, stem: str, options: list[str] | None, answer: str)`
  - `def answers_match(kind: str, expected: str, got: str, options: list[str] | None) -> bool | None`：按全局约束的本地比对；能判定返回 True/False，判定不了（文字填空等）返回 None
  - `async def generate_drafts(db, model: VisionModel, teacher_id: int, source: Source, count: int, avoid_stems: list[str]) -> list[Draft]`：一次调用出 `count` 道；模型 JSON 形如 `{"objective": bool, "items": [{"kind", "stem", "options", "answer"}]}`；`objective == false` 或 `kind` 不在四种内的条目丢弃；记用量 `practice_generate`；`ModelError` 返回 `[]`
  - `async def verify_draft(db, model: VisionModel, teacher_id: int, draft: Draft) -> bool`：第一次调用只给题干和选项，要求 `{"answer": ...}`；`answers_match` 为 None 时第二次调用给两个答案问 `{"equivalent": bool}`；记用量 `practice_verify`；任何 `ModelError`、JSON 缺字段都返回 False
  - `def dedupe(drafts: list[Draft], existing: list[str]) -> list[Draft]`：按 `normalize_answer(stem)` 去重
  - 提示词：中文；出题提示给题目原文、正确答案、知识点名、年级、学科，要求同知识点同难度、只换数字情境或问法、纯文字可作答、题目里不出现任何学生姓名（也不传给模型）；验算提示要求只输出 JSON

- [ ] **Step 1: 写失败的测试**（FakeModel）：`test_generate_drops_non_objective_and_unknown_kinds`、`test_generate_model_error_returns_empty`、`test_verify_blind_then_local_match`（第一次调用的提示里不含出题答案）、`test_verify_text_answer_asks_equivalence`、`test_choice_answer_text_maps_to_letter`、`test_numeric_and_judge_equivalence`（0.5 / 1/2 / 50%；√ / 正确）、`test_verifier_garbage_or_error_is_unverified`、`test_dedupe_against_existing_and_within`、`test_prompts_have_no_student_names`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 全量测试通过**
- [ ] **Step 5: 提交** `feat(practice): generate and verify variant questions`

### Task 4: 后台任务与接口

**Files:**
- Create: `backend/app/practice/jobs.py`、`backend/app/practice/router.py`
- Modify: `backend/app/jobs/worker.py`（注册 `practice_paper_job`、`practice_replace_job`；startup 里 `ctx["practice_generate_model"]`、`ctx["practice_verify_model"]`）、`backend/app/main.py`
- Test: `backend/tests/test_practice_api.py`、`backend/tests/test_practice_jobs.py`

**Interfaces:**
- Consumes: 任务 2、3
- Produces:
  - `async def run_paper(db, gen_model, verify_model, paper_id: int) -> None`（`jobs.py`）：状态 `running`；按源题以 `asyncio.Semaphore(CONCURRENCY)` 并发出题、验算，每道源题失败重出一次；每完成一道源题 `sources_done += 1` 并提交；最后写入 `practice_items`（按源题顺序、`position` 从 1）、`status`、`partial`、`error`
  - `async def run_replace(db, gen_model, verify_model, item_id: int) -> bool`：同源题出 1 道新题（避开整张纸已有题干），验算通过才替换（`stem/options/answer/kind`），否则保持原题并返回 False
  - arq 函数 `practice_paper_job(ctx, paper_id)`、`practice_replace_job(ctx, item_id)`；任务 id `practice:{paper_id}:{nonce}` / `practice-item:{item_id}:{nonce}`
  - 入队依赖 `get_practice_enqueuer()`（测试里覆盖，同 `get_enqueuer` 写法）
  - `POST /api/assignments/{id}/practice` → 201/200 `PaperOut`（全班）；`POST /api/submissions/{id}/practice` → `PaperOut`（单人）。已有 `queued`/`running` 的那张 → 200 返回它不新开；否则（不存在或已完成/失败）重置为 `queued`、清空题目、入队 → 201。没有可用源题 → 409 文案见全局约束
  - `GET /api/assignments/{id}/practice` 与 `GET /api/submissions/{id}/practice` → 最近一张 `PaperOut`，没有 → 404
  - `GET /api/practice/{paper_id}` → `PaperOut`
  - `POST /api/practice-items/{item_id}/replace` → 202 `{"queued": true}`；纸在 `queued`/`running` → 409「还在出题，请稍等」；纸 `failed` → 409「这张练习纸没出成，请重新生成」
  - `PaperOut = {"id", "scope": "class" | "student", "student_name": str | null, "status", "partial", "sources_total", "sources_done", "error", "generated_at", "items": [{"id", "position", "source_no", "knowledge_point", "kind", "stem", "options", "answer", "replacing": bool}]}`；`replacing` 由 Redis 或表字段标记换题进行中（实现者择一），换题结束后为 false

- [ ] **Step 1: 写失败的测试**：`test_generate_creates_paper_and_enqueues`、`test_second_generate_while_running_returns_same_paper`、`test_regenerate_resets_done_paper`、`test_no_sources_409_class_and_student`、`test_run_paper_keeps_only_verified_and_marks_partial`、`test_run_paper_retries_source_once`、`test_run_paper_zero_items_fails_with_message`、`test_run_paper_progress_counts`、`test_replace_swaps_only_when_verified`、`test_replace_rejected_while_running_or_failed`、`test_practice_endpoints_other_teacher_404`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 全量测试通过**
- [ ] **Step 5: 提交** `feat(practice): background generation, replace and API`

### Task 5: 练习纸 PDF 与导出

**Files:**
- Modify: `backend/app/export/pdf.py`（`PracticeItem`、`PracticeSheet`、`render_practice`）、`backend/app/export/service.py`、`backend/app/export/router.py`
- Test: `backend/tests/test_export_pdf.py`、`backend/tests/test_export_api.py`

**Interfaces:**
- Consumes: 任务 2、4 的表
- Produces:
  - `@dataclass PracticeItem(number: int, kind: str, stem: str, options: list[str] | None, answer: str)`
  - `@dataclass PracticeSheet(class_name: str, title: str, date: str, signature: str, student_name: str | None, items: list[PracticeItem], include_answers: bool)`
  - `def render_practice(sheet: PracticeSheet) -> bytes`：标题「同类题练习」；选择题选项逐行 A./B./…；每题后 30 mm 作答空白；`include_answers` 时最后另起一页「参考答案」列 `1. B` 这样的行
  - `ExportIn` 增加 `kind` 取值 `"practice"`、`"practice_student"` 和字段 `include_answers: bool = True`；`practice_student` 需要本作业的 `submission_id`；对应练习纸不存在或不是 `done` → 409「还没有可以导出的练习纸」
  - 文件名如 `五年级1班-10-22作业-练习纸.pdf`、`五年级1班-10-22作业-张三-练习纸.pdf`

- [ ] **Step 1: 写失败的测试**：`test_practice_pdf_with_and_without_answer_page`（无答案时文字里没有「参考答案」，有答案时最后一页以「参考答案」开头）、`test_practice_pdf_choice_options_and_student_header`、`test_export_practice_class_and_student`（GET 签名链接得 `%PDF`）、`test_export_practice_not_ready_409`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 全量测试通过**
- [ ] **Step 5: 提交** `feat(export): practice sheet PDF`

## 二、小程序（任务 6–7）

### Task 6: 练习纸数据与文案工具

**Files:**
- Create: `miniprogram/src/lib/practice.ts`、`miniprogram/tests/practice.test.ts`
- Modify: `miniprogram/src/lib/types.ts`

**Interfaces:**
- Produces（`types.ts`）：`PracticePaperOut`、`PracticeItemOut`，字段同任务 4 的 `PaperOut`
- Produces（`practice.ts`）：
  - `progressText(p: PracticePaperOut): string` → 「正在出题…（已完成 2 / 5 道源题）」；`queued` 且 `sources_done == 0` 时「正在出题…」
  - `isWorking(p: PracticePaperOut): boolean`（`queued`/`running` 或任一题 `replacing`）
  - `sourceLabel(item: PracticeItemOut): string` → 「第 5 题的同类题」（有知识点时加「 · 知识点名」）
  - `optionLetter(i: number): string` → `A`…
  - `PARTIAL_TEXT = '部分题目没出成，可以重新生成'`、`FAILED_TEXT = '这次没出成题，请稍后重试'`

- [ ] **Step 1: 写失败的测试**（每个函数 2～3 个用例）
- [ ] **Step 2: 运行确认失败**：`npx vitest run tests/practice.test.ts`
- [ ] **Step 3: 实现**
- [ ] **Step 4: `npx vitest run` 与 `npx tsc --noEmit` 通过**
- [ ] **Step 5: 提交** `feat(miniprogram): practice types and text helpers`

### Task 7: 练习纸页与入口

**Files:**
- Create: `miniprogram/src/pages/practice/index.tsx`、`index.config.ts`（标题「同类题练习」）
- Modify: `miniprogram/src/app.config.ts`、`miniprogram/src/pages/analytics/index.tsx`（「生成练习纸」按钮）、`miniprogram/src/pages/results/detail/index.tsx`（「给他出练习」按钮）、`miniprogram/src/components/ExportSheet.tsx` 或新组件（练习纸导出：附答案开关）

**Interfaces:**
- Consumes: 任务 4、5 的接口；任务 6 的工具；M4 的 `exportPdf`、署名流程
- 页面参数：`?assignmentId=`（全班）或 `?submissionId=`（单人）
- 进入页面：先 GET 最近一张；没有（404）就自动 POST 生成；有就直接显示（显示 `generated_at` 生成时间）
- 生成中：显示 `progressText`，每 2 秒轮询 `GET /api/practice/{id}`，页面隐藏或离开时停止；`failed` 显示 `FAILED_TEXT` 和「重新生成」
- 完成：题目卡片列表（序号、`sourceLabel`、题干、选择题选项、答案折叠显示「看答案」）；每题「换一道」（进行中显示「正在换…」并轮询，换题失败时提示「没换成，原题保留」）；`partial` 时顶部提示 `PARTIAL_TEXT`；底部「重新生成」与「导出 PDF」（导出面板里「附答案」开关，默认开，沿用署名流程）
- 409 一律原样显示后端文案

- [ ] **Step 1: 实现页面与入口**
- [ ] **Step 2: `tsc`、`vitest`、开发构建通过**
- [ ] **Step 3: 开发者工具里用测试作业走一遍：学情页生成 → 进度 → 预览 → 换一道 → 导出（附/不附答案）；学生页给单人生成；截图**
- [ ] **Step 4: 提交** `feat(miniprogram): practice sheet page`

## 三、收尾（任务 8）

### Task 8: 部署与验收

**Files:**
- Create: `docs/benchmark/m5-acceptance.md`（格式同 `m4-acceptance.md`，逐条对应设计第 8 节与本计划 Review Focus）

- [ ] **Step 1: 本地全量**：后端 `pytest -q`；小程序 `vitest`、`tsc`、开发构建
- [ ] **Step 2: 服务器 `.env` 加 `DEEPSEEK_API_KEY`**（从本地 `backend/.env` 读取，经 ssh 写入 `~/mistake-book/deploy/.env`，不打印；去掉 `\r`）
- [ ] **Step 3: 部署**：`powershell -File deploy\deploy.ps1`；确认 alembic 到 0011、`{"ok":true}`、worker 日志里注册了两个练习任务
- [ ] **Step 4: 开发者工具里逐条走验收清单并填写结果**（手机上打开 PDF 记为未测：待域名与 HTTPS）
- [ ] **Step 5: 提交** `docs: M5 acceptance results`
