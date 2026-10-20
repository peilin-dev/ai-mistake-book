# AI 智能错题本 设计文档

- 日期：2026-10-20
- 状态：决定已确认（第 1–16 项），实现细节中的「默认选型」见第 13 节待确认事项
- 来源：参考视频《多端通用：基于 Coze 搭建中小学智能错题本工作流》，经 grill-me 访谈逐项确定

---

## 1. 背景与目标

参考案例在 Coze 上搭建了「拍一张试卷 → AI 识别错题 → 错因分析 → 入库 → 生成报告」的工作流，面向家长/学生、单张照片、单人使用。

本产品在此基础上做成**正式上线、面向老师**的工具：老师拍全班**未批改**的卷子，AI 完成批改、归档错题、生成班级学情和个人错题本，并能生成举一反三练习、导出打印。

**成功标准（试用期）**
- 老师从首次打开到批出第一份卷子 ≤ 2 分钟。
- 一个 40 人班一次作业（单页卷）上传后 10 分钟内全部出结果。
- 客观题批改与老师复核结论一致率 ≥ 95%（以试用期复核数据统计）。

**不做（第一版）**：家长端、学生端、学校管理员、付费、Coze。

## 2. 已确认的决定

编号与访谈总结一致。总体路线：微信小程序 + 自建后端直接调用视觉大模型，不用 Coze。

| # | 主题 | 决定 |
|---|------|------|
| 1 | 定位与用户 | 正式上线，主要给老师用；学生端以后可能做（学校不允许学生用手机），不做家长端 |
| 2 | 账号组织 | 老师个人注册、自己建班，数据模型预留「学校」层级 |
| 3 | 主体 | 先个人主体体验版试用，正式发布前转企业主体 |
| 4 | 收费 | 试用期免费 + 每月限额 + 记录每次调用成本 |
| 5 | 录入方式 | 老师先建一次「作业/考试」，再拍**未批改**卷，每个学生可拍多页 |
| 6 | 标准答案 | 有答案卷则对照答案卷批改；没有则 AI 自己解题并标「未校验」 |
| 7 | 学生匹配 | 导入班级名单，AI 读卷头姓名匹配，匹配不上由老师选 |
| 8 | 学科与主观题 | 中小学全科；主观题 AI 全自动打分 |
| 9 | 人工复核 | 仅低置信度题需老师复核，老师随时可改 |
| 10 | 老师输出 | 班级学情分析、个人错题本与报告、举一反三练习、导出打印 |
| 11 | 知识点 | 按课标建通用固定知识点树，AI 只能从中归类 |
| 12 | 变式题 | 一家模型出题，另一家独立验算，不一致丢弃，老师勾选后导出 |
| 13 | 端与后端 | 小程序 + 网页后台；后端 Python FastAPI + MySQL |
| 14 | 大模型 | 模型适配层，先接通义千问（Qwen-VL）+ 豆包，实测后定主力 |
| 15 | 照片保存 | 只长期保存错题裁剪图；原图 30 天后自动删除；国内私有对象存储 |
| 16 | 登录与资料 | 微信一键登录不填资料；建班选年级、建作业选学科（记住上次学科）；首次导出时询问署名，可随时修改；网页后台用小程序扫码登录 |

## 3. 老师的核心流程

```
微信一键登录
  └─ 首页引导「先建一个班」：选年级 + 导入名单（粘贴文本 / 拍名单照片）
       └─ 新建作业：学科（默认上次）+ 标题 + 可选拍答案卷
            ├─ 若拍了答案卷：AI 提取每题答案 → 老师确认/修改
            └─ 连拍学生卷（每人可多页）
                 └─ 后台异步批改，列表实时显示进度
                      ├─ 自动通过的题直接入库
                      └─ 待复核（黄色）：低置信度 / 未校验答案 / 姓名未匹配
                           └─ 老师逐题点「对/错/改分」或选学生
  ├─ 班级学情：每题正确率、高频错题、薄弱知识点
  ├─ 个人错题本：某学生的错题历史、错因、薄弱知识点
  ├─ 举一反三：按错题/知识点生成变式题 → 双模型验算 → 老师勾选
  └─ 导出 PDF：班级错题集 / 个人错题本 / 练习卷（首次导出询问署名）
```

网页后台：扫码登录，提供与小程序相同的数据，但以大屏方式做学情查看、批量复核和导出。拍照只在小程序。

## 4. 系统架构

```
 微信小程序 ─┐                         ┌─ MySQL 8（业务数据）
            ├─ HTTPS ─ FastAPI API ───┼─ Redis（任务队列、扫码登录状态、限流）
 网页后台 ──┘          │               └─ 对象存储（私有读，原图/裁剪图/导出PDF）
                       │ 入队
                  批改 Worker（arq）── 模型适配层 ─┬─ 通义千问 Qwen-VL（DashScope）
                       │                          └─ 豆包视觉（火山方舟 Ark）
                  定时任务：原图 30 天清理、月度配额重置
```

- API 与 Worker 共用同一 Python 包，Worker 单独进程运行。
- 批改是异步的：上传只负责存图和入队，客户端轮询作业进度（第一版不做 WebSocket）。
- 模型调用一律经过适配层，业务代码不直接依赖某家 SDK；两家都走 OpenAI 兼容的 HTTP 接口。

## 5. 后端模块划分

| 模块 | 职责 |
|------|------|
| `auth` | 小程序 `code2session` 登录、JWT、网页扫码登录 |
| `classes` | 班级、学生名单导入与维护 |
| `assignments` | 作业、答案卷、页面上传、进度 |
| `grading` | 批改流水线：识别 → 判分 → 学生匹配 → 置信度 → 裁剪 → 入库 |
| `review` | 待复核队列、老师修正 |
| `knowledge` | 知识点树加载、按学科年级取候选 |
| `ai` | 模型适配层、用量记录 |
| `storage` | 对象存储抽象（本地/OSS） |
| `quota` | 月度限额与成本统计 |
| `analytics` | 班级学情、个人报告 |
| `practice` | 变式题生成与双模型验算 |
| `export` | PDF 导出 |
| `jobs` | Worker 任务与定时任务 |

## 6. 数据模型

所有表含 `id`（BIGINT 自增）、`created_at`、`updated_at`。

| 表 | 关键字段 | 说明 |
|----|----------|------|
| `schools` | name | 预留，第一版不使用 |
| `teachers` | unionid, mp_openid, display_name(可空), school_id(可空), last_subject(可空) | 用户主键用自有 id，不依赖 openid（转企业主体后 AppID 会变） |
| `classes` | teacher_id, name, grade(1–12) | 年级挂在班级上 |
| `students` | class_id, name, student_no(可空) | 同班同名允许，靠学号或老师选择区分 |
| `assignments` | class_id, subject, title, answer_key_status(none/pending/confirmed) | 学科挂在作业上 |
| `answer_items` | assignment_id, question_no, answer, max_score, is_subjective | 答案卷提取并经老师确认 |
| `pages` | assignment_id, seq, image_key, image_sha256, status(queued/processing/done/failed), fail_reason, student_id(可空), original_deleted_at | 一张照片一行；seq 为上传顺序 |
| `submissions` | assignment_id, student_id, total_score, needs_review_count | 一个学生一次作业的汇总（由多页合并） |
| `question_results` | submission_id, page_id, question_no, question_text, student_answer, correct_answer, answer_verified, is_correct, score, max_score, confidence, needs_review, reviewed, model_is_correct, model_score, error_reason, knowledge_point_id, crop_key | 错题与非错题都存，统计正确率需要全量；`model_*` 在老师修改时保存模型原值 |
| `knowledge_points` | subject, grade_band, parent_id, code, name | 课标知识点树 |
| `practice_items` | teacher_id, source_question_id, knowledge_point_id, stem, answer, verified, selected | 变式题 |
| `usage_records` | teacher_id, provider, model, purpose, input_tokens, output_tokens, cost_fen | 每次模型调用一行 |
| `exports` | teacher_id, kind, file_key, signature_name | 导出记录 |

学科枚举：`chinese, math, english, physics, chemistry, biology, history, geography, politics, science, other`。

## 7. 批改流水线

对每个 `page` 执行（Worker 任务 `grade_page(page_id)`）：

1. **取图**：读取原图，按 EXIF 方向校正，长边缩放到 ≤ 2048px。
2. **调用视觉模型**，要求输出严格 JSON（见下），提示词带上：学科、年级、该作业已确认的答案（若有）、该学科年级的知识点候选列表（id + 名称）。
3. **校验输出**：用 pydantic 校验；不合法则重试 1 次，仍失败则 `status=failed, fail_reason="model_output_invalid"`。识别不到任何题目则 `fail_reason="unreadable"`，提示老师重拍。
4. **学生匹配**（见 7.2）。
5. **判分**：有确认答案时以答案为准，`answer_verified=true`；无答案时采用模型自解答案，`answer_verified=false`。
6. **知识点校验**：模型返回的 `knowledge_point_id` 不在候选集合内则置空。
7. **置信度与复核**（见 7.3）。
8. **裁剪**：对 `is_correct=false` 的题按 `bbox` 裁剪存图，得到 `crop_key`。
9. **入库与汇总**：写 `question_results`，更新 `submissions` 总分与待复核数，记录 `usage_records`。

### 7.1 模型输出 JSON

```json
{
  "student_name": "张三",
  "questions": [
    {
      "no": "3",
      "question_text": "一个圆柱形水桶，底面半径 2dm，高 5dm……",
      "student_answer": "157dm³",
      "correct_answer": "62.8dm³",
      "is_subjective": false,
      "is_correct": false,
      "score": 0,
      "max_score": 4,
      "confidence": 0.92,
      "bbox": [0.08, 0.31, 0.92, 0.45],
      "knowledge_point_id": 1234,
      "error_reason": "把侧面积公式当成体积公式"
    }
  ]
}
```

`bbox` 为相对坐标 `[x1, y1, x2, y2]`，取值 0–1。

### 7.2 学生匹配

- 卷头姓名与班级名单**完全相等且唯一**：直接匹配。
- 否则做相似度匹配（字符相似度 ≥ 0.8 且唯一最高）：匹配并标记该页 `needs_review`。
- 同名多人、无匹配或未识别到姓名：
  - 若该页未识别到姓名，且同一作业中上一页（seq−1）已匹配学生，则视为同一学生的续页；
  - 其余情况 `student_id` 为空，进入待复核由老师选择。
- 同一学生的多页合并到同一 `submission`。

### 7.3 置信度与复核规则

一道题 `needs_review = true` 当且仅当满足任一条件：
- `confidence < 0.8`（阈值可配置）；
- `answer_verified = false`（AI 自解答案）；
- 所在页的学生未确定。

主观题不额外强制复核（决定 8），同样按上述规则处理。老师修正后 `reviewed=true`，以老师结果为准，并保留模型原值用于准确率统计。

## 8. 模型适配层

```python
class VisionModel(Protocol):
    name: str
    async def complete_json(self, prompt: str, images: list[bytes]) -> ModelResult: ...

@dataclass
class ModelResult:
    data: dict
    input_tokens: int
    output_tokens: int
    model: str
```

- 实现：`QwenVLModel`（DashScope 兼容模式）、`DoubaoVisionModel`（火山方舟）、`FakeModel`（测试）。
- 按用途配置主模型：`grading`、`answer_key`、`practice_generate`、`practice_verify`（验算必须与生成用不同厂商）。
- 选型方法：准备 ≥ 100 张真实卷子（覆盖各学科、手写潦草、拍歪），两家分别批改，比较一致率、耗时、单页成本，再定 `grading` 主力。

## 9. 知识点树

- 依据义务教育及普通高中课程标准，按 `学科 → 学段/年级 → 领域 → 知识点` 组织，不绑定教材版本；以后再加「教材章节 → 知识点」映射。
- 生成方式：先由 AI 按课标逐学科生成草稿，再分学科人工审核，以 YAML/CSV 维护在仓库 `data/knowledge/` 下，通过导入脚本写库。
- 批改时只把**该学科、该年级附近**的知识点作为候选传给模型，控制提示词长度。

## 10. 输出功能

- **班级学情**（按作业）：每题正确率、平均分、错误人数排名、薄弱知识点 Top N、待复核数。
- **个人错题本**：按时间/知识点列出错题（含裁剪图、学生答案、正确答案、错因），薄弱知识点统计，AI 生成的文字总结（Markdown）。
- **举一反三**：选错题或知识点 → 生成模型出 N 道变式题（含答案）→ 验算模型独立求解 → 答案一致的才 `verified=true` 显示给老师 → 老师勾选 → 进入练习卷。
- **导出 PDF**：班级错题集、个人错题本、练习卷（可选是否附答案）。首次导出时询问署名并保存到 `teachers.display_name`。

## 11. 账号与登录

- 小程序：`wx.login` 拿 code → 后端 `code2session` → 按 `unionid`（无则 `mp_openid`）查找或创建老师 → 返回 JWT（有效期 7 天，静默续期）。
- 网页后台：页面展示二维码（含一次性 `ticket`，Redis 存 5 分钟）→ 老师用小程序扫码确认 → 网页轮询拿到 JWT。
- 不收集手机号、头像、昵称；未设署名时界面统一显示「老师」。
- 数据隔离：老师只能访问自己的班级及其下所有数据，接口层统一校验归属。

## 12. 合规、安全、成本

- **个人主体阶段**：只发布体验版，邀请试用老师（≤ 100 人），不开通支付。转企业主体前完成 ICP 备案、教育类目资质、隐私政策与用户协议。
- **未成年人信息**：最小化收集（只有姓名、可选学号）；原图 30 天删除；裁剪图与导出文件私有读，经短时签名 URL 访问；老师可删除班级及其全部数据。
- **模型**：只用已备案的国内模型，数据不出境。
- **限额**：每位老师每月批改页数上限（默认 300 页，可配置）；超限返回明确提示。每次调用记录 token 与估算成本（分），后台可按老师和月份汇总，作为后续定价依据。

## 13. 待确认事项（采用默认值，可随时改）

以下在访谈中未单独确认，文档按默认值写，开发前可调整：

| 项 | 默认 |
|----|------|
| 小程序框架 | 原生小程序 + TypeScript |
| 网页后台框架 | Vue 3 + Vite + Element Plus |
| 任务队列 | arq（基于 Redis） |
| 对象存储 | 阿里云 OSS（与通义千问同云，内网传输） |
| 复核置信度阈值 | 0.8 |
| 每月免费限额 | 300 页/老师 |
| 进度更新方式 | 客户端轮询，间隔 3 秒 |

## 14. 主要风险

| 风险 | 应对 |
|------|------|
| 主观题全自动打分与老师判断偏差大 | 试用期统计主观题复核修改率；若修改率高，将主观题改为默认复核（只改 7.3 规则） |
| 一次作业多次上传同一张照片 | 按 `image_sha256` 在同一作业内去重，重复上传直接返回已有页面 |
| 个人主体审核与体验版人数限制 | 尽早准备企业主体；用户主键自有，迁移时按 unionid 关联 |
| 全科知识点树工作量大 | AI 生成草稿 + 分学科审核；先完成试用老师所教的学科 |
| 手写识别与拍照质量 | 拍照页加取景框与清晰度提示；`unreadable` 时提示重拍 |
| 模型成本超预期 | 用量记录 + 月度限额；按实测在两家间切换主力模型 |
