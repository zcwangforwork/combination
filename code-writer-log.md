# code-writer-log — combination 合并项目

（本文件覆盖 2026-09-16 合并调试回合；合并实施阶段的完整记录见
`E:\nrf_sample_codes\working_team_work\public\docs\code_writer_docs\session-2026-09-16-140852.md`）

## 2026-09-16 15:30 - 调试回合总结（用户报告：侧边栏看不到 AI 写作入口）

### 问题 1：3000 端口服务的是原目录，不是 combination 副本
- Command: `curl -s http://localhost:3000/index.html | md5sum` 等指纹比对（含 grep -c agent-chat）
- Purpose: 判定 http-server 实际根目录（用户两次清缓存重启后入口仍不显示）
- Result: 两次（含新 PID 25076）指纹均为原版 index.html MD5 `99bef056...`（agent-chat 出现 0 次、css/js 404）
  → 根因：http-server 启动目录仍是原 `user_management/frontend`，与缓存无关
- 处置: `taskkill //PID 25076 //F` 终止错目录实例；
  由我接管启动（后台任务 bm5a3wr7h）:
  `cd "E:/A_nrf_sample_codes/working_team_work/public/project/git_project/combination/user_management/frontend" && npx http-server -p 3000 -c-1`
- Result: Success — 指纹变为接线版 MD5 `95e6c173...`，agent-chat 出现 5 次，css/js 均 200

### 问题 2：Playwright E2E 发现移植层运行时崩溃（用户尚未走到这一步）
- Finding: 控制台 `TypeError: Cannot read properties of null (reading 'addEventListener') at agent-chat.js:1059 (setupDragDrop)`
- 分析: agent 视图位于登录 v-else 分支内，登录前 DOM 不存在；原脚本顶层 IIFE
  （setupDragDrop / setupInputDragDrop / kbFilesDialog 遮罩绑定）在脚本加载即执行 → null 崩溃，
  且顶层崩溃终止整个 IIFE，`window.AgentChat` 根本不会定义（入口点击也无反应）
- File Edited: `tools/build_agent_port.py`
  - 新增 3 组替换：iife_dragdrop_head/tail、iife_input_head/tail、kbmask_toplevel
    （顶层 IIFE/绑定 → 具名函数，由 `_doInit()` 首次调用）
  - 新增审计断言：禁止顶层 IIFE / 顶层 getElementById 立即绑定 / 顶层 window 操作残留
- Result: Success — 重建 18/18 替换计数均为 1，`node --check` 通过
- 顺带修复: `<MagicStick />` → `<magic-stick />`（in-DOM 模板小写化陷阱，PascalCase 不可解析）

### E2E 终验（Playwright，全部通过）
- 登录 admin/admin123 → 8080 API 200
- 菜单项「AI 文档写作」位于 商业成本 与 部门管理 之间，点击切换视图正常
- AGENT_BASE 探测 `:8002/api/health` → 200；CORS 生效：state/attachments/projects/templates/orphan/doc-types/history/stream 共 9 个 agent API 全部 200
- localStorage 项目持久化生效（徽标「项目: 已恢复会话」，恢复提示消息渲染）
- 当前页控制台 0 errors / 0 warnings；截图确认侧边栏/聊天区/输入区布局完整
- 注：全量控制台残留 1 条 TypeError 为修复前旧页面加载的记录（跨导航保留），与当前版本无关

### 待办移交
- 用户后续自启服务时，http-server 必须从 `combination/user_management/frontend` 启动（本次根因）
- SMOKE-TEST.md 12 步手动验收仍待用户执行
