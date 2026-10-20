# M3 老师端小程序（最小可用版）开发计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做出老师端微信小程序最小可用版（登录、建班、名单、作业、答案卷、连拍上传、进度、复核、成绩），并补齐它需要的 4 项后端改动。

**Architecture:** 后端改动沿用 M1 的 FastAPI 模块与按作业加锁的写入方式。小程序用 Taro + React + TypeScript，放在仓库 `miniprogram/`；可测试的逻辑（请求封装、上传队列、文案映射、学科、名单预览、缩图尺寸、轮询判断）放在 `src/lib/` 的纯模块里用 Vitest 测试，页面只做组合与展示。

**Tech Stack:** 后端 Python 3.11 / FastAPI / SQLAlchemy async / Alembic / pytest；前端 Taro 4.x、React 18、TypeScript、Vitest。

**Spec:** `docs/specs/2026-10-21-m3-miniprogram-design.md`（上游：`docs/specs/2026-10-20-ai-mistake-book-design.md`）

## Global Constraints

- 反目标："复杂、不方便使用"。首页到"开始拍卷"不超过 3 次点击；能给默认值的都给；错误提示说清"发生了什么、该怎么做"，不出现错误码和技术术语。
- 小程序代码放 `miniprogram/`；框架 Taro 4.x + React + TypeScript；单元测试 Vitest。
- 接口基地址来自环境变量 `TARO_APP_API_BASE`（`.env.development` / `.env.production`）。
- 上传：**按拍摄顺序逐张上传**；单张失败自动重试 2 次；上传前把长边缩到 ≤ 2000px 再转 JPEG。
- 作业页轮询间隔 3 秒，所有页面结束（done/failed）或离开页面时停止。
- 班级年级选择器只提供 1–9。
- 学科（中文显示）：1–6 年级 `chinese 语文, math 数学, english 英语, science 科学, politics 道德与法治, other 其他`；7–9 年级在此基础上加 `physics 物理, chemistry 化学, biology 生物, history 历史, geography 地理`。
- 后端：老师只能访问自己的数据，他人或不存在的资源一律 404；新接口都要测试。
- 固定文案：429 →"本月批改额度已用完"；503（上传）→"已收到，稍后会自动开始批改"；无答案卷标注"本次没有答案卷，答案由 AI 判断"；删除有成绩的学生 409 →"已有成绩的学生不能删除，可以改名"。
- 失败原因文案：`unreadable` →"看不清，请重拍这张"；`model_output_invalid` →"这张没批出来，请重拍"；`model_unavailable` / `internal_error` →"批改服务暂时出错，点重试"。
- Windows 环境：Bash 工具遇到含中文的命令会失败，用 PowerShell；后端 venv 在 `backend/.venv`；提交信息以空行加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 结尾。

## Review Focus

1. **复核页停留超过 10 分钟后图片打不开**（签名 URL 过期）：老师应看到图片自动重新加载，而不是空白。→ 任务 12 测试 `refreshesExpiredImageUrls`。
2. **连拍过程中登录过期**（401）：上传应自动重新登录后继续，不丢张、不打乱顺序。→ 任务 5 测试 `relogsInOnceOn401`，任务 7 测试 `continuesAfterReloginMidQueue`。
3. **上传还没完成就离开拍照页**：必须提示"还有 N 张没传完"，不能悄悄丢失。→ 任务 7 测试 `pendingCountForLeaveGuard`。
4. **作业所在班级还没有名单**：批改照常进行但所有卷子都是"未识别学生"；作业页应提示先导入名单。→ 任务 10 测试 `rosterEmptyHint`。
5. **没有答案卷时，全班多数答案正好打平**（例如 2 人得 A、2 人得 B）：不能随意认定一方是对的，打平的题全部进复核。→ 任务 4 测试 `test_tie_flags_all`。

---

## 一、后端改动（任务 1–4）

### Task 1: 学生改名与删除

**Files:**
- Modify: `backend/app/classes/router.py`
- Test: `backend/tests/test_classes.py`

**Interfaces:**
- Produces: `PATCH /api/students/{id} {name?, student_no?}` → `StudentOut`；`DELETE /api/students/{id}` → 204。挂在一个 `prefix="/api/students"` 的新 router 上（同文件），并在 `app/main.py` 注册。
- 规则：name 去空白后 1–64 字；student_no 可为 null；归属通过 student → class → teacher 校验，他人 404；删除时若存在该学生的 `Submission` 或 `Page.student_id` 指向他，返回 409，detail `"已有成绩的学生不能删除，可以改名"`。

- [ ] **Step 1: 写失败的测试**

```python
async def test_rename_student(auth_client, my_class, db):
    s = await add_student(db, my_class, "张三")
    r = await auth_client.patch(f"/api/students/{s.id}", json={"name": " 张珊 ", "student_no": "2024001"})
    assert r.status_code == 200 and r.json()["name"] == "张珊" and r.json()["student_no"] == "2024001"

async def test_delete_student_without_results(auth_client, my_class, db):
    s = await add_student(db, my_class, "李四")
    assert (await auth_client.delete(f"/api/students/{s.id}")).status_code == 204

async def test_cannot_delete_student_with_results(auth_client, graded_submission):
    r = await auth_client.delete(f"/api/students/{graded_submission.student_id}")
    assert r.status_code == 409 and r.json()["detail"] == "已有成绩的学生不能删除，可以改名"

async def test_foreign_student_404(auth_client, other_class_student):
    assert (await auth_client.patch(f"/api/students/{other_class_student.id}", json={"name": "x"})).status_code == 404
    assert (await auth_client.delete(f"/api/students/{other_class_student.id}")).status_code == 404
```

（`add_student` 为测试内小工具；`graded_submission`、`other_class_student` 已在 conftest。）
- [ ] **Step 2:** `cd backend; .venv\Scripts\python -m pytest tests/test_classes.py -q`，预期新测试 FAIL（404/405）。
- [ ] **Step 3:** 实现两个接口。
- [ ] **Step 4:** 再跑，PASS。
- [ ] **Step 5:** 提交 `feat: rename and delete students`。

---

### Task 2: 替换失败的卷子

**Files:**
- Modify: `backend/app/assignments/router.py`（复用 `read_limited`、`sniff_image`、`lock_assignment`、`check_quota`、`_enqueue_or_503`）
- Test: `backend/tests/test_upload.py`

**Interfaces:**
- Produces: `POST /api/pages/{page_id}:replace`（multipart `file`）→ `PageUploadOut`（`duplicate=false`，HTTP 200）。
- 规则：页面归属校验（他人 404）；仅 `status == failed` 可替换，否则 409 detail `"只有失败的卷子可以重拍"`；类型/大小检查同上传（415/413）；同一作业中已有相同 sha256 的**其他**页面 → 409 detail `"这张照片已经传过了"`；占用额度（429 同上传）；在 `lock_assignment` 下：删除该页旧结果和旧裁剪图（复用 pipeline 的 `_clear_results` 思路，旧 submission 重算）、`student_id`/`recognized_name` 置空、写新原图（key 规则不变，扩展名按新图）、新 `image_sha256`、`original_deleted_at=None`、`status=queued`、`fail_reason=None`、`retry_count += 1`；提交后按 `grade_job_id(page_id, retry_count)` 入队。`seq` 不变。

- [ ] **Step 1: 写失败的测试**

```python
async def test_replace_failed_page_keeps_seq(auth_client, failed_page, make_jpeg, enqueued):
    r = await auth_client.post(f"/api/pages/{failed_page.id}:replace", files={"file": ("n.jpg", make_jpeg(9), "image/jpeg")})
    body = r.json()
    assert r.status_code == 200 and body["seq"] == failed_page.seq and body["status"] == "queued"
    assert enqueued[-1] == failed_page.id

async def test_replace_only_failed_pages(auth_client, uploaded_page, make_jpeg):
    r = await auth_client.post(f"/api/pages/{uploaded_page.id}:replace", files={"file": ("n.jpg", make_jpeg(9), "image/jpeg")})
    assert r.status_code == 409 and r.json()["detail"] == "只有失败的卷子可以重拍"

async def test_replace_with_existing_photo_409(auth_client, failed_page, second_page_bytes):
    r = await auth_client.post(f"/api/pages/{failed_page.id}:replace", files={"file": ("n.jpg", second_page_bytes, "image/jpeg")})
    assert r.status_code == 409 and r.json()["detail"] == "这张照片已经传过了"

async def test_replace_foreign_page_404(auth_client, other_teacher_failed_page, make_jpeg):
    r = await auth_client.post(f"/api/pages/{other_teacher_failed_page.id}:replace", files={"file": ("n.jpg", make_jpeg(9), "image/jpeg")})
    assert r.status_code == 404

async def test_replace_clears_old_results(auth_client, failed_page_with_results, make_jpeg, db):
    await auth_client.post(f"/api/pages/{failed_page_with_results.id}:replace", files={"file": ("n.jpg", make_jpeg(9), "image/jpeg")})
    assert await count_results(db, failed_page_with_results.id) == 0
```

（conftest 新增：`failed_page`——my_assignment 中 status=failed、fail_reason="unreadable"、原图已存的页面；`failed_page_with_results`——同上但带 2 条旧结果；`second_page_bytes`——同作业另一页的原图字节；`other_teacher_failed_page`；`failed_page_factory(reason)`；测试小工具 `count_results(db, page_id)`。）
- [ ] **Step 2:** 跑 `tests/test_upload.py`，FAIL。
- [ ] **Step 3:** 实现。
- [ ] **Step 4:** PASS，并跑全量一次。
- [ ] **Step 5:** 提交 `feat: replace a failed page in place`。

---

### Task 3: 重试批改服务出错的卷子

**Files:**
- Modify: `backend/app/assignments/router.py`
- Test: `backend/tests/test_upload.py`

**Interfaces:**
- Produces: `POST /api/pages/{page_id}:retry` → `PageUploadOut`（`duplicate=false`，HTTP 200）。
- 规则：归属校验 404；仅 `status == failed` 且 `fail_reason in RETRYABLE_FAILURES` 可重试，否则 409 detail `"这张需要重拍"`；在锁下置 `queued`、清 `fail_reason`、`retry_count += 1`，提交后按 `grade_job_id(page_id, retry_count)` 入队（失败返回 503，沿用 `_enqueue_or_503`）；不占额度、不改图片。与"重复上传触发重试"共用一个内部函数，不重复逻辑。

- [ ] **Step 1: 写失败的测试**

```python
async def test_retry_model_unavailable(auth_client, failed_page_factory, enqueued):
    p = await failed_page_factory("model_unavailable")
    r = await auth_client.post(f"/api/pages/{p.id}:retry")
    assert r.status_code == 200 and r.json()["status"] == "queued" and enqueued[-1] == p.id

async def test_retry_unreadable_is_409(auth_client, failed_page_factory):
    p = await failed_page_factory("unreadable")
    r = await auth_client.post(f"/api/pages/{p.id}:retry")
    assert r.status_code == 409 and r.json()["detail"] == "这张需要重拍"
```

- [ ] **Step 2:** FAIL。 **Step 3:** 实现（抽出 `_requeue_failed(db, page_id, enqueue) -> PageUploadOut` 给重复上传与本接口共用）。 **Step 4:** PASS + 全量。 **Step 5:** 提交 `feat: retry a page that failed for a transient reason`。

---

### Task 4: 无答案卷时的复核规则（方案 B）

**Files:**
- Modify: `backend/app/grading/rules.py`、`backend/app/grading/pipeline.py`、`backend/app/review/router.py`、`backend/app/models.py`
- Create: `backend/migrations/versions/0007_answer_mismatch.py`、`backend/app/grading/consensus.py`
- Test: `backend/tests/test_grading_rules.py`、`backend/tests/test_consensus.py`、`backend/tests/test_pipeline.py`、`backend/tests/test_review.py`

**Interfaces:**
- 新列 `QuestionResult.answer_mismatch: bool`（NOT NULL，默认 False，迁移 0007，在临时库验证 upgrade/downgrade -1）。
- `rules.needs_review(confidence: float, student_status: str, threshold: float, answer_mismatch: bool = False) -> bool`：`confidence < threshold or student_status in UNRESOLVED_STUDENT_STATUSES or answer_mismatch`（**去掉** `answer_verified` 参数；所有调用方同步修改）。
- `consensus.normalize_answer(s: str | None) -> str`：去掉全部空白、全角转半角、转小写。
- `consensus.majority(answers: list[str]) -> str | None`：出现次数严格最多的那个；打平或空列表返回 None。
- `async consensus.refresh_answer_consensus(db, assignment_id: int, question_nos: set[str], settings) -> set[int]`：在调用方已持有作业锁的前提下，对给定题号，取本作业所有 `status == done` 页面上 `answer_verified == False` 且 `reviewed == False` 的结果，按 `normalize_answer(correct_answer)` 求多数；`answer_mismatch = (多数为 None) or (该行归一化答案 != 多数)`，但只有一行时 `answer_mismatch = False`；据此重算这些行的 `needs_review`（学生状态：页面 `student_id` 为空视为 `"none"`，否则视为 `"exact"`——模糊匹配的行原本已在复核中且未被 reviewed，保持 True）；返回受影响的 submission id 集合。
- pipeline `_write_phase`：写完本页行后、`attach_following_pages` 之前调用 `refresh_answer_consensus`（题号 = 本页无答案卷的题号），并把返回的 submission 加入重算集合。
- review `_reason`：顺序改为 无学生 →`student_uncertain`；`confidence < threshold` →`low_confidence`；`answer_mismatch` →`answer_mismatch`；否则 `student_uncertain`。不再返回 `unverified_answer`。
- `GET /api/assignments/{id}` 响应增加 `has_answer_key: bool`（`answer_key_status == confirmed`），供前端显示"本次没有答案卷，答案由 AI 判断"。

- [ ] **Step 1: 写失败的测试**

```python
def test_unverified_alone_not_reviewed():
    assert needs_review(0.95, "exact", 0.8) is False
    assert needs_review(0.95, "exact", 0.8, answer_mismatch=True) is True

def test_majority():
    assert majority(["62.8", "62.8", "157"]) == "62.8"
    assert majority(["a", "b"]) is None and majority([]) is None

def test_normalize_answer():
    assert normalize_answer(" ６２.８ dm³ ") == normalize_answer("62.8dm³")

async def test_minority_answer_flagged(db, storage, three_pages_same_q):   # AI 答案 62.8/62.8/157
    ...grade all three...
    flagged = {r.correct_answer: r.needs_review for r in results_for_q("3")}
    assert flagged == {"62.8": False, "157": True}

async def test_tie_flags_all(db, storage, two_pages_conflicting):         # 62.8 / 157
    assert all(r.needs_review and r.answer_mismatch for r in results_for_q("3"))

async def test_single_page_not_flagged(db, storage, uploaded_page, roster_zhangsan):
    # 唯一一张卷子、置信度 0.95、学生精确匹配、无答案卷
    assert all(not r.needs_review and not r.answer_mismatch for r in await results_of(db, uploaded_page))

async def test_answer_key_present_ignores_consensus(db, storage, confirmed_key_q1_q2, two_pages_conflicting):
    # 有答案卷时 answer_verified=True，不参与多数比较
    assert all(not r.answer_mismatch for r in results_for_q("1"))

async def test_review_reason_answer_mismatch(auth_client, mismatch_result):
    items = (await auth_client.get(f"/api/assignments/{mismatch_result.assignment_id}/review")).json()["questions"]
    assert items[0]["reason"] == "answer_mismatch"

async def test_assignment_has_answer_key_flag(auth_client, my_assignment):
    assert (await auth_client.get(f"/api/assignments/{my_assignment.id}")).json()["has_answer_key"] is False
```

（conftest/测试内新增：`three_pages_same_q`、`two_pages_conflicting`——同作业、同名单中不同学生的已上传页面，配好 FakeModel 使第 "3" 题的 `correct_answer` 分别为 62.8/62.8/157 或 62.8/157；`mismatch_result`；小工具 `results_of(db, page)`、`results_for_q(no)`。）
- [ ] **Step 2:** FAIL。
- [ ] **Step 3:** 实现（迁移、规则、consensus 模块、pipeline 与 review 调用点、`has_answer_key`）。更新现有测试中依赖"未校验即复核"的断言。
- [ ] **Step 4:** 全量 PASS。
- [ ] **Step 5:** 提交 `feat: no-answer-key review by class majority (option B)`。

---

## 二、小程序（任务 5–13）

### 文件结构

```
miniprogram/
  package.json  tsconfig.json  vitest.config.ts  project.config.json
  config/index.ts  .env.development  .env.production
  src/
    app.ts  app.config.ts  app.scss
    lib/
      api.ts          request(): 基地址、token、401 静默重登一次
      auth.ts         login()
      messages.ts     失败原因/HTTP 错误 → 中文
      subjects.ts     学科列表与中文名
      roster.ts       名单预览（人数、行解析）
      resize.ts       targetSize() 纯函数 + compressForUpload()
      uploadQueue.ts  顺序上传队列
      progress.ts     轮询停止判断、进度文案
      types.ts        与后端一致的数据类型
    pages/
      index/          P1 班级列表
      class/          P2 班级详情 + 新建作业弹层
      class-edit/     P3 新建班级 / 名单
      assignment/     P4 作业主页
      camera/         P5 拍照（学生卷 / 答案卷）
      answer-key/     P6 答案卷确认
      review/         P7 复核
      results/        P8 成绩列表 + 学生明细
    components/       StatusPill、EmptyGuide、BottomButton 等少量组件
  tests/              Vitest 测试（只测 src/lib）
```

### Task 5: 工程骨架与登录

**Files:** Create `miniprogram/`（Taro 4 React TS 模板）、`src/lib/api.ts`、`src/lib/auth.ts`、`src/lib/types.ts`、`src/app.ts`、`vitest.config.ts`、`tests/api.test.ts`；Modify 根 `.gitignore`（忽略 `miniprogram/node_modules/`、`miniprogram/dist/`）。

**Interfaces:**
- `api.request<T>(method: 'GET'|'POST'|'PUT'|'PATCH'|'DELETE', path: string, body?: unknown): Promise<T>`；非 2xx 抛 `ApiError { status: number; detail: string }`。
- `api.upload<T>(path: string, filePath: string): Promise<T>`（`Taro.uploadFile`，字段名 `file`）。
- `auth.login(): Promise<void>`：`Taro.login` → `POST /api/auth/wx-login {code}` → `Taro.setStorageSync('token', ...)`。
- 401 时调用一次 `login()` 后重试原请求；仍 401 抛 `ApiError(401)`。
- `types.ts`：`ClassOut, StudentOut, AssignmentOut(含 has_answer_key), PageOut, ProgressOut, SubmissionOut, ReviewOut, AnswerKeyItem`，字段名与后端 JSON 一致。

- [ ] **Step 1:** 用 Taro CLI 初始化（React、TypeScript、Sass、webpack5、默认模板），配置 `TARO_APP_API_BASE`（开发值 `http://127.0.0.1:8000`）。加 Vitest，`tests/` 中 mock `@tarojs/taro`。
- [ ] **Step 2: 写失败的测试** `tests/api.test.ts`：`addsBearerToken`、`relogsInOnceOn401`（第一次 401、重登后 200 → 返回数据，login 调用 1 次）、`throwsApiErrorOnSecond401`、`mapsNon2xxToApiError`（status 与 detail）。
- [ ] **Step 3:** `cd miniprogram; npx vitest run`，FAIL。
- [ ] **Step 4:** 实现；`app.ts` 启动时若无 token 则 `login()`。
- [ ] **Step 5:** PASS；`npm run build:weapp` 成功；微信开发者工具导入 `miniprogram/` 能打开空首页。
- [ ] **Step 6:** 提交 `feat(miniprogram): scaffold Taro app with API client and login`。

### Task 6: 纯逻辑模块

**Files:** Create `src/lib/messages.ts`、`subjects.ts`、`roster.ts`、`resize.ts`、`progress.ts` 及对应 `tests/*.test.ts`。

**Interfaces:**
- `failReasonText(reason: string | null): string`（Global Constraints 的映射；未知原因 →"这张没批出来，请重拍"）；`failReasonAction(reason): 'retake' | 'retry' | null`（`model_unavailable`/`internal_error` → retry，其余 failed → retake）。
- `errorText(e: unknown): string`：`ApiError` 429/503/409 用后端 detail（已是中文）；网络错误 →"网络不太好，请稍后再试"；其他 →"出了点问题，请稍后再试"。
- `subjectsForGrade(grade: number): {value: string; label: string}[]`（按 Global Constraints 的两组）。
- `previewRoster(text: string): {count: number; entries: {name: string; studentNo: string | null}[]}`：与后端 `parse_roster` 同规则（一行一人；`[A-Za-z]?\d+` 为学号；恰好一个学号 token 时其余为姓名，否则整行为姓名；空行跳过；完全相同的行去重）。
- `targetSize(w: number, h: number, maxLong = 2000): {width: number; height: number}`（不放大，四舍五入取整）。`compressForUpload(path): Promise<string>` 用离屏 canvas 绘制后 `canvasToTempFilePath`（JPEG, quality 0.85），只在页面里用，不做单测。
- `isFinished(progress: ProgressOut): boolean`（`total > 0 && queued + processing === 0`）；`progressText(p, submissions, rosterSize): {pages: string; students: string}`（"已批 x/y 张"、"已出成绩 m/n 人"）。

- [ ] **Step 1: 写失败的测试**：每个函数至少覆盖设计文档中的例子与边界（`targetSize(4000,3000)` → 2000×1500；`targetSize(800,600)` 不变；`subjectsForGrade(6)` 不含"物理"、`subjectsForGrade(7)` 含"物理"；`previewRoster("张三\n 2024002 李四 \n王五,2024003\n\n张三").count === 3`；`isFinished({total:0,...})` 为 false）。
- [ ] **Step 2:** FAIL。 **Step 3:** 实现。 **Step 4:** PASS。 **Step 5:** 提交 `feat(miniprogram): copy, subjects, roster preview, resize and progress helpers`。

### Task 7: 顺序上传队列

**Files:** Create `src/lib/uploadQueue.ts`、`tests/uploadQueue.test.ts`。

**Interfaces:**
- `type Uploader = (filePath: string) => Promise<{page_id: number; seq: number; duplicate: boolean}>`
- `class UploadQueue { constructor(uploader: Uploader, opts?: {retries?: number /*默认 2*/}); add(filePath: string): string /*返回本地 id*/; items(): QueueItem[]; pendingCount(): number; retry(localId: string): void; onChange(cb: () => void): () => void; stopped: null | 'quota' }`
- `QueueItem { localId; filePath; state: 'waiting'|'uploading'|'done'|'failed'|'held'; pageId?: number; message?: string }`
- 行为：同一时刻只上传一张，严格按 `add` 顺序；失败重试至多 2 次（网络错误与 5xx，503 除外）；`duplicate: true` 记为 done；429 → 当前与后续全部 `held`，`stopped = 'quota'`，message"本月批改额度已用完"，不再上传；503 → 记为 done 并带 message"已收到，稍后会自动开始批改"（后端已保存页面），并在 30 秒后对同一文件静默重传一次以重新排队；401 由 `api` 层处理，对队列透明。

- [ ] **Step 1: 写失败的测试**：`uploadsInOrderOneAtATime`、`retriesTwiceThenFails`、`manualRetryRequeuesAtSamePosition`（重试的张在仍等待的张之前上传）、`duplicateCountsAsDone`、`quotaHoldsRemaining`、`serviceUnavailableMarksDoneAndResendsLater`（假计时器）、`pendingCountForLeaveGuard`、`continuesAfterReloginMidQueue`（uploader 第一次抛 401 后 api 层重登成功——用 mock api 模拟，队列顺序不变）。
- [ ] **Step 2:** FAIL。 **Step 3:** 实现。 **Step 4:** PASS。 **Step 5:** 提交 `feat(miniprogram): sequential upload queue`。

### Task 8: 班级列表、新建班级与名单（P1、P3）

**Files:** Create `src/pages/index/*`、`src/pages/class-edit/*`、`src/components/EmptyGuide.tsx`、`StatusPill.tsx`。

**Interfaces:**
- P1：`GET /api/classes`；每个班再取 `GET /api/classes/{id}/assignments`（第一项）和其 `/progress`，卡片显示"N 人"、最近作业标题与状态（待复核数 > 0 → 黄色"N 题待复核"；未结束 →"批改中 x/y"；否则绿色"全部完成"）。无班级时只显示"先建一个班"按钮。
- P3：新建模式（班名默认"X年级X班"可改、年级选择器 1–9、名单粘贴框、实时显示 `previewRoster` 人数）→ `POST /api/classes` 再 `POST students:import`；编辑模式（`?classId=`）显示名单列表，每行可改名/改学号（Task 1 接口）、删除（409 时弹出后端 detail），底部"追加名单"。

- [ ] **Step 1:** 实现页面。
- [ ] **Step 2:** 在开发者工具中对接本地后端验证：首次进入显示引导；建班后回到 P1 卡片出现；粘贴 3 行显示"3 人"；改名生效；删除有成绩学生出现中文提示。
- [ ] **Step 3:** 提交 `feat(miniprogram): class list, class creation and roster editing`。

### Task 9: 班级详情与新建作业（P2）

**Files:** Create `src/pages/class/*`、`src/components/NewAssignmentSheet.tsx`。

**Interfaces:** `GET /api/classes/{id}/assignments`（新的在前），每项显示进度摘要；"新建作业"底部弹层：学科选择器（`subjectsForGrade(class.grade)`，默认 `/api/me` 的 `last_subject`，若不在列表中则默认第一个）、标题默认 `MM-DD 作业`；创建后 `redirectTo` P4。右上角"名单"进 P3 编辑模式。

- [ ] **Step 1:** 实现。 **Step 2:** 手动验证：新建作业 2 次点击可完成（打开弹层 → 创建），学科默认上次所选。 **Step 3:** 提交 `feat(miniprogram): class detail and new assignment`。

### Task 10: 作业主页（P4）

**Files:** Create `src/pages/assignment/*`。

**Interfaces:**
- 数据：`GET /api/assignments/{id}`、`/progress`、`/pages`、`/submissions`、`GET /api/classes/{class_id}/students`（名单人数）。轮询 3 秒，`isFinished` 后停止，`useDidHide`/卸载时停止。
- 顶部：学科中文名、标题；答案卷状态（无 → 按钮"拍答案卷"突出显示为第一个按钮；`pending` →"确认答案卷"；已确认 → ✓）；`has_answer_key == false` 时显示"本次没有答案卷，答案由 AI 判断"。
- 中部：`progressText` 两行；名单为空时显示提示"这个班还没有名单，先导入名单才能认出学生"并带"去导入"按钮（`rosterEmptyHint`）。
- 页面列表：每张显示序号、学生名或"未识别"、状态；failed 显示 `failReasonText` 与按钮（`retake` → 进入 P5 替换模式，调用 `POST /api/pages/{id}:replace`；`retry` → `POST /api/pages/{id}:retry`）。
- 底部：主按钮"开始拍卷"（进入 P5）；有待复核时"去复核 N 题"；有成绩时"看成绩"。

- [ ] **Step 1:** 先在 `src/lib/progress.ts` 加 `assignmentHints(a: AssignmentOut, rosterSize: number): string[]` 并写测试 `rosterEmptyHint`、`noAnswerKeyHint`（返回对应中文提示）。 **Step 2:** FAIL→实现→PASS。
- [ ] **Step 3:** 实现页面；手动验证轮询停止、重拍与重试按钮生效。
- [ ] **Step 4:** 提交 `feat(miniprogram): assignment page with progress, retake and retry`。

### Task 11: 拍照页与答案卷（P5、P6）

**Files:** Create `src/pages/camera/*`、`src/pages/answer-key/*`。

**Interfaces:**
- P5 参数 `mode=pages|answerKey|replace`、`assignmentId`、`pageId?`。
  - `pages`：`<Camera>` 全屏 + 快门；每次拍照 → `compressForUpload` → `queue.add`；"从相册选"（`chooseMedia`，最多 20 张，按选择顺序加入）；底部缩略图条显示每张状态，failed 可点重传；"完成"返回 P4。离开时若 `queue.pendingCount() > 0` 弹窗"还有 N 张没传完，离开会中断"（继续上传 / 放弃剩余）。
  - `answerKey`：拍 1 张（或相册选 1 张）→ 显示"正在识别答案…" → `POST /api/assignments/{id}/answer-key` → 进入 P6。
  - `replace`：拍 1 张 → `POST /api/pages/{pageId}:replace` → 返回 P4。
- P6：列表编辑题号、答案、分值（可空）；可删行、加行；"确认答案" → `PUT`；`regrade_suggested` 为 true 时提示"已批的卷子不会自动重批"。

- [ ] **Step 1:** 实现。
- [ ] **Step 2:** 手动验证：连拍 10 张后 P4 页面序号 1–10 与拍摄顺序一致；断网拍 1 张后恢复网络可重传；额度用完时出现"本月批改额度已用完"且后续不再上传；答案卷识别后可修改并确认。
- [ ] **Step 3:** 提交 `feat(miniprogram): camera with sequential upload, answer key capture and confirmation`。

### Task 12: 复核与成绩（P7、P8）

**Files:** Create `src/pages/review/*`、`src/pages/results/*`、`src/lib/review.ts`、`tests/review.test.ts`。

**Interfaces:**
- `review.buildQueue(r: ReviewOut): ReviewItem[]`：未识别学生的页面在前（`kind: 'page'`），然后题目（`kind: 'question'`），保持后端顺序。
- `review.reasonText(reason): string`：`student_uncertain`"学生不确定"、`low_confidence`"AI 不太确定"、`answer_mismatch`"和全班多数答案不一致"。
- `review.refreshesExpiredImageUrls`：图片 `onError` 时重新拉取 `/review` 并替换当前项 URL（每项最多一次）。
- P7：一次一项。页面项：显示整页图片与"识别到的名字"，从名单选择学生 → `PATCH /api/pages/{id}`。题目项：错题截图、学生名、题目、学生答案、正确答案、AI 判定与分数、原因；"判对"/"判错"/"改分"（数字键盘，0–满分）→ `PATCH /api/question-results/{id}`；"换学生" → 名单选择 → `PATCH /api/pages/{page_id}`。成功后自动下一项；全部完成显示"复核完成"返回 P4。
- P8：`GET /api/assignments/{id}/submissions` 列表（姓名、总分、待复核数）；点进学生 → `GET /api/submissions/{id}` 显示每题对错、得分、错题截图。`has_answer_key == false` 时顶部显示"本次没有答案卷，答案由 AI 判断"。

- [ ] **Step 1: 写失败的测试** `buildQueuePutsPagesFirst`、`reasonTextCoversAll`、`refreshesExpiredImageUrls`（模拟 onError → 重新请求一次，第二次失败不再请求）。
- [ ] **Step 2:** FAIL→实现→PASS。
- [ ] **Step 3:** 实现页面；手动验证判对/判错/改分后 P8 分数变化；换学生后续页一起换（后端已实现）。
- [ ] **Step 4:** 提交 `feat(miniprogram): review queue and results`。

### Task 13: 验收与开发说明

**Files:** Create `miniprogram/README.md`（本地开发步骤：启动后端、Worker、开发者工具"不校验合法域名"、环境变量、测试号 AppID）。

- [ ] **Step 1:** 本地起 MySQL、Redis（需要密码，见 R7；无密码时用后端 FakeModel 或手动把页面状态改为 done 验证前端）、API、Worker，按设计文档第 8 节验收清单逐项走一遍，记录结果到 `docs/benchmark/m3-acceptance.md`（通过/未通过/原因）。
- [ ] **Step 2:** `npx vitest run` 与后端 `pytest` 全部通过。
- [ ] **Step 3:** 提交 `docs: M3 dev setup and acceptance results`。

---

## M3 完成标准

- [ ] 后端 pytest、小程序 Vitest 全部通过；`npm run build:weapp` 成功。
- [ ] 设计文档第 8 节验收清单全部通过（或未通过项写明原因并经产品负责人认可）。
- [ ] 首页到"开始拍卷"不超过 3 次点击（已有班级时）。
