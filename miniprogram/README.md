# AI 错题本 · 老师端小程序（M3）

Taro 4 + React + TypeScript。接口基地址来自环境变量 `TARO_APP_API_BASE`。

## 一、准备

- Node 18+（开发时用 v24）、npm
- 微信开发者工具
- 本机 MySQL（库名见 `backend/.env` 的 `DATABASE_URL`）
- Redis（仅 Worker 和上传入队需要，见下）
- Python 3.11+ 虚拟环境：`backend/.venv`

## 二、启动后端

在 `backend/` 目录：

```powershell
cd backend
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`backend/.env` 常用项（均有默认值，见 `app/config.py`）：

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | `mysql+aiomysql://用户:密码@localhost:3306/库名` |
| `REDIS_URL` | 有密码时写 `redis://:密码@127.0.0.1:6379/0`（用 `127.0.0.1`，不要用 `localhost`：Windows 上 `localhost` 可能先走 IPv6 导致连接超时） |
| `WX_APPID` / `WX_SECRET` | 登录用，见第四节 |
| `JWT_SECRET` | 本地可用默认值 |
| `DASHSCOPE_API_KEY` | 真实批改用的通义千问 key（百炼控制台 → API Key） |
| `QWEN_BASE_URL` | 百炼业务空间 key（`sk-ws-` 开头）必须填业务空间专属地址，即控制台"按量付费 Base URL"：`https://ws-<id>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` |
| `STORAGE_DIR` | 图片存放目录，默认 `storage` |

健康检查：浏览器打开 `http://127.0.0.1:8000/healthz` 应返回 `{"ok":true}`。

## 三、启动 Worker（批改任务）

```powershell
cd backend
$env:REDIS_URL = "redis://:密码@127.0.0.1:6379/0"   # 或写进 .env
.venv\Scripts\python -m arq app.jobs.worker.WorkerSettings
```

Worker 需要可连接的 Redis、`DASHSCOPE_API_KEY` 和 `QWEN_BASE_URL`（默认模型 `qwen:qwen3-vl-plus`；百炼业务空间里没有 `qwen-vl-max`）。API 上传时也会往 Redis 入队，Redis 连不上时上传返回"已收到，稍后会自动开始批改"（503 提示）。

### 没有 Worker / 没有 Redis 时怎么做界面测试

后端的 `FakeModel`（`app/ai/fake.py`）只是测试替身：按顺序回放预设 JSON，没有接到 Worker 或任何配置项，**不能在手动运行时直接启用**，也没有现成的假批改脚本。可选做法：

1. 先验证不依赖批改的页面：登录、建班、导入名单、新建作业、拍照上传（Redis 不可用时会走 503 提示）、答案卷识别需要模型。
2. 要看复核页和成绩页，需有已批完的数据：用真实 key 起 Worker 批改，或直接改数据库（把页面状态改为 `done` 并补 submission / question_result 行）。
3. 后端 pytest 已覆盖这些流程，不需要 Redis。

## 四、登录与 AppID

- `miniprogram/project.config.json` 里的 `appid` 目前是 `touristappid`（游客模式）。拿到正式 AppID 或测试号后，改这个字段，或在开发者工具"详情 → 基本设置"里改。
- 后端登录 `POST /api/auth/wx-login` 会用 `WX_APPID` / `WX_SECRET` 向微信换 openid。游客 AppID 无法换到有效 openid，所以**要真实走通登录，必须在 `backend/.env` 配与小程序一致的 `WX_APPID` 和 `WX_SECRET`（可用微信公众平台的测试号）**。

## 五、运行小程序

```powershell
cd miniprogram
npm install
npm run dev:weapp      # 监听编译，产物在 dist/
```

1. 微信开发者工具 → 导入项目 → 目录选 `miniprogram/`（`project.config.json` 的 `miniprogramRoot` 指向 `dist/`）。
2. 详情 → 本地设置 → 勾选"不校验合法域名、web-view、TLS 版本以及 HTTPS 证书"。
3. 接口基地址：
   - `.env.development`：`TARO_APP_API_BASE=http://127.0.0.1:8000`（`dev:weapp` 使用）
   - `.env.production`：`TARO_APP_API_BASE=https://api.example.com`（正式构建前改成真实域名，需 HTTPS 与备案，属 M7）
4. 真机预览：把 `.env.development` 改成电脑的局域网 IP（如 `http://192.168.1.5:8000`），后端用 `--host 0.0.0.0`，手机开启调试模式。改完要重新编译。

一次性构建：`npm run build:weapp`。

## 六、测试

```powershell
cd miniprogram
npx vitest run          # 单元测试（只测 src/lib）
npx tsc --noEmit        # 类型检查
npm run build:weapp     # 构建

cd ..\backend
.venv\Scripts\python -m pytest -q    # 后端测试，需要本地 MySQL 测试库（git 忽略的 backend/.env.test）；不需要 Redis
```

页面层没有自动化测试，按 `docs/benchmark/m3-acceptance.md` 在开发者工具里手动验收。
