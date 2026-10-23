# M6 网页后台（讲评投屏 + 下载打印）开发计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 老师在电脑浏览器打开网页，用小程序扫码登录，选作业看每题错误率格子，点开一道题全屏投影（错答分组 + 学生原图 + AI 错因，不显示姓名），在单独的下载页下载讲评单 / 全班错题单 / 练习卷 PDF 打印。

**Architecture:** 后端新增 `app/weblogin`：微信小程序码生成（access_token 缓存）、Redis 票据存储、扫码登录接口；其余数据全部复用现有接口。小程序新增「确认登录网页版」页。新目录 `web/` 是 Vite + React 单页应用，构建产物随部署上传，由同一个 nginx 提供，`/api/` 转后端（同源）。

**Tech Stack:** 后端 Python 3.11 / FastAPI / redis-py 5（`redis.asyncio`，arq 已带）/ httpx / pytest；小程序 Taro 4.3 + React 18 + TypeScript + Vitest；网页 Vite 5.4.11 + React 18.3.1 + react-router-dom 6.28.0 + TypeScript 5.7.2 + Vitest 2.1.8 + jsdom 25.0.1 + @testing-library/react 16.1.0。

**Spec:** `docs/specs/2026-10-23-m6-web-admin-design.md`（上游：`docs/specs/2026-10-22-m4-analytics-design.md`、`docs/specs/2026-10-22-m5-practice-design.md`）

## Global Constraints

- 网页只读：不提供拍照、上传、建班、建作业、改分、复核、生成或换练习题的入口；唯一的写操作是署名（`PATCH /api/me`）和导出 PDF（`POST /api/assignments/{id}/exports`）。
- 投影页（题目页）**任何位置都不渲染学生姓名**；接口照旧返回姓名，只在前端不显示。
- 扫码票据：Redis 存 **300 秒**；票据号 `secrets.token_urlsafe(12)`（16 字符，放进小程序码 `scene`，≤32）；轮询密钥 `secrets.token_urlsafe(24)`，不进二维码；配对数字 4 位（`f"{secrets.randbelow(10000):04d}"`）。凭证只能取走一次，取走即删票据。
- 状态取值：`pending`（待扫码）/ `scanned`（已扫码）/ `confirmed` / `cancelled`；票据不存在或已过期一律返回 `expired`。
- 创建票据限流：同一 IP 每 60 秒最多 10 次，超出 429「操作太频繁，请稍后再试」。
- 登录凭证复用 `app.auth.tokens.issue_token`（7 天，产品负责人决定）；「退出登录」只清浏览器本地，不做服务器作废。网页本地存储键 `hbj_token`。
- 小程序码：`wxacode.getUnlimited`，`page = settings.WX_QR_PAGE`（默认 `pages/web-login/index`），`env_version = settings.WX_QR_ENV_VERSION`（默认 `trial`，正式发布后改 `release`），`check_path = False`；access_token 缓存在 Redis 键 `wx:access_token`，TTL = `expires_in - 300`。
- 网页轮询间隔 2 秒；票据过期或取消后显示「二维码已过期，点击刷新」。
- 投影仪排版：1024×768 下不滚动可见「第 N 题 错了 X 人（Y%）」和前两组错答；根字号 ≥ 20px，主标题 ≥ 48px。
- 格子颜色：错误率 `wrong_count / student_count`：≥ 40% 深红、≥ 20% 橙、其余浅色；`student_count = 0` 显示「—」。主观题格子同样着色，加「主观」小标（偏离设计文档「主观题显示得分率」：现有统计只给满分率，计划按错误率统一，见交接说明）。
- 配色沿用小程序「温暖纸本」主题变量（取自 `miniprogram/src/app.scss`），网页另写一份 CSS 变量，不共用构建。
- 文案：登录页「用微信扫一扫，在小程序里确认登录」；已扫码「已扫码，请在手机上确认」；确认页「请核对电脑屏幕上的数字一致后再确认」；待复核提示「还有 N 项没复核，统计可能变化，请在手机上复核」；练习卷未生成「练习卷请先在手机上生成」；网络错误「网络不太好，请稍后再试」。
- 新接口按老师归属校验，他人资源 404；网页沿用后端已有的 404/409 文案。小程序新代码行内尺寸用 rpx。
- 开发环境登录：`settings.DEV_LOGIN: bool = False`；为 True 时才注册 `POST /api/auth/dev-login`（生产 `.env` 不设，路由不存在）。
- Windows 环境：Bash 工具遇到中文路径会失败，用 PowerShell；后端 venv 在 `backend/.venv`；小程序开发构建 `npm run dev:weapp`，体验版用 `npx taro build --type weapp --mode staging`。提交信息以空行加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 结尾，多行信息用无 BOM 的文件 `git commit -F`。

## Review Focus

1. **别人拍到/拿到二维码**（只知道票据号，不知道轮询密钥）：查询状态拿不到凭证，返回 404。→ 任务 2 测试 `test_poll_requires_poll_key`。
2. **两个网页标签同时轮询同一个已确认票据**（或确认后重复轮询）：只有第一次拿到 token，第二次是 `expired`。→ 任务 2 测试 `test_token_handed_out_once`。
3. **老师 B 扫了码但老师 A 去点确认**（或没扫码直接确认）：拒绝 409，票据仍归扫码的老师。→ 任务 2 测试 `test_confirm_only_by_the_teacher_who_scanned`。
4. **登录状态过期后在投影页翻题**（接口 401）：清掉本地凭证并回到登录页，不出现空白页或英文报错。→ 任务 5 测试 `test_401_clears_token_and_redirects`。
5. **错答组里有学生没有原图、或原图属于不在任何组的提交**：组照常显示人数，图只挂到对应组，不串组、不报错。→ 任务 7 测试 `cropsByGroup matches by submission_id and drops strays`。

---

## 一、后端（任务 1–3）

### Task 1: 微信小程序码

**Files:**
- Modify: `backend/app/auth/wechat.py`、`backend/app/config.py`（`WX_QR_PAGE = "pages/web-login/index"`、`WX_QR_ENV_VERSION = "trial"`、`DEV_LOGIN: bool = False`）、`deploy/.env.example`（注释说明 `WX_QR_ENV_VERSION`）
- Test: `backend/tests/test_wechat_qr.py`

**Interfaces:**
- Consumes: conftest 的 `MockTransport`
- Produces:
  - `class KeyValueCache(Protocol)`：`async def get(self, key: str) -> str | None`、`async def set(self, key: str, value: str, ttl_s: int) -> None`
  - `HttpWeChatClient.__init__(self, transport=None, cache: KeyValueCache | None = None)`
  - `async def HttpWeChatClient.wxacode(self, scene: str) -> bytes`：返回 PNG 字节；`WeChatClient` 协议加同名方法；conftest `FakeWeChatClient.wxacode` 返回固定字节 `b"\x89PNG-fake"` 并记录 `scene`
  - `class WeChatQrError(Exception)`
- [ ] **Step 1: 写失败的测试**：`test_wxacode_fetches_and_caches_access_token`（两次调用只换一次 token；缓存 TTL = expires_in − 300）、`test_wxacode_posts_scene_page_env_version`（请求体含 `scene`、`page`、`env_version: "trial"`、`check_path: false`）、`test_wxacode_error_json_raises`（微信回 JSON `errcode` 时抛 `WeChatQrError`；回 40001 时清缓存重换 token 重试一次）
- [ ] **Step 2: 运行确认失败**：`.venv\Scripts\python -m pytest tests/test_wechat_qr.py -q`
- [ ] **Step 3: 实现**：token 接口 `https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential`；码接口 `https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token=...`；成功时响应是图片（`content-type` 非 JSON）。
- [ ] **Step 4: 全量测试通过并提交** `feat(auth): WeChat mini program code with cached access token`

### Task 2: 扫码登录接口

**Files:**
- Create: `backend/app/weblogin/__init__.py`、`backend/app/weblogin/store.py`、`backend/app/weblogin/router.py`
- Modify: `backend/app/main.py`（注册路由，前缀 `/api`；`DEV_LOGIN` 为真时注册开发登录）、`backend/app/auth/router.py`（开发登录）、`backend/tests/conftest.py`（`fake_tickets` 夹具覆盖 `get_ticket_store`，内存实现）
- Test: `backend/tests/test_weblogin.py`

**Interfaces:**
- Consumes: 任务 1 的 `WeChatClient.wxacode`、`KeyValueCache`；`issue_token`；`current_teacher`
- Produces:
  - `store.py`：`class TicketStore(KeyValueCache, Protocol)` 加 `async def get_json(key) -> dict | None`、`async def set_json(key, value: dict, ttl_s: int)`、`async def delete(key)`、`async def incr(key, ttl_s: int) -> int`、`async def ttl(key) -> int`；`RedisTicketStore`（`redis.asyncio.from_url(settings.REDIS_URL)`，进程内单例）；`get_ticket_store() -> TicketStore`；`get_wechat_client` 给 `HttpWeChatClient` 传入同一个 store 作缓存
  - 票据 JSON：`{"poll_key", "pair_code", "status", "teacher_id": int | None}`，键 `weblogin:{ticket}`；限流键 `weblogin:rate:{ip}`
  - `POST /api/web-login/tickets`（不需登录）→ 201 `{"ticket", "poll_key", "pair_code", "qr_png": <base64>, "expires_in": 300}`；微信出错 → 503「二维码生成失败，请稍后再试」；限流 429
  - `GET /api/web-login/tickets/{ticket}?poll_key=...` → `{"status", "expires_in", "token": str | None, "teacher": {"id", "display_name"} | None}`；轮询密钥不对 → 404；`confirmed` 时返回 token 并删票据；不存在 → `{"status": "expired"}`
  - `POST /api/web-login/tickets/{ticket}:scan`（需登录）→ `{"pair_code"}`；`pending` → `scanned` 并记 `teacher_id`；已被别的老师扫过 → 409；过期 → 410「二维码已过期，请在电脑上刷新」
  - `POST /api/web-login/tickets/{ticket}:confirm` / `:cancel`（需登录）→ 204；只有扫码的那位老师、且状态为 `scanned` 才行，否则 409；过期 410。状态改动保留原 TTL。
  - `POST /api/auth/dev-login`（仅 `DEV_LOGIN`）body `{"teacher_id": int | None}` → `WxLoginOut`；不传时取 id 最小的老师，没有老师则新建一个
- [ ] **Step 1: 写失败的测试**：`test_create_ticket_returns_qr_and_pair_code`（`fake_wx` 收到的 scene 等于票据号）、`test_create_ticket_rate_limited`（第 11 次 429）、`test_poll_requires_poll_key`、`test_scan_confirm_then_poll_gets_token`（token 解出来是该老师 id；扫码后轮询状态为 `scanned`）、`test_token_handed_out_once`、`test_confirm_only_by_the_teacher_who_scanned`、`test_cancel_then_poll_is_cancelled`、`test_expired_ticket_scan_is_410`、`test_dev_login_absent_unless_enabled`（默认 404/405；`DEV_LOGIN=True` 新建 app 后可用）
- [ ] **Step 2: 运行确认失败**：`.venv\Scripts\python -m pytest tests/test_weblogin.py -q`
- [ ] **Step 3: 实现**：IP 取 `X-Real-IP` 头（nginx 已设置），没有时用 `request.client.host`。
- [ ] **Step 4: 本地真实冒烟（不进测试套件）**：本机后端 + Redis 起着时 `POST /api/web-login/tickets`，把返回的 `qr_png` 存成文件看一眼是小程序码（本机 `.env` 有真实 AppID/Secret）；写进报告。
- [ ] **Step 5: 全量测试通过并提交** `feat(weblogin): QR ticket login for the web admin`

### Task 3: 部署网页

（在任务 8 之后执行；放在这里是因为只改部署文件。）

**Files:**
- Modify: `deploy/nginx.conf`、`deploy/docker-compose.yml`、`deploy/deploy.ps1`
- Test: 手动（见步骤）

**Interfaces:**
- Consumes: 任务 5 的 `web/` 构建命令 `npm run build`（产物 `web/dist`）
- Produces: 服务器上 `~/mistake-book/deploy/web/` 为网页静态文件；nginx：`location /api/` 和 `location = /healthz` 转后端（保留现有 resolver、`proxy_read_timeout 180s`、`client_max_body_size 20m`），`location /` 用 `root /srv/web; try_files $uri /index.html;`，`/assets/` 加长缓存，`index.html` 不缓存
- [ ] **Step 1: 改 nginx 与 compose**：nginx 服务加卷 `./web:/srv/web:ro`。
- [ ] **Step 2: 改 `deploy.ps1`**：git archive 之前在 `web/` 跑 `npm ci` 与 `npm run build`（失败即停）；把 `web/dist` 内容追加进上传包的 `deploy/web/`（例如先解包到临时目录再重新打包，或用 `tar -rf` 以 `deploy/web` 前缀追加）；远端清理逻辑已会删除不在上传包里的旧文件，保留 `.env`。`web/` 有未提交改动时同样警告。
- [ ] **Step 3: 部署并检查**：`powershell -NoProfile -ExecutionPolicy Bypass -File deploy\deploy.ps1`；`http://42.194.206.186/` 返回网页 `index.html`，`/healthz` 返回 `{"ok":true}`，`/api/me` 无凭证返回 401，刷新 `/a/1` 这类前端路由不 404。
- [ ] **Step 4: 提交** `feat(deploy): serve the web admin from nginx`

## 二、小程序（任务 4）

### Task 4: 「确认登录网页版」页

**Files:**
- Create: `miniprogram/src/lib/webLogin.ts`、`miniprogram/src/pages/web-login/index.tsx`、`miniprogram/src/pages/web-login/index.config.ts`（标题「登录网页版」）、`miniprogram/src/pages/web-login/index.scss`
- Modify: `miniprogram/src/app.config.ts`（加页面）
- Test: `miniprogram/tests/webLogin.test.ts`

**Interfaces:**
- Consumes: `request` / `ApiError`（`src/lib/api.ts`）、`errorText`（`src/lib/messages.ts`）、任务 2 的 `:scan` / `:confirm` / `:cancel`
- Produces:
  - `ticketFromScene(scene: string | undefined): string | null`（`decodeURIComponent`，只接受 `[A-Za-z0-9_-]{16}`）
  - `scanTicket(ticket): Promise<{ pair_code: string }>`、`confirmTicket(ticket): Promise<void>`、`cancelTicket(ticket): Promise<void>`
  - `webLoginErrorText(e: unknown): string`：410 →「二维码已过期，请在电脑上刷新」；409 →「这个二维码已经被使用，请在电脑上刷新」；其余 `errorText`
- 页面：打开即 `scanTicket`，大字显示配对数字 + 「请核对电脑屏幕上的数字一致后再确认」+「确认登录」「取消」；确认后「已登录网页版，可以回到电脑上了」；取消后「已取消」；从首页进入（没有 scene）显示「请用微信扫电脑上的二维码」。
- [ ] **Step 1: 写失败的测试**：`ticketFromScene decodes and validates`、`webLoginErrorText maps 410 and 409`、`scan/confirm/cancel call the right endpoints`（mock `request`）
- [ ] **Step 2: 运行确认失败**：`npx vitest run tests/webLogin.test.ts`
- [ ] **Step 3: 实现 lib 与页面**（沿用温暖纸本样式，rpx）
- [ ] **Step 4: 全量 vitest 通过；`npm run build:weapp` 成功；提交** `feat(miniprogram): confirm web admin login page`

## 三、网页（任务 5–8）

### Task 5: 网页骨架、接口与扫码登录页

**Files:**
- Create: `web/package.json`、`web/vite.config.ts`（开发代理 `/api` → `http://127.0.0.1:8000`；Vitest `environment: 'jsdom'`）、`web/tsconfig.json`、`web/index.html`（`<title>红笔君</title>`）、`web/src/main.tsx`、`web/src/App.tsx`（路由）、`web/src/theme.css`、`web/src/lib/api.ts`、`web/src/lib/auth.ts`、`web/src/lib/login.ts`、`web/src/pages/Login.tsx`、`web/.gitignore`（`node_modules`、`dist`）
- Test: `web/tests/api.test.ts`、`web/tests/login.test.ts`

**Interfaces:**
- Produces:
  - `auth.ts`：`getToken(): string | null`、`setToken(t: string)`、`clearToken()`（`localStorage` 键 `hbj_token`，读写包 try/catch）
  - `api.ts`：`class ApiError(status: number, detail: string)`；`request<T>(method, path, body?): Promise<T>`（带 `Authorization: Bearer`；401 → `clearToken()` 并调用注册的 `onUnauthorized` 回调，抛 `ApiError(401)`）；`setOnUnauthorized(fn: () => void)`；`errorText(e): string`（网络错误 →「网络不太好，请稍后再试」；有中文 `detail` 用它；其余「出了点问题，请稍后再试」）
  - `login.ts`：`createTicket(): Promise<Ticket>`（`Ticket = { ticket, poll_key, pair_code, qr_png, expires_in }`）；`pollOnce(t: Ticket): Promise<PollResult>`；`startPolling(t: Ticket, onState: (s: 'pending' | 'scanned' | 'expired' | 'cancelled') => void, onToken: (token: string) => void, intervalMs = 2000): () => void`（返回停止函数；拿到 token 或终态后自动停）
  - 路由：`/login`、`/`（班级与作业，任务 6）、`/a/:assignmentId`（总览，任务 6）、`/a/:assignmentId/q/:questionNo`（投影，任务 7）、`/a/:assignmentId/downloads`（下载，任务 8）；没有 token 时除 `/login` 都跳 `/login`，登录后回到原来要去的地址
  - 登录页：小程序码图片（`data:image/png;base64,`）+ 配对数字（大字）+ 文案；`scanned` 时显示「已扫码，请在手机上确认」；`expired` / `cancelled` 时显示「二维码已过期，点击刷新」，点击重建票据；429/503 显示后端文案
  - 页头组件（之后各页共用）：「红笔君」+ 老师署名 +「退出登录」（`clearToken()` 回 `/login`）
- [ ] **Step 1: 写失败的测试**：`test_401_clears_token_and_redirects`（`request` 收到 401 → token 清掉、回调被调）、`errorText maps network and detail`、`startPolling stops after token`、`startPolling reports scanned then expired and stops`（用 fake timers 与 mock fetch）
- [ ] **Step 2: 运行确认失败**：在 `web/` 下 `npx vitest run`
- [ ] **Step 3: 实现**
- [ ] **Step 4: 本地联调**：本机 `.env` 临时加 `DEV_LOGIN=true` 起后端，`npm run dev` 打开网页；确认登录页能拿到真实小程序码（扫码需体验版，留到任务 9）。另在登录页加一个只在 `import.meta.env.DEV` 下显示的「开发者登录」按钮调用 `/api/auth/dev-login`。
- [ ] **Step 5: `npm run build` 成功；提交** `feat(web): scaffold, API client and QR login page`

### Task 6: 班级与作业、作业总览

**Files:**
- Create: `web/src/pages/Home.tsx`、`web/src/pages/Overview.tsx`、`web/src/lib/overview.ts`
- Test: `web/tests/overview.test.ts`

**Interfaces:**
- Consumes: `GET /api/classes`、`GET /api/classes/{id}/assignments`、`GET /api/assignments/{id}`、`GET /api/assignments/{id}/analytics`（字段见 `backend/app/analytics/stats.py` 的 `AssignmentStats` / `QuestionStat`）
- Produces:
  - `errorRate(q: { wrong_count: number; student_count: number }): number | null`（`student_count = 0` → null）
  - `heatLevel(rate: number | null): 'hot' | 'warm' | 'cool' | 'none'`（≥ 0.4 / ≥ 0.2 / 其余 / null）
  - `pendingHint(pending: number): string | null`（0 → null，否则全局约束里的文案）
- 首页：左侧班级列表（选中高亮），右侧该班作业（标题、学科、日期，新的在前），点作业进 `/a/:id`；没有班级时「还没有班级，请先在小程序里建班」。
- 总览：页头「班级 · 学科 · 作业名 · 日期」；全班人数、平均分、及格率；`pendingHint`；题目格子网格（题号 + 百分比，主观题加「主观」小标），点格子进投影页；一个「下载打印」按钮进下载页。**本页不放下载按钮**。
- [ ] **Step 1: 写失败的测试**：`errorRate handles zero`、`heatLevel thresholds 0.4 and 0.2`、`pendingHint`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**（数字与小程序学情页一致：同一接口同一字段）
- [ ] **Step 4: 全量 vitest 通过；提交** `feat(web): class picker and assignment overview`

### Task 7: 题目投影页

**Files:**
- Create: `web/src/pages/Question.tsx`、`web/src/lib/question.ts`、`web/src/components/Lightbox.tsx`
- Test: `web/tests/question.test.ts`、`web/tests/QuestionPage.test.tsx`

**Interfaces:**
- Consumes: `GET /api/assignments/{id}/analytics/questions/{no}`（`groups[].students[].submission_id`、`crops[].submission_id` / `crop_url`）、`POST .../causes`（`{causes: {[group.key]: string}}`）、总览接口的题号顺序（上一题 / 下一题）
- Produces:
  - `cropsByGroup(groups, crops): Map<string, string[]>`（按 `submission_id` 把 `crop_url` 挂到组 `key`；不属于任何组的图丢弃；保持接口顺序）
  - `neighbors(order: string[], current: string): { prev: string | null; next: string | null }`
- 页面：大字「第 N 题　错了 X 人（Y%）」+ 进度条；正确答案、知识点；客观题按组列出「写成 {answer}，{count} 人」+ 该组前 3 张原图（多于 3 张显示「还有 N 张」，点开展开）+ AI 错因（页面加载后请求一次，失败静默）；主观题显示 `score_buckets` 和原图；点图用 `Lightbox` 全屏放大，Esc 关闭；「上一题 / 下一题」按钮与键盘 ←/→；「全屏」按钮（`document.documentElement.requestFullscreen()`）；「返回总览」。**不渲染 `student_name`**（也不放进 `title` / `alt`）。
- [ ] **Step 1: 写失败的测试**：`cropsByGroup matches by submission_id and drops strays`、`neighbors at both ends`、`question page never renders student names`（渲染带姓名「张三」「李四」的接口数据，断言 `document.body.textContent` 与所有属性都不含这两个名字）、`arrow keys navigate`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**（按全局约束的投影仪字号）
- [ ] **Step 4: 手动检查**：浏览器窗口调到 1024×768，用本地有数据的作业确认不滚动可见错误人数和前两组；截图写进报告（只截浏览器窗口）。
- [ ] **Step 5: 全量 vitest 通过；提交** `feat(web): question projection page`

### Task 8: 下载打印页

**Files:**
- Create: `web/src/pages/Downloads.tsx`、`web/src/lib/download.ts`
- Test: `web/tests/download.test.ts`

**Interfaces:**
- Consumes: `POST /api/assignments/{id}/exports`（`kind`：`lecture` / `class_students` / `practice`，`include_answers`）→ `{url, filename}`；`GET /api/assignments/{id}/practice`（404 或 `status != "done"` 视为没有）；`GET /api/me`、`PATCH /api/me`
- Produces:
  - `exportAndDownload(assignmentId: number, kind: 'lecture' | 'class_students' | 'practice', includeAnswers?: boolean): Promise<void>`：拿到签名链接后 `fetch` 成 Blob，用 `<a download={filename}>` 触发浏览器下载（不在页面里打开）
  - `needsSignature(me: { display_name: string | null }): boolean`
- 页面：三张卡片「讲评单」「全班错题单」「练习卷（附答案 / 不附答案）」；练习卷没有时按钮置灰并显示「练习卷请先在手机上生成」；第一次下载且没有署名时弹框填署名（`PATCH /api/me`）后继续下载；409 显示后端文案；下载中按钮显示「正在生成…」并防连点。
- [ ] **Step 1: 写失败的测试**：`exportAndDownload posts kind and include_answers then saves blob with filename`、`practice disabled when 404 or not done`、`needsSignature`
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 全量 vitest 通过；提交** `feat(web): download and print page`

然后执行 **任务 3**（部署网页）。

## 四、联调与验收（任务 9）

### Task 9: 体验版与端到端验收

**Files:**
- Create: `docs/benchmark/m6-acceptance.md`（按设计文档第 8 节逐条列出，结果栏留给真机）
- 小程序体验版版本号 `0.2.0`

- [ ] **Step 1: 部署后端 + 网页**（任务 3 的部署脚本）
- [ ] **Step 2: 小程序体验版**：`npx taro build --type weapp --mode staging`，用开发者工具 CLI `upload -v 0.2.0 -d "网页版扫码登录"` 上传；之后恢复本地开发构建 `npm run dev:weapp`。在公众平台把 0.2.0 设为体验版需要产品负责人操作，写进报告。
- [ ] **Step 3: 服务器冒烟（自动部分）**：`POST http://42.194.206.186/api/web-login/tickets` 返回小程序码；不带 `poll_key` 查询 404；网页首页能打开。
- [ ] **Step 4: 写验收文档并提交** `docs: M6 acceptance checklist`；需要手机扫码的条目标注「待产品负责人真机」。
