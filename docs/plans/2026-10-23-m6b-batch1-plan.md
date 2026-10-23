# M6b 第一批（电脑上建班、建作业、答案卷、批量上传、待认领）开发计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 老师在电脑网页上建班（粘贴名单）、建作业、上传并核对答案卷，把一批照片 / PDF / ZIP 一次传上去批改，在「待认领」里把没归属的页指给学生，并在作业页看批改进度、重试、换图、删废页。

**Architecture:** 后端只做少量改动：页面加来源标记（`phone` / `web`，迁移 0012），三处「没名字页跟随前一页」的逻辑只在相邻两页都是手机来源时生效；新增删页接口、待认领候选接口，`/api/me` 带上本月额度。其余全部复用现有接口。网页在 `web/` 新增班级、作业、上传、待认领、答案卷页面；文件转换（ZIP 解压、PDF 拆页、HEIC 解码、压缩到 2000px JPEG、读拍摄时间）在浏览器里完成，服务器仍只收 JPEG。

**Tech Stack:** 后端 Python 3.11 / FastAPI / SQLAlchemy async / Alembic / pytest；网页 React 18.3.1 + react-router-dom 6.28.0 + TypeScript 5.7.2 + Vite 5.4.11 + Vitest 2.1.8（已有），新增浏览器端库：fflate 0.8.2（ZIP）、pdfjs-dist 4.10.38（PDF 渲染，worker 用 Vite `?url` 打包进 `web/`）、heic2any 0.0.4（HEIC）、exifr 7.1.3（拍摄时间）。

**Spec:** `docs/specs/2026-10-23-m6b-web-full-design.md`（上游：`docs/specs/2026-10-23-m6-web-admin-design.md`、`docs/specs/2026-10-21-m3-miniprogram-design.md`）

**执行顺序：** 1 → 2 → 3 → 3b → 5 → 4 → 6 → 7 → 8 → 9（任务 4 的「换一张」用到任务 5 的 `prepareOne`）。

## Global Constraints

- 页面来源：`Page.source` 取值 `phone` / `web`，迁移给已有数据一律 `phone`；只有网页批量上传传 `source=web`。小程序不改、不重新上传。
- 「没名字页跟随前一页」只在**相邻两页都是 `phone`** 时生效——批改时匹配（`_previous_student`）、批改完成后接上后续页（`attach_following_pages`）、改归属时连带移动（`_move_continuation`）三处一致。
- 待认领 = 这份作业里 `status = done` 且 `student_id` 为空的所有页（与现有复核接口 `pages_unassigned` 同一批数据）。
- 候选排序：这页上的题号该学生已有页里**一个都没有**的排前面，其次按名单顺序（同现有学生列表顺序）；只排序，必须老师点选。
- 废页：彻底删除（页、图片、批改结果、裁剪图），任何状态都可删，**不退额度**，删后同一张图可重新上传；网页上二次确认。
- 格式：JPG、PNG、HEIC/HEIF、WebP、PDF（每页一张）、ZIP（内含上述格式；忽略 `__MACOSX/`、以 `.` 开头的文件和其它格式）。全部在浏览器里转成长边 ≤ 2000px 的 JPEG（质量 0.85）后走现有上传接口。
- 排序：有拍摄时间的按时间在前，没有的按文件名自然排序在后；PDF 内按页码；预览可删、可拖动调整，但顺序只是展示用。
- 单批最多 **200 页**（硬限制，提示「一次最多上传 200 页，请分批上传」）；上传前显示本月剩余额度，超出时提醒「本月还能批改 N 页，这批有 M 页」并可选「只传前 N 页」；上传中遇到 429 停止并列出没传的页。
- 上传并发 3；上传结束汇总「上传 N 页，跳过重复 M 页，失败 K 页」；上传进行中离开页面要拦住并提示「还有 N 页没传完，确定离开吗？」，不做后台续传。
- 不可恢复操作（删班、删学生、废页）必须二次确认，确认框写清后果（删班：「作业和成绩会一起删除，无法恢复」）。
- 网页沿用 M6：同源 `/api/...`、`request` / `errorText` / `Header`、温暖纸本配色、7 天登录；新页面加在 `web/src/App.tsx` 路由里且需登录。
- 文案与校验沿用小程序（建班的年级、名单粘贴规则、学科列表与「记住上次学科」、答案卷核对规则）：把小程序 `miniprogram/src/lib/` 里对应的纯逻辑模块（`roster.ts`、`grades.ts`、`subjects.ts`、`answerKey.ts`）复制到 `web/src/lib/` 并保持行为一致（文件头注明来源）。
- 新接口按老师归属校验，他人资源 404。
- Windows 环境：Bash 工具遇到中文路径会失败，用 PowerShell；后端 venv 在 `backend/.venv`；本机开着的后端 / worker / 小程序监听构建不要动。提交信息以空行加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 结尾，多行信息用无 BOM 的文件 `git commit -F`；不要提交 `miniprogram/project.config.json`、`project.private.config.json` 和 pptx 文件。

## Review Focus

1. **网页上传的有名字页后面紧跟一张手机拍的没名字页（或反过来）**：两页来源不同，不能互相跟随，没名字的那页进待认领。→ 任务 1 测试 `test_mixed_sources_never_chain`。
2. **待认领里把一页指给学生后，紧跟在它后面的网页没名字页不能被「连带」拉过去**：只有被点的那一页归属。→ 任务 1 测试 `test_assign_web_page_does_not_drag_next_web_page`。
3. **删一张还在排队或批改中的页**：删除成功，worker 拿到这个页时安静跳过、不报错、不留下孤立结果。→ 任务 2 测试 `test_delete_queued_page_then_job_is_noop`。
4. **ZIP 里套着系统隐藏文件、PDF 打不开、HEIC 解码失败**：坏文件单独列出原因，其余照常进预览，预览页数 = 将上传的页数。→ 任务 5 测试 `expandFiles reports bad files and keeps the rest`。
5. **一批里一部分照片有拍摄时间、一部分没有、文件名像 IMG_2 / IMG_10**：有时间的按时间在前，没有的按自然文件名在后。→ 任务 5 测试 `sortPages mixes taken-time and natural filename order`。

---

## 一、后端（任务 1–2）

### Task 1: 页面来源与「不跟随」规则

**Files:**
- Create: `backend/migrations/versions/0012_page_source.py`（`down_revision = "0011"`）
- Modify: `backend/app/models.py`（`Page.source: Mapped[str] = mapped_column(String(8), default="phone", server_default="phone")`）、`backend/app/assignments/router.py`（`upload_page` 增加查询参数 `source: Literal["phone", "web"] = "phone"`，写入新页；重复图片不改已有页的来源）、`backend/app/grading/pipeline.py`（`_previous_student`、`attach_following_pages`）、`backend/app/review/router.py`（`_move_continuation`）
- Test: `backend/tests/test_page_source.py`

**Interfaces:**
- Produces: `POST /api/assignments/{id}/pages?source=web`；`PageListItem` 增加 `source: str`；规则「两页都是 `phone` 才跟随」。
- [ ] **Step 1: 写失败的测试**：`test_upload_defaults_to_phone_and_accepts_web`、`test_web_nameless_page_goes_unassigned`（前一页有学生、这页网页来源没名字 → `student_id` 为空，出现在 `/review` 的 `pages_unassigned`）、`test_phone_pages_still_chain`（现有行为不变）、`test_mixed_sources_never_chain`（web 有名 + phone 无名、phone 有名 + web 无名，都不跟随）、`test_assign_web_page_does_not_drag_next_web_page`（`PATCH /pages/{id}` 后下一张 web 无名页仍未归属）、`test_page_list_includes_source`
- [ ] **Step 2: 运行确认失败**：`.venv\Scripts\python -m pytest tests/test_page_source.py -q`
- [ ] **Step 3: 实现**（迁移在本机 `alembic upgrade head` 跑通；三处判断写成一个小函数 `chains(prev: Page, nxt: Page) -> bool` 放在 `pipeline.py` 共用）
- [ ] **Step 4: 全量测试通过并提交** `feat(pages): page source; web pages never follow the previous page`

### Task 2: 删页、待认领候选、额度

**Files:**
- Modify: `backend/app/assignments/router.py`（删页）、`backend/app/review/router.py`（候选）、`backend/app/auth/router.py`（`MeOut` 加额度）、必要时 `backend/app/jobs/worker.py` / `backend/app/grading/pipeline.py`（页不存在时跳过）
- Test: `backend/tests/test_page_delete.py`、`backend/tests/test_claim_candidates.py`、`backend/tests/test_auth.py`（额度字段）

**Interfaces:**
- Consumes: 任务 1 的 `Page.source`
- Produces:
  - `DELETE /api/pages/{page_id}` → 204：加作业锁；删该页的 `QuestionResult`、裁剪图与原图（存储里不存在时忽略），删页；受影响的提交重新计算（`recompute_submission`；提交下已无结果时删除该提交）；他人或不存在 404。
  - `GET /api/pages/{page_id}/claim-candidates` → `{"page_id", "image_url", "question_nos": [str], "candidates": [{"student_id", "name", "missing_all": bool, "page_count": int, "thumb_url": str | null}]}`：`question_nos` 为该页结果里的题号（去重、自然排序）；`missing_all` 为「该学生已有页里一个都没有这些题号」；`thumb_url` 为该学生 seq 最小的一页的签名图（没有页为 null）；排序：`missing_all` 为真的在前，其余按现有学生列表顺序；页未批改完 409「页面尚未批改完成」。
  - `GET /api/me` 增加 `quota_total: int`（`MONTHLY_PAGE_QUOTA`）、`quota_used: int`（`pages_used_this_month`）。
- [ ] **Step 1: 写失败的测试**：`test_delete_done_page_recomputes_submission`、`test_delete_page_removes_images_and_allows_reupload`（同一张图再传不再是 duplicate）、`test_delete_queued_page_then_job_is_noop`（删除后直接调用批改任务函数处理该 page_id：不抛异常、无结果写入）、`test_delete_other_teachers_page_404`、`test_delete_does_not_refund_quota`、`test_candidates_missing_all_first_then_roster_order`、`test_candidates_409_until_done`、`test_candidates_other_teacher_404`、`test_me_includes_quota`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 全量测试通过并提交** `feat(pages): delete page, claim candidates, quota on /me`

## 二、网页（任务 3–8）

### Task 3: 班级管理

**Files:**
- Create: `web/src/lib/roster.ts`、`web/src/lib/grades.ts`（从小程序复制）、`web/src/pages/ClassNew.tsx`、`web/src/pages/ClassDetail.tsx`、`web/src/components/Confirm.tsx`（二次确认框，之后各页共用）
- Modify: `web/src/App.tsx`（路由 `/classes/new`、`/classes/:classId`）、`web/src/pages/Home.tsx`（「新建班级」按钮；班级名旁「管理」进班级页）、`web/src/theme.css`
- Test: `web/tests/roster.test.ts`（复制小程序对应测试并通过）、`web/tests/classes.test.tsx`

**Interfaces:**
- Consumes: `POST /api/classes`、`GET /api/classes`、`POST /api/classes/{id}/students:import`、`GET /api/classes/{id}/students`、`PATCH /api/students/{id}`、`DELETE /api/students/{id}`、`DELETE /api/classes/{id}`（请求体与返回见 `backend/app/classes/router.py`；行为参照小程序 `pages/class-edit`、`pages/class`）
- Produces: `Confirm` 组件 `({ title, message, confirmText, danger?, onConfirm, onCancel })`
- 建班：班级名、年级下拉（1–9）、名单文本框（粘贴），提交后显示「新增 N 人，跳过重复 M 人」并进班级页。班级页：名单（改名、删除）、追加名单、删除班级（`Confirm`，文案见全局约束）。
- [ ] **Step 1: 写失败的测试**：roster 解析测试（复制）、`creating a class imports the pasted roster`、`deleting a class asks for confirmation first`、`deleting a student asks for confirmation first`
- [ ] **Step 2: 运行确认失败**：在 `web/` 下 `npx vitest run`
- [ ] **Step 3: 实现**
- [ ] **Step 4: 全量 vitest、`npx tsc --noEmit`、`npm run build` 通过并提交** `feat(web): create classes and manage the roster`

### Task 3b: 账号设置（改署名、看额度）

**Files:**
- Create: `web/src/components/AccountDialog.tsx`
- Modify: `web/src/components/Header.tsx`（老师名字可点击；没设署名时显示「设置署名」）、`web/src/theme.css`
- Test: `web/tests/account.test.tsx`

**Interfaces:**
- Consumes: `GET /api/me`（任务 2 加的 `quota_total` / `quota_used`）、`PATCH /api/me` body `{"display_name"}`（≤ 32 字，去首尾空格）
- Produces: `Header` 点名字打开 `AccountDialog`：可修改署名（说明「PDF 上印的署名，小程序和网页同时生效」）、显示「本月已批改 X / Y 页」；保存后页头立即显示新名字。
- [ ] **Step 1: 写失败的测试**：`clicking the name opens the dialog with the current name`、`saving trims, PATCHes and updates the header`、`empty or over-32 names show an error and are not sent`、`no name shows 设置署名`、`dialog shows quota used / total`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 全量通过并提交** `feat(web): edit the signature name and see the monthly quota`

### Task 4: 建作业与作业页（批改进度）

**Files:**
- Create: `web/src/lib/subjects.ts`（从小程序复制）、`web/src/pages/AssignmentNew.tsx`、`web/src/pages/AssignmentWork.tsx`、`web/src/lib/pages.ts`
- Modify: `web/src/App.tsx`（`/classes/:classId/assignments/new`、`/a/:assignmentId/work`）、`web/src/pages/Home.tsx` 与 `web/src/pages/Overview.tsx`（入口）
- Test: `web/tests/assignmentWork.test.tsx`、`web/tests/pages.lib.test.ts`

**Interfaces:**
- Consumes: `POST /api/assignments`、`GET /api/assignments/{id}`、`GET /api/assignments/{id}/progress`、`GET /api/assignments/{id}/pages`（含任务 1 的 `source`）、`POST /api/pages/{id}:retry`、`POST /api/pages/{id}:replace`、任务 2 的 `DELETE /api/pages/{id}`；`GET /api/me` 的 `last_subject`
- Produces:
  - `pageStatusText(p: PageListItem): string`（排队中 / 批改中 / 完成 / 失败：原因 / 待认领——`done` 且无学生时）
  - 作业页 `/a/:id/work`：顶部进度（总数、完成、失败、待认领数、需复核数），按钮「上传卷子」→ `/a/:id/upload`、「待认领 N 页」→ `/a/:id/claim`、「答案卷」→ `/a/:id/answer-key`、「学情」→ `/a/:id`；页列表（缩略图可省，显示页序、来源「手机 / 网页」、状态、学生名或识别名）；失败页「重试」（仅可重试的失败原因）与「换一张」（选文件，经任务 5 的 `prepareOne` 转成 JPEG 后调 `:replace`）；每页「删除」（`Confirm`）；有排队 / 批改中的页时每 3 秒刷新，否则停。
- 建作业：班级（从入口带入）、标题、学科（默认 `last_subject`），提交后进 `/a/:id/work`。
- [ ] **Step 1: 写失败的测试**：`pageStatusText covers every state`、`work page polls while pages are queued and stops when done`、`delete page asks for confirmation then calls DELETE`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**（「换一张」只接受图片，用任务 5 的 `prepareOne` 转成 JPEG——任务 5 在本任务之前执行）
- [ ] **Step 4: 全量通过并提交** `feat(web): create assignments and track grading progress`

### Task 5: 文件转换与排序（纯逻辑库）

**Files:**
- Create: `web/src/lib/intake.ts`
- Modify: `web/package.json`（加 fflate 0.8.2、pdfjs-dist 4.10.38、heic2any 0.0.4、exifr 7.1.3，锁定版本并提交 package-lock）
- Test: `web/tests/intake.test.ts`

**Interfaces:**
- Produces:
  - `type SourcePage = { id: string; fileName: string; pageNo: number | null; takenAt: number | null; load: () => Promise<Blob> }`（`load` 返回原始图片或 PDF 渲染出的图片，延迟到压缩时才执行，避免一次占满内存）
  - `type BadFile = { fileName: string; reason: string }`（原因文案：「这个 PDF 打不开」「这张 HEIC 图片解码失败」「不支持的文件格式」「压缩包打不开」）
  - `expandFiles(files: File[]): Promise<{ pages: SourcePage[]; bad: BadFile[] }>`：ZIP 展开（忽略 `__MACOSX/`、`.` 开头、不支持的格式）、PDF 按页展开（`pageNo` 从 1 起）、读取拍摄时间（exifr，读不到为 null，不报错）
  - `sortPages(pages: SourcePage[]): SourcePage[]`：有 `takenAt` 的按时间升序在前；没有的按文件名自然排序（`localeCompare` 带 `numeric: true`）在后；同一 PDF 内按 `pageNo`
  - `toJpeg(blob: Blob, maxSide = 2000, quality = 0.85): Promise<Blob>`（HEIC 先经 heic2any；PDF 页由 `load` 已渲染为图片）
  - `prepareOne(file: File): Promise<Blob>`（单张图片 → JPEG，供「换一张」）
  - `MAX_BATCH = 200`
- [ ] **Step 1: 写失败的测试**（转换库用 `vi.mock` 替身，测本模块自己的逻辑）：`expandFiles reports bad files and keeps the rest`、`zip entries skip __MACOSX and dotfiles`、`pdf expands to one SourcePage per page with pageNo`、`sortPages mixes taken-time and natural filename order`、`toJpeg keeps the long side at most 2000px`（用 canvas 替身断言目标尺寸计算）
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**（pdfjs worker 用 `import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'`；PDF 渲染缩放使长边约 2000px）
- [ ] **Step 4: 全量通过，`npm run build` 通过（确认 worker 与 heic2any 被打包进 `dist/`，不引外部 CDN）并提交** `feat(web): convert and order uploaded files in the browser`

### Task 6: 批量上传页

**Files:**
- Create: `web/src/pages/Upload.tsx`、`web/src/lib/uploader.ts`
- Modify: `web/src/App.tsx`（`/a/:assignmentId/upload`）、`web/src/lib/api.ts`（如需 `FormData` 上传辅助）
- Test: `web/tests/uploader.test.ts`、`web/tests/upload.test.tsx`

**Interfaces:**
- Consumes: 任务 5 的 `expandFiles` / `sortPages` / `toJpeg` / `MAX_BATCH`；`POST /api/assignments/{id}/pages?source=web`（multipart 字段 `file`）→ `{page_id, seq, status, duplicate}`；`GET /api/me` 的 `quota_total` / `quota_used`
- Produces:
  - `type UploadState = 'waiting' | 'uploading' | 'done' | 'duplicate' | 'failed' | 'skipped_quota'`
  - `uploadAll(assignmentId: number, pages: SourcePage[], onChange: (id: string, s: UploadState, err?: string) => void, concurrency = 3): Promise<{ uploaded: number; duplicates: number; failed: number; quotaStopped: boolean }>`：每页 `toJpeg` 后上传；429 → 停止派发新页，未传的标 `skipped_quota`；其它错误该页 `failed`，可单独重试
  - `summaryText(r): string` → 「上传 N 页，跳过重复 M 页，失败 K 页」（额度停止时追加「本月额度已用完，剩下 X 页没有上传」）
- 页面：选择文件按钮 + 拖放区；展开后显示预览网格（缩略图、来源文件名、PDF 页码），可删除、拖动排序；坏文件单独列出；超过 200 页提示并禁止开始；显示「本月还能批改 N 页」，超出时提醒并给「只传前 N 页」；开始后显示整体进度与每页状态，失败页「重试」；上传中用 `beforeunload` 和路由拦截提示离开；结束显示汇总与「去作业页」按钮。
- [ ] **Step 1: 写失败的测试**：`uploadAll runs at most 3 at a time`、`uploadAll marks duplicates and counts them`、`uploadAll stops on 429 and marks the rest skipped_quota`、`summaryText wording`、`start is disabled above 200 pages`、`quota warning offers uploading only the first N pages`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 全量通过并提交** `feat(web): batch upload with preview, quota check and summary`

### Task 7: 待认领页

**Files:**
- Create: `web/src/pages/Claim.tsx`、`web/src/lib/claim.ts`
- Modify: `web/src/App.tsx`（`/a/:assignmentId/claim`）
- Test: `web/tests/claim.test.tsx`

**Interfaces:**
- Consumes: `GET /api/assignments/{id}/review` 的 `pages_unassigned`；任务 2 的 `GET /api/pages/{id}/claim-candidates`、`DELETE /api/pages/{id}`；`PATCH /api/pages/{id}` body `{"student_id"}`（409 文案原样显示）
- Produces: `nextIndex(list: number[], current: number): number`（处理完一页后跳到下一页，列表空时返回 -1）
- 页面：左边原图（点开放大），右边候选列表（名字、`missing_all` 时标「缺这些题」、已有页缩略图）；上下键选候选、回车确认归属、自动跳到下一页；「废页 / 不是这个班的」→ `Confirm` 后删页；全部处理完显示「没有待认领的页了」并给「回作业页」。
- [ ] **Step 1: 写失败的测试**：`first candidate is preselected and Enter assigns it`、`after assigning, the next unassigned page loads`、`discard asks for confirmation then deletes`、`409 from assign shows the server message`、`nextIndex at end returns -1`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**（键盘只在没有输入框获得焦点时生效）
- [ ] **Step 4: 全量通过并提交** `feat(web): claim unassigned pages with keyboard`

### Task 8: 答案卷

**Files:**
- Create: `web/src/lib/answerKey.ts`（从小程序复制核对规则）、`web/src/lib/answerKeyMerge.ts`、`web/src/pages/AnswerKey.tsx`
- Modify: `web/src/App.tsx`（`/a/:assignmentId/answer-key`）
- Test: `web/tests/answerKey.test.ts`（复制）、`web/tests/answerKeyMerge.test.ts`、`web/tests/answerKeyPage.test.tsx`

**Interfaces:**
- Consumes: 任务 5 的 `expandFiles` / `sortPages` / `toJpeg`；`GET / POST / PUT /api/assignments/{id}/answer-key`（`POST` 收一张图、返回该图提取出的题目并覆盖服务器上的待确认结果；`PUT` 提交最终题目——请求体与返回见 `backend/app/assignments/router.py` 的 `AnswerKeyOut` / 确认模型，行为参照小程序 `pages/answer-key`）
- Produces:
  - `mergeKeys(pages: { pageIndex: number; items: AnswerItem[] }[]): { items: AnswerItem[]; overridden: string[] }`（题号重复时后一页为准，`overridden` 列出被覆盖的题号）
- 页面：选择答案卷文件（同上传格式，可多文件 / 多页）→ 逐页 `POST` 提取并显示进度；某页失败标「第 N 页没提取出来」，可「重试这一页」或「跳过」；合并后进入核对表格（题号、答案、分值，可改、可删、可加行；`overridden` 的题号标出「多页里都有，请核对」）；「确认保存」调 `PUT`。已有确认过的答案卷时显示并允许重新上传覆盖（提示会替换现有答案）。
- [ ] **Step 1: 写失败的测试**：`mergeKeys later page wins and lists overridden`、`a failed page can be retried or skipped`、`confirm sends the merged edited items once`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 全量通过并提交** `feat(web): upload and confirm the answer key from PDFs or photos`

## 三、收尾（任务 9）

### Task 9: 验收清单

**Files:**
- Create: `docs/benchmark/m6b-batch1-acceptance.md`

- [ ] **Step 1: 按设计文档第 8 节中属于第一批的条目（建班、答案卷、批量上传、排序、待认领、批改进度、权限）逐条列表，结果栏留空；顶部「上线前步骤」：合并 → `deploy\deploy.ps1`（迁移 0012 会自动执行）→ 冒烟检查（网页能打开、`/api/me` 带额度字段、上传一张 `?source=web` 的图后作业页显示来源「网页」）。小程序无需重新上传。**
- [ ] **Step 2: 提交** `docs: M6b batch 1 acceptance checklist`
