# Web UI 第一版

Mode: Operate. 用户已要求直接生成一版再看，采用代码优先预览，不重复进行方向确认。

## Direction contract
THESIS: 老师工作台。按班级找到作业，再由错误分布进入讲评，信息优先于装饰。
OWN-WORLD: 纸白、清晰墨色、朱红选中与品牌；统一无衬线中文，数据等宽数字，边界细而明确。签名细节是品牌笔尖与当前页的红色下划线。
STORY: 左侧选班，右侧搜索筛选作业；进入学情先看覆盖人数，再看错误率与知识点；单题讲评与打印有明确返回路径。
FIRST VIEWPORT: 1440px 桌面，72px 顶栏，224px 班级栏，内容区最大 1200px。标题 30px，正文 15–16px，列表行高约 96px。学情页三项简洁数据及题目热力矩阵，所有颜色有数字标签。375px 时班级栏转横向选择，操作可换行。
FORM: 用户指定的纸白墨色朱红方向优先；seed:b54b3cbcd7d3fd24。参考候选只用于密度与可读性，不用随机风格覆盖用户接受的方向。
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## 红笔君识别细节（2026-10-23 增补，产品负责人确认）

在第一版布局之上加四处，让它像「老师拿红笔批改」而不是通用后台模板：

1. **标题用宋体**：页面标题、题号、大数字（统计值、错误人数）用 `--serif: "Source Han Serif SC", "Noto Serif SC", "Songti SC", "STSong", "SimSun", serif`（只用系统字体，不下载网页字体），字重 700–900、墨色；正文、表格、按钮保持无衬线。
2. **红笔笔迹（只用在关键处）**：
   - 学情格子里错误率最高的那一题（及所有 ≥ 40% 的题）不再整块涂红，改为浅底 + **手绘红圈**（SVG 路径，略不闭合、粗细 2–3px），数字用朱红；
   - 需要老师注意的数字或提示（待复核数、失败页数）下面一道**红色波浪线**（`text-decoration: underline wavy` 或 SVG）；
   - 当前导航项的红色下划线保留。全站红色笔迹每屏不超过 3 处。
3. **标志是朱红方印**：页头左上角用 `web/public/brand/seal-64.png`（32px 显示，2 倍图）＋「红笔君」宋体字；浏览器标签图标用同一印章（`seal-64.png`）。原笔尖图标不再作为品牌标志。小程序头像为 `docs/brand/avatar-1024.png`（由 `docs/brand/make_seal.py` 生成，字体思源宋体 Heavy，SIL OFL 可商用）。
4. **纸面感**：卡片圆角不超过 6px、去掉投影，用 1px 细线分隔；表格行用细横线，像纸上的表格。

不做：纸纹背景图、满屏手写字体、吉祥物。

## Preview boundary
仅开发入口 preview.html 使用示例数据，复用真实页面组件，独立 MemoryRouter，不存登录凭证，不向真实 API 发送请求。生产入口维持现有登录与 API。
