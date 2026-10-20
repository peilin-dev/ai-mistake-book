# AI 智能错题本 开发计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先交付后端核心（M1）：老师登录、建班导名单、建作业、上传卷子，Worker 自动批改入库并产生待复核队列，可通过 API 完整走通。

**Architecture:** FastAPI 单体，按业务模块分包；批改走 arq + Redis 异步 Worker；模型经适配层调用（通义千问 / 豆包 / 测试用 Fake）；图片经存储抽象（开发用本地目录，上线用 OSS）。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2（async）+ aiomysql、Alembic、pydantic v2、arq、Redis、httpx、Pillow、PyJWT、pytest + pytest-asyncio。

**Spec:** `docs/specs/2026-10-20-ai-mistake-book-design.md`

---

## 一、总路线图

整个产品拆成 7 个阶段。每个阶段开工前单独写一份详细计划；本文档只把 **M1** 写到任务级。

| 阶段 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| **M1 后端核心** | 登录、班级名单、作业、上传、模型适配、批改流水线、复核、原图清理、模型评测脚本 | 用 API 能走通「拍卷 → 批改 → 复核」 | — |
| M2 知识点数据 | 按课标 AI 生成全科知识点草稿，分学科人工审核，导入 | `data/knowledge/*.yaml` 全科 | 可与 M1 并行 |
| M3 小程序 | 登录、建班、建作业、连拍上传、进度、复核、查看结果 | 体验版可用 | M1 |
| M4 学情与报告 | 班级学情、个人错题本、AI 总结、PDF 导出、署名 | 老师能看能导出 | M1 |
| M5 举一反三 | 变式题生成、双模型验算、老师勾选、练习卷导出 | 练习卷 PDF | M4 |
| M6 网页后台 | 扫码登录、学情大屏、批量复核、导出 | Web 后台 | M1、M4 |
| M7 试用上线 | 部署（云服务器 + OSS + Redis）、体验版发布、邀请老师、收集复核数据 | 首批老师试用 | M3–M6 |

**模型选型时机**：M1 的任务 14 产出评测脚本，拿到 ≥100 张真实卷子后立刻跑，结果决定 `grading` 主力模型，并在 M3 开始前定下来。

---

## 二、M1 详细计划

### Global Constraints

- Python 3.11；所有 I/O 用 async。
- 学科枚举：`chinese, math, english, physics, chemistry, biology, history, geography, politics, science, other`。
- 年级 `grade`：整数 1–12（1–6 小学，7–9 初中，10–12 高中）。
- 复核置信度阈值默认 `0.8`（配置项 `REVIEW_CONFIDENCE_THRESHOLD`）。
- 姓名相似度阈值 `0.8`（配置项 `NAME_MATCH_THRESHOLD`）。
- 每月免费限额默认 `300` 页/老师（配置项 `MONTHLY_PAGE_QUOTA`）。
- 原图保留 `30` 天（配置项 `ORIGINAL_RETENTION_DAYS`）。
- 上传图片：只接受 JPEG/PNG/HEIC，单张 ≤ 10 MB；送模型前长边缩放到 ≤ 2048px。
- JWT 有效期 7 天；`teachers` 主键是自有 id，绝不把 openid 当主键。
- 老师只能访问自己的数据：他人资源一律返回 **404**（不暴露存在性）。
- 测试数据库：环境变量 `TEST_DATABASE_URL`（本机 MySQL 的 `cuotiben_test` 库）。

### Review Focus

1. **照片模糊、倒置或不是试卷**：模型识别不到题目时，页面应为 `failed` 且 `fail_reason="unreadable"`，而不是生成一份空结果算 0 分。→ 任务 10 测试 `test_unreadable_page_fails`。
2. **模型返回非法 JSON 或缺字段**：重试 1 次，仍失败则 `failed`、`fail_reason="model_output_invalid"`，Worker 不崩溃。→ 任务 10 测试 `test_invalid_output_retries_then_fails`。
3. **同一张照片重复上传**（老师手抖连点）：返回已有页面，不重复批改、不扣额度。→ 任务 6 测试 `test_duplicate_upload_returns_existing_page`。
4. **班上同名学生**：不能自动匹配给其中任何一人，要进待复核。→ 任务 9 测试 `test_duplicate_names_in_roster_are_ambiguous`。
5. **连拍中途额度用完**：已上传的页正常批改，超出的页返回 429 和明确提示，不会出现「上传成功却永远不批」。→ 任务 6 测试 `test_upload_over_quota_returns_429`。

### 文件结构

```
backend/
  pyproject.toml
  alembic.ini
  migrations/                     # Alembic
  app/
    main.py                       # create_app()，挂载各模块 router
    config.py                     # Settings（pydantic-settings）
    db.py                         # engine、async_session、Base
    deps.py                       # get_db、current_teacher
    models.py                     # 全部 ORM 模型（M1 规模单文件即可）
    auth/        router.py  wechat.py  tokens.py
    classes/     router.py  roster.py
    assignments/ router.py
    storage/     base.py  local.py
    quota/       service.py
    ai/          base.py  openai_compat.py  fake.py  registry.py  usage.py
    knowledge/   loader.py  service.py
    grading/     schema.py  matching.py  rules.py  crop.py  prompts.py  pipeline.py  answer_key.py
    review/      router.py
    jobs/        worker.py  cleanup.py
  data/knowledge/math_primary_sample.yaml
  scripts/benchmark_models.py
  tests/
    conftest.py
    test_health.py  test_auth.py  test_classes.py  test_assignments.py  test_upload.py
    test_ai.py  test_knowledge.py  test_grading_rules.py  test_matching.py
    test_pipeline.py  test_answer_key.py  test_review.py  test_cleanup.py
```

---

### Task 1: 工程骨架与测试基座

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/app/deps.py`, `backend/tests/conftest.py`, `backend/tests/test_health.py`, `.gitignore`

**Interfaces:**
- Produces: `create_app() -> FastAPI`；`Settings`（含 Global Constraints 中所有配置项及 `DATABASE_URL`、`REDIS_URL`、`JWT_SECRET`、`WX_APPID`、`WX_SECRET`、`STORAGE_DIR`、`DASHSCOPE_API_KEY`、`ARK_API_KEY`）；`get_settings()`；`Base`；`get_db() -> AsyncIterator[AsyncSession]`。
- conftest 提供 fixture：`db`（每个测试前 `create_all`、测试后清空表）、`client`（`httpx.AsyncClient` 挂 `create_app()`，覆盖 `get_db`）、`settings`（测试用配置，`STORAGE_DIR` 指向 `tmp_path`）。

- [ ] **Step 1:** 在 `F:\项目` 执行 `git init`，`.gitignore` 忽略 `.venv/ __pycache__/ .env storage/`。
- [ ] **Step 2: 写失败的测试** `tests/test_health.py`

```python
async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
```

- [ ] **Step 3:** 运行 `cd backend && pytest tests/test_health.py -v`，预期 FAIL（`create_app` 不存在）。
- [ ] **Step 4:** 实现 `create_app()`、`Settings`、`db.py`、`deps.get_db`、conftest；`pyproject.toml` 设 `asyncio_mode = "auto"`。
- [ ] **Step 5:** 再运行，预期 PASS。
- [ ] **Step 6:** 提交 `git commit -m "chore: backend skeleton with health check"`。

---

### Task 2: 数据模型与迁移

**Files:**
- Create: `backend/app/models.py`, `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/0001_initial.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: ORM 类 `School, Teacher, Class_, Student, Assignment, AnswerItem, Page, Submission, QuestionResult, KnowledgePoint, UsageRecord`，字段与设计文档第 6 节一致（`practice_items`、`exports` 留到 M4/M5）。枚举：`Subject`（str Enum，取值见 Global Constraints）、`PageStatus = queued|processing|done|failed`、`AnswerKeyStatus = none|pending|confirmed`。
- `QuestionResult` 额外包含 `model_is_correct: bool | None`、`model_score: float | None`（老师首次修改时保存模型原值，供任务 12 和准确率统计使用）。
- 唯一约束：`Teacher.unionid`、`Teacher.mp_openid`、`(Page.assignment_id, Page.image_sha256)`、`(Submission.assignment_id, Submission.student_id)`。

- [ ] **Step 1: 写失败的测试**

```python
async def test_page_sha_unique_per_assignment(db, make_assignment):
    a = await make_assignment()
    db.add(Page(assignment_id=a.id, seq=1, image_key="k1", image_sha256="x"))
    await db.commit()
    db.add(Page(assignment_id=a.id, seq=2, image_key="k2", image_sha256="x"))
    with pytest.raises(IntegrityError):
        await db.commit()
```

（`make_assignment` 工厂 fixture 加入 conftest：建老师 → 班级 → 作业。）
- [ ] **Step 2:** 运行 `pytest tests/test_models.py -v`，预期 FAIL。
- [ ] **Step 3:** 实现 `models.py`；`alembic revision --autogenerate -m initial` 生成 `0001_initial.py` 并人工检查。
- [ ] **Step 4:** 运行测试 PASS；对空库执行 `alembic upgrade head` 无报错。
- [ ] **Step 5:** 提交 `feat: data models and initial migration`。

---

### Task 3: 微信登录与鉴权

**Files:**
- Create: `backend/app/auth/wechat.py`, `backend/app/auth/tokens.py`, `backend/app/auth/router.py`
- Modify: `backend/app/deps.py`（加 `current_teacher`）
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Produces:
  - `class WeChatClient(Protocol): async def code2session(self, code: str) -> WxSession`；`WxSession(openid: str, unionid: str | None)`；`WeChatAuthError`。真实实现 `HttpWeChatClient`；依赖 `get_wechat_client()` 可在测试中覆盖。
  - `issue_token(teacher_id: int) -> str`、`decode_token(token: str) -> int`。
  - `POST /api/auth/wx-login {code}` → `{token, teacher: {id, display_name}}`。
  - `GET /api/me` → `{id, display_name, last_subject}`；`PATCH /api/me {display_name}`。
  - `current_teacher(...) -> Teacher`（Bearer token，无效 401）。

- [ ] **Step 1: 写失败的测试**

```python
async def test_first_login_creates_teacher_without_profile(client, fake_wx):
    fake_wx.sessions["c1"] = WxSession(openid="o1", unionid="u1")
    r = await client.post("/api/auth/wx-login", json={"code": "c1"})
    assert r.status_code == 200
    assert r.json()["teacher"]["display_name"] is None

async def test_same_unionid_returns_same_teacher(client, fake_wx):
    fake_wx.sessions["c1"] = WxSession(openid="o1", unionid="u1")
    fake_wx.sessions["c2"] = WxSession(openid="o2-new-appid", unionid="u1")
    a = (await client.post("/api/auth/wx-login", json={"code": "c1"})).json()
    b = (await client.post("/api/auth/wx-login", json={"code": "c2"})).json()
    assert a["teacher"]["id"] == b["teacher"]["id"]

async def test_invalid_code_401(client, fake_wx):
    r = await client.post("/api/auth/wx-login", json={"code": "bad"})
    assert r.status_code == 401

async def test_me_requires_token(client):
    assert (await client.get("/api/me")).status_code == 401
```

- [ ] **Step 2:** 运行 `pytest tests/test_auth.py -v`，预期 FAIL。
- [ ] **Step 3:** 实现。查找顺序：先按 `unionid`，没有再按 `mp_openid`；命中后补写缺失的那个字段。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: wechat login and jwt auth`。

---

### Task 4: 班级与名单

**Files:**
- Create: `backend/app/classes/router.py`, `backend/app/classes/roster.py`
- Test: `backend/tests/test_classes.py`

**Interfaces:**
- Produces:
  - `parse_roster(text: str) -> list[RosterEntry]`；`RosterEntry(name: str, student_no: str | None)`。每行一人，支持「姓名」「学号 姓名」「姓名,学号」，去掉空行和首尾空白，同行完全重复的去重。
  - `POST /api/classes {name, grade}` → class；`GET /api/classes`；`POST /api/classes/{id}/students:import {text}` → `{created: int, students: [...]}`；`GET /api/classes/{id}/students`；`DELETE /api/classes/{id}`（级联删除其下全部数据）。

- [ ] **Step 1: 写失败的测试**

```python
def test_parse_roster_formats():
    text = "张三\n 2024002 李四 \n王五,2024003\n\n张三"
    assert parse_roster(text) == [
        RosterEntry("张三", None), RosterEntry("李四", "2024002"), RosterEntry("王五", "2024003")]

async def test_grade_must_be_1_to_12(auth_client):
    r = await auth_client.post("/api/classes", json={"name": "五(2)班", "grade": 13})
    assert r.status_code == 422

async def test_other_teachers_class_is_404(auth_client, other_teacher_class):
    r = await auth_client.get(f"/api/classes/{other_teacher_class.id}/students")
    assert r.status_code == 404
```

（加入 conftest：`auth_client` 已登录老师的 client；`my_class` 该老师的一个五年级班；`other_teacher_class` 属于另一位老师的班级。）
- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: classes and roster import`。

---

### Task 5: 作业与学科记忆

**Files:**
- Create: `backend/app/assignments/router.py`
- Test: `backend/tests/test_assignments.py`

**Interfaces:**
- Produces: `POST /api/assignments {class_id, subject, title}` → assignment（`answer_key_status="none"`），并把 `teacher.last_subject` 更新为该学科；`GET /api/classes/{id}/assignments`；`GET /api/assignments/{id}/progress` → `{total, queued, processing, done, failed, needs_review}`。

- [ ] **Step 1: 写失败的测试**

```python
async def test_create_assignment_remembers_subject(auth_client, my_class):
    await auth_client.post("/api/assignments",
        json={"class_id": my_class.id, "subject": "math", "title": "第三单元测验"})
    me = (await auth_client.get("/api/me")).json()
    assert me["last_subject"] == "math"

async def test_unknown_subject_422(auth_client, my_class):
    r = await auth_client.post("/api/assignments",
        json={"class_id": my_class.id, "subject": "art_x", "title": "t"})
    assert r.status_code == 422
```

- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现（progress 先返回全 0，任务 6/10 填充后自然正确）。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: assignments with last-subject memory`。

---

### Task 6: 存储、页面上传、去重与限额

**Files:**
- Create: `backend/app/storage/base.py`, `backend/app/storage/local.py`, `backend/app/quota/service.py`
- Modify: `backend/app/assignments/router.py`
- Test: `backend/tests/test_upload.py`

**Interfaces:**
- Produces:
  - `class Storage(Protocol)`: `async put(key: str, data: bytes, content_type: str) -> None`、`async get(key: str) -> bytes`、`async delete(key: str) -> None`、`signed_url(key: str, expires_s: int = 600) -> str`。`LocalStorage(root: Path)`；依赖 `get_storage()`。
  - `async pages_used_this_month(db, teacher_id: int) -> int`、`async check_quota(db, teacher_id: int) -> None`（超限抛 `QuotaExceeded`）。计数口径：本自然月（Asia/Shanghai）新建的 `pages` 数。
  - `POST /api/assignments/{id}/pages`（multipart 字段 `file`）→ `{page_id, seq, status, duplicate: bool}`；新页 `status="queued"` 并调用 `enqueue_grade_page(page_id)`（本任务里是可覆盖的依赖，测试中记录调用；任务 10 接入 arq）。
  - 图片 key 规则：`originals/{teacher_id}/{assignment_id}/{page_id}.{ext}`。

- [ ] **Step 1: 写失败的测试**

```python
async def test_upload_queues_page(auth_client, my_assignment, jpeg_bytes, enqueued):
    r = await auth_client.post(f"/api/assignments/{my_assignment.id}/pages",
                               files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    body = r.json()
    assert r.status_code == 201 and body["status"] == "queued" and body["duplicate"] is False
    assert enqueued == [body["page_id"]]

async def test_duplicate_upload_returns_existing_page(auth_client, my_assignment, jpeg_bytes, enqueued):
    url = f"/api/assignments/{my_assignment.id}/pages"
    a = (await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})).json()
    b = (await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})).json()
    assert b["page_id"] == a["page_id"] and b["duplicate"] is True
    assert len(enqueued) == 1

async def test_upload_over_quota_returns_429(auth_client, my_assignment, settings, make_jpeg):
    settings.MONTHLY_PAGE_QUOTA = 1
    url = f"/api/assignments/{my_assignment.id}/pages"
    await auth_client.post(url, files={"file": ("a.jpg", make_jpeg(1), "image/jpeg")})
    r = await auth_client.post(url, files={"file": ("b.jpg", make_jpeg(2), "image/jpeg")})
    assert r.status_code == 429
    assert r.json()["detail"] == "本月批改额度已用完"

async def test_rejects_non_image_and_oversize(auth_client, my_assignment):
    url = f"/api/assignments/{my_assignment.id}/pages"
    assert (await auth_client.post(url, files={"file": ("a.txt", b"hi", "text/plain")})).status_code == 415
    big = b"\xff\xd8" + b"0" * (10 * 1024 * 1024 + 1)
    assert (await auth_client.post(url, files={"file": ("a.jpg", big, "image/jpeg")})).status_code == 413
```

（加入 conftest：`my_assignment` 属于 `my_class` 的数学作业；`jpeg_bytes` 一张小 JPEG；`make_jpeg(n)` 生成内容各不相同的 JPEG；`enqueued` 覆盖 `enqueue_grade_page` 并记录收到的 page_id 列表。）
- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现。顺序：校验类型/大小 → 算 sha256 → 查重（命中直接返回，不查额度）→ 查额度 → 存图 → 建 Page（`seq` = 该作业现有最大 seq + 1）→ 入队。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: page upload with dedupe and monthly quota`。

---

### Task 7: 模型适配层与用量记录

**Files:**
- Create: `backend/app/ai/base.py`, `backend/app/ai/openai_compat.py`, `backend/app/ai/fake.py`, `backend/app/ai/registry.py`, `backend/app/ai/usage.py`
- Test: `backend/tests/test_ai.py`

**Interfaces:**
- Produces:
  - `ModelResult(data: dict, input_tokens: int, output_tokens: int, model: str, provider: str)`。
  - `class VisionModel(Protocol): provider: str; async def complete_json(self, prompt: str, images: list[bytes]) -> ModelResult`；JSON 解析失败抛 `ModelOutputError`。
  - `OpenAICompatModel(provider, base_url, api_key, model)`：POST `{base_url}/chat/completions`，图片以 base64 data URL 传入，`response_format={"type":"json_object"}`。预置：`qwen`（`https://dashscope.aliyuncs.com/compatible-mode/v1`）、`doubao`（`https://ark.cn-beijing.volces.com/api/v3`）。
  - `FakeModel(responses: list[dict | Exception])`：按顺序返回或抛出，记录收到的 prompt。
  - `get_model(purpose: Literal["grading","answer_key","practice_generate","practice_verify"]) -> VisionModel`，按配置 `MODEL_FOR_<PURPOSE>`（值为 `qwen:<model>` 或 `doubao:<model>`）。
  - `async record_usage(db, teacher_id: int, purpose: str, result: ModelResult) -> None`；单价表 `PRICE_FEN_PER_1K: dict[str, tuple[float, float]]`（输入、输出，单位：分/千 token）放在配置里。

- [ ] **Step 1: 写失败的测试**（用 `httpx.MockTransport` 模拟接口）

```python
async def test_openai_compat_parses_json_and_usage(mock_transport):
    mock_transport.reply({"choices": [{"message": {"content": '{"a": 1}'}}],
                          "usage": {"prompt_tokens": 100, "completion_tokens": 20}, "model": "qwen-vl-max"})
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "qwen-vl-max", transport=mock_transport)
    r = await m.complete_json("p", [b"img"])
    assert r.data == {"a": 1} and r.input_tokens == 100 and r.output_tokens == 20

async def test_non_json_content_raises(mock_transport):
    mock_transport.reply({"choices": [{"message": {"content": "not json"}}], "usage": {}})
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "m", transport=mock_transport)
    with pytest.raises(ModelOutputError):
        await m.complete_json("p", [])

async def test_record_usage_cost(db, teacher, settings):
    settings.PRICE_FEN_PER_1K = {"qwen-vl-max": (0.3, 0.9)}
    await record_usage(db, teacher.id, "grading",
                       ModelResult({}, 2000, 1000, "qwen-vl-max", "qwen"))
    row = (await db.execute(select(UsageRecord))).scalar_one()
    assert row.cost_fen == pytest.approx(0.3 * 2 + 0.9 * 1)
```

- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现；`cost_fen` 用 DECIMAL(10,4) 存。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: vision model adapter with usage tracking`。

---

### Task 8: 知识点导入与候选

**Files:**
- Create: `backend/app/knowledge/loader.py`, `backend/app/knowledge/service.py`, `backend/data/knowledge/math_primary_sample.yaml`
- Test: `backend/tests/test_knowledge.py`

**Interfaces:**
- YAML 格式：

```yaml
subject: math
grade_band: [5, 6]
nodes:
  - code: M-NA-01
    name: 数与运算
    children:
      - {code: M-NA-01-03, name: 分数加减法}
```

- Produces：`async import_yaml(db, path: Path) -> int`（按 `code` 幂等 upsert，返回节点数）；`async candidates(db, subject: str, grade: int) -> list[KnowledgePoint]`（返回 `grade_band` 包含该年级的**叶子节点**）。
- 样例数据：小学数学五、六年级，约 30 个叶子知识点，供 M1 联调；全科数据由 M2 产出。

- [ ] **Step 1: 写失败的测试**

```python
async def test_import_is_idempotent(db, sample_yaml):
    assert await import_yaml(db, sample_yaml) == await import_yaml(db, sample_yaml)
    assert (await db.execute(select(func.count(KnowledgePoint.id)))).scalar() == count_nodes(sample_yaml)

async def test_candidates_are_leaves_in_grade(db, sample_yaml):
    await import_yaml(db, sample_yaml)
    names = {k.name for k in await candidates(db, "math", 5)}
    assert "分数加减法" in names and "数与运算" not in names
    assert await candidates(db, "math", 1) == []
```

- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现；写样例 YAML。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: knowledge tree import and candidates`。

---

### Task 9: 批改输出校验、学生匹配、复核规则（纯函数）

**Files:**
- Create: `backend/app/grading/schema.py`, `backend/app/grading/matching.py`, `backend/app/grading/rules.py`
- Test: `backend/tests/test_grading_rules.py`, `backend/tests/test_matching.py`

**Interfaces:**
- Produces:
  - `schema.py`：pydantic `GradedQuestion`、`GradedPage`，字段与设计文档 7.1 一致；`confidence` 限 0–1，`bbox` 为 4 个 0–1 浮点数且 x1<x2、y1<y2，`score ≤ max_score`；`GradedPage.questions` 可为空列表（是否 unreadable 由流水线判断）。
  - `matching.py`：`MatchResult(student_id: int | None, status: Literal["exact","fuzzy","ambiguous","none","continued"])`；`match_student(name: str | None, roster: list[tuple[int, str]], prev_page_student_id: int | None, threshold: float) -> MatchResult`。相似度用 `difflib.SequenceMatcher(None, a, b).ratio()`。
  - `rules.py`：`needs_review(confidence: float, answer_verified: bool, student_status: str, threshold: float) -> bool`，当 `confidence < threshold`、`not answer_verified`、或 `student_status in {"fuzzy","ambiguous","none"}` 时为真；`filter_knowledge_point(kp_id: int | None, allowed: set[int]) -> int | None`。

- [ ] **Step 1: 写失败的测试**

```python
ROSTER = [(1, "张三"), (2, "李四"), (3, "王小明"), (4, "李四")]

def test_exact_unique_match():
    assert match_student("张三", ROSTER, None, 0.8) == MatchResult(1, "exact")

def test_duplicate_names_in_roster_are_ambiguous():
    assert match_student("李四", ROSTER, None, 0.8) == MatchResult(None, "ambiguous")

def test_fuzzy_match():
    assert match_student("王小朋", ROSTER, None, 0.6) == MatchResult(3, "fuzzy")

def test_no_name_continues_previous_page():
    assert match_student(None, ROSTER, 3, 0.8) == MatchResult(3, "continued")

def test_no_name_no_previous():
    assert match_student("", ROSTER, None, 0.8) == MatchResult(None, "none")

@pytest.mark.parametrize("conf,verified,status,expected", [
    (0.95, True, "exact", False),
    (0.79, True, "exact", True),
    (0.95, False, "exact", True),
    (0.95, True, "fuzzy", True),
    (0.95, True, "continued", False),
])
def test_needs_review(conf, verified, status, expected):
    assert needs_review(conf, verified, status, 0.8) is expected

def test_bbox_must_be_ordered():
    with pytest.raises(ValidationError):
        GradedQuestion(**{**VALID_Q, "bbox": [0.5, 0.1, 0.4, 0.2]})

def test_unknown_knowledge_point_dropped():
    assert filter_knowledge_point(999, {1, 2}) is None and filter_knowledge_point(2, {1, 2}) == 2
```

- [ ] **Step 2:** 运行 `pytest tests/test_grading_rules.py tests/test_matching.py -v`，预期 FAIL。
- [ ] **Step 3:** 实现。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: grading schema, student matching and review rules`。

---

### Task 10: 批改流水线与 Worker

**Files:**
- Create: `backend/app/grading/prompts.py`, `backend/app/grading/crop.py`, `backend/app/grading/pipeline.py`, `backend/app/jobs/worker.py`
- Modify: `backend/app/assignments/router.py`（`enqueue_grade_page` 接入 arq）
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: 任务 6 `Storage`；任务 7 `get_model`、`record_usage`、`ModelOutputError`；任务 8 `candidates`；任务 9 全部。
- Produces:
  - `build_grading_prompt(subject: str, grade: int, answer_items: list[AnswerItem], kps: list[KnowledgePoint]) -> str`。提示词要求只输出 7.1 的 JSON，并列出知识点候选 `id: 名称`。
  - `prepare_image(data: bytes) -> bytes`：按 EXIF 校正方向、长边 ≤ 2048、转 JPEG。
  - `crop(image: bytes, bbox: tuple[float, float, float, float]) -> bytes`；裁剪图 key：`crops/{teacher_id}/{assignment_id}/{question_result_id}.jpg`。
  - `async grade_page(db, storage, model, page_id: int) -> None`，按设计文档第 7 节执行。答案确定规则：作业 `answer_key_status=="confirmed"` 且有对应 `question_no` 的 `AnswerItem` 时，用其 `answer` 和 `max_score`，`answer_verified=True`，`is_correct` 仍取模型判断；否则 `answer_verified=False`。
  - Worker：`WorkerSettings.functions = [grade_page_job]`，`max_tries = 3`；`grade_page_job(ctx, page_id)` 开新会话调用 `grade_page`。

- [ ] **Step 1: 写失败的测试**（用 `FakeModel`、`LocalStorage`）

```python
async def test_grades_page_and_creates_submission(db, storage, uploaded_page, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[
        q(no="1", is_correct=True, score=2, max_score=2, confidence=0.95),
        q(no="2", is_correct=False, score=0, max_score=4, confidence=0.9)])])
    await grade_page(db, storage, model, uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "done" and page.student_id == roster_zhangsan.id
    sub = (await db.execute(select(Submission))).scalar_one()
    assert sub.total_score == 2
    results = (await db.execute(select(QuestionResult).order_by(QuestionResult.question_no))).scalars().all()
    assert results[0].crop_key is None and results[1].crop_key is not None
    assert all(r.answer_verified is False and r.needs_review for r in results)  # 无答案卷

async def test_confirmed_answer_key_marks_verified(db, storage, uploaded_page, confirmed_key_q1_q2, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[q(no="1", confidence=0.95)])])
    await grade_page(db, storage, model, uploaded_page.id)
    r = (await db.execute(select(QuestionResult))).scalar_one()
    assert r.answer_verified is True and r.needs_review is False

async def test_second_page_without_name_joins_previous_student(db, storage, two_uploaded_pages, roster_zhangsan):
    model = FakeModel([graded(student_name="张三", questions=[q(no="1")]),
                       graded(student_name=None, questions=[q(no="5")])])
    await grade_page(db, storage, model, two_uploaded_pages[0].id)
    await grade_page(db, storage, model, two_uploaded_pages[1].id)
    assert (await db.execute(select(func.count(Submission.id)))).scalar() == 1

async def test_unreadable_page_fails(db, storage, uploaded_page):
    await grade_page(db, storage, FakeModel([graded(student_name=None, questions=[])]), uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "failed" and page.fail_reason == "unreadable"

async def test_invalid_output_retries_then_fails(db, storage, uploaded_page):
    model = FakeModel([{"oops": 1}, ModelOutputError("bad")])
    await grade_page(db, storage, model, uploaded_page.id)
    page = await db.get(Page, uploaded_page.id)
    assert page.status == "failed" and page.fail_reason == "model_output_invalid"
    assert len(model.prompts) == 2

async def test_usage_recorded(db, storage, uploaded_page, roster_zhangsan):
    await grade_page(db, storage, FakeModel([graded(student_name="张三", questions=[q(no="1")])]), uploaded_page.id)
    assert (await db.execute(select(func.count(UsageRecord.id)))).scalar() == 1
```

（`graded()`、`q()` 是 conftest 中构造模型输出 dict 的小工具，`q` 默认 `confidence=0.95, is_correct=True, score=max_score=2, bbox=[0.1,0.1,0.9,0.2]`。）
- [ ] **Step 2:** 运行 `pytest tests/test_pipeline.py -v`，预期 FAIL。
- [ ] **Step 3:** 实现。页面处理开始时置 `processing`；续页判断用同一作业中 `seq = 当前 seq - 1` 的页面的 `student_id`，该页未完成时视为无前页。
- [ ] **Step 4:** 运行 PASS；本地 `arq app.jobs.worker.WorkerSettings` 能启动。
- [ ] **Step 5:** 提交 `feat: grading pipeline and arq worker`。

---

### Task 11: 答案卷提取与确认

**Files:**
- Create: `backend/app/grading/answer_key.py`
- Modify: `backend/app/assignments/router.py`
- Test: `backend/tests/test_answer_key.py`

**Interfaces:**
- Produces:
  - `POST /api/assignments/{id}/answer-key`（multipart `file`）→ 同步调用 `get_model("answer_key")` 提取 `[{question_no, answer, max_score, is_subjective}]`，写入 `answer_items`，`answer_key_status="pending"`，返回列表。
  - `PUT /api/assignments/{id}/answer-key {items: [...]}` → 整体替换 `answer_items`，`answer_key_status="confirmed"`。
  - 作业已有 `done` 页面后再确认答案卷：不自动重批，返回字段 `regrade_suggested: true`（重批功能留到 M3 按需做）。

- [ ] **Step 1: 写失败的测试**

```python
async def test_extract_then_confirm(auth_client, my_assignment, jpeg_bytes, fake_model_answer_key):
    url = f"/api/assignments/{my_assignment.id}/answer-key"
    items = (await auth_client.post(url, files={"file": ("k.jpg", jpeg_bytes, "image/jpeg")})).json()["items"]
    assert items[0]["question_no"] == "1"
    items[0]["answer"] = "62.8dm³"
    r = await auth_client.put(url, json={"items": items})
    assert r.json()["answer_key_status"] == "confirmed"
```

- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: answer key extraction and confirmation`。

---

### Task 12: 复核接口

**Files:**
- Create: `backend/app/review/router.py`
- Test: `backend/tests/test_review.py`

**Interfaces:**
- Produces:
  - `GET /api/assignments/{id}/review` → `{pages_unassigned: [{page_id, image_url, recognized_name}], questions: [{id, student_name, question_no, question_text, student_answer, correct_answer, is_correct, score, max_score, confidence, reason: "low_confidence"|"unverified_answer"|"student_uncertain", crop_url}]}`。图片用 `signed_url`。
  - `PATCH /api/pages/{id} {student_id}` → 指定学生，合并到该学生的 submission，该页所有题按规则重新计算 `needs_review`。
  - `PATCH /api/question-results/{id} {is_correct?, score?}` → 保存修改，`reviewed=True`、`needs_review=False`；首次修改时把模型原值存入 `model_is_correct`、`model_score`（任务 2 中加这两列），并重算 submission 总分。

- [ ] **Step 1: 写失败的测试**

```python
async def test_teacher_correction_updates_total(auth_client, graded_submission):
    qr = graded_submission.questions[0]          # 模型判对，2 分
    r = await auth_client.patch(f"/api/question-results/{qr.id}", json={"is_correct": False, "score": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["reviewed"] is True and body["model_is_correct"] is True
    sub = (await auth_client.get(f"/api/submissions/{graded_submission.id}")).json()
    assert sub["total_score"] == graded_submission.total_score - 2

async def test_assign_student_to_unmatched_page(auth_client, unmatched_page, roster_zhangsan):
    r = await auth_client.patch(f"/api/pages/{unmatched_page.id}", json={"student_id": roster_zhangsan.id})
    assert r.status_code == 200
    review = (await auth_client.get(f"/api/assignments/{unmatched_page.assignment_id}/review")).json()
    assert review["pages_unassigned"] == []

async def test_cannot_assign_student_from_other_class(auth_client, unmatched_page, other_class_student):
    r = await auth_client.patch(f"/api/pages/{unmatched_page.id}", json={"student_id": other_class_student.id})
    assert r.status_code == 404
```

- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现；加 `GET /api/submissions/{id}`。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: review queue and teacher corrections`。

---

### Task 13: 原图 30 天清理

**Files:**
- Create: `backend/app/jobs/cleanup.py`
- Modify: `backend/app/jobs/worker.py`（`cron_jobs` 每天 03:00 Asia/Shanghai 运行）
- Test: `backend/tests/test_cleanup.py`

**Interfaces:**
- Produces: `async purge_old_originals(db, storage, now: datetime, retention_days: int) -> int`：删除 `created_at < now - retention_days` 且 `original_deleted_at IS NULL` 的页面原图，置 `original_deleted_at=now`，返回删除数；裁剪图不动。

- [ ] **Step 1: 写失败的测试**

```python
async def test_purges_only_old_originals_keeps_crops(db, storage, page_factory):
    old = await page_factory(created_days_ago=31, with_crop=True)
    new = await page_factory(created_days_ago=5)
    n = await purge_old_originals(db, storage, now=utcnow(), retention_days=30)
    assert n == 1
    assert not await storage_exists(storage, old.image_key)
    assert await storage_exists(storage, old.crop_keys[0])
    assert await storage_exists(storage, new.image_key)
    assert await purge_old_originals(db, storage, now=utcnow(), retention_days=30) == 0
```

- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现。
- [ ] **Step 4:** 运行 PASS。
- [ ] **Step 5:** 提交 `feat: daily purge of original photos after 30 days`。

---

### Task 14: 模型评测脚本

**Files:**
- Create: `backend/scripts/benchmark_models.py`
- Test: `backend/tests/test_benchmark.py`

**Interfaces:**
- 输入目录结构：`bench/<case_id>/page.jpg` + `bench/<case_id>/truth.json`（人工标注：`subject, grade, questions: [{no, is_correct, score}]`）。
- 命令：`python scripts/benchmark_models.py --dir bench --models qwen:qwen-vl-max doubao:<model> --out bench_report.csv`。
- Produces: `score_case(truth: dict, graded: GradedPage) -> CaseScore(matched: int, total: int, correct_agree: int, score_abs_err: float)`；按题号对齐，未识别到的题计入 `total` 不计入 `matched`。报告按模型、学科汇总：判对错一致率、识别覆盖率、平均耗时、平均每页成本（分）。

- [ ] **Step 1: 写失败的测试**

```python
def test_score_case_alignment():
    truth = {"questions": [{"no": "1", "is_correct": True, "score": 2},
                           {"no": "2", "is_correct": False, "score": 0}]}
    graded = GradedPage(student_name=None, questions=[make_q(no="1", is_correct=False, score=0)])
    assert score_case(truth, graded) == CaseScore(matched=1, total=2, correct_agree=0, score_abs_err=2.0)
```

- [ ] **Step 2:** 运行，预期 FAIL。
- [ ] **Step 3:** 实现脚本（复用任务 10 的 `build_grading_prompt`、`prepare_image` 和任务 9 的 `GradedPage`）。
- [ ] **Step 4:** 运行 PASS；用 3 张样例卷手动跑一次，确认 CSV 生成。
- [ ] **Step 5:** 提交 `feat: model benchmark script`。

---

### M1 完成标准

- [ ] `pytest` 全部通过。
- [ ] 本地起 MySQL + Redis + API + Worker，用真实通义千问 key，按顺序调用接口：登录（用测试 `WeChatClient`）→ 建班导名单 → 建作业 → 传答案卷并确认 → 上传 3 张真实卷子 → 进度变为全部 `done` → 复核队列有数据 → 修改一题后总分正确。
- [ ] 评测脚本对 ≥100 张标注卷跑完两家模型，结果记录到 `docs/benchmark/` 并确定 `MODEL_FOR_GRADING`。
