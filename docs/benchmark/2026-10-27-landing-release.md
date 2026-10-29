# 红笔君产品首页发布

- 日期：2026-10-27（Asia/Singapore）。
- 正式页面：http://42.194.206.186/welcome 。未登录根路径展示产品页；原有登录及工作台路由保持有效。
- UI UX Pro Max 规划，React 18 + Tailwind 3.4；包含主视觉、交互示例、功能卡片、流程、方案预览、FAQ。
- 价格与付费权益未发布，本次不加入支付。
- 发布来源：基于 HEAD db7d87c 的现有网页，加入首页、路由和 Tailwind 配置。使用 outputs/hongbijun-landing-release-20261027 隔离构建，排除本地未发布的答案卷删除及相关组件、样式修改。
- 验证：隔离发布包 TypeScript 与生产构建成功，28 个测试文件、119 项测试通过。
- 发布仅更新 nginx 静态文件；新资源先复制，index.html 原子替换，旧哈希资源保留。未修改数据库或重启批改服务。
- 备份：/home/ubuntu/mistake-book-web-releases/20261027-landing-133802/previous-web.tar.gz 。
- 入口 SHA-256：682324ff1d0d66960622f0695f519797224acce3dea565fcb5ccb6b702a807b8。
- 服务器健康检查通过；服务器实际入口与 JS/CSS 与发布包逐字节一致。外网校验输出见 outputs/hongbijun-landing-release-20261027/verification.json。
- 浏览器已打开正式站点并确认新版首页渲染。

如需回滚，将 previous-web.tar.gz 解压到 /home/ubuntu/mistake-book/deploy/web；目录为 nginx bind mount，不替换目录本身。新增哈希资源可保留，不影响旧入口。
