# Web UI 第一版

Mode: Operate. 用户已要求直接生成一版再看，采用代码优先预览，不重复进行方向确认。

## Direction contract
THESIS: 老师工作台。按班级找到作业，再由错误分布进入讲评，信息优先于装饰。
OWN-WORLD: 纸白、清晰墨色、朱红选中与品牌；统一无衬线中文，数据等宽数字，边界细而明确。签名细节是品牌笔尖与当前页的红色下划线。
STORY: 左侧选班，右侧搜索筛选作业；进入学情先看覆盖人数，再看错误率与知识点；单题讲评与打印有明确返回路径。
FIRST VIEWPORT: 1440px 桌面，72px 顶栏，224px 班级栏，内容区最大 1200px。标题 30px，正文 15–16px，列表行高约 96px。学情页三项简洁数据及题目热力矩阵，所有颜色有数字标签。375px 时班级栏转横向选择，操作可换行。
FORM: 用户指定的纸白墨色朱红方向优先；seed:b54b3cbcd7d3fd24。参考候选只用于密度与可读性，不用随机风格覆盖用户接受的方向。
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Preview boundary
仅开发入口 preview.html 使用示例数据，复用真实页面组件，独立 MemoryRouter，不存登录凭证，不向真实 API 发送请求。生产入口维持现有登录与 API。
