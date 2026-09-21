# TODOS — combination 后续改进

来源：合并评审（/plan-eng-review）决策 D3 延后项 + 外部独立意见。

## P1（安全/多用户，尽快）

- [x] **Agent 项目用户隔离**（2026-09-17 完成）：`project_owners` 归属表 +
      全部 38 个 `/agent/*` 路由 JWT 鉴权（`app/services/agent_auth.py`）；
      聊天列表、删除、续写均校验归属，跨用户 403；存量 155 线程已迁移划归 admin
      （`tools/migrate_project_owners.py`）；前端 localStorage 项目 key 按用户分键、
      新建项目 ID 用 UUID 防碰撞。测试：`tests/test_agent_auth.py`（含 guard 测试）。
- [x] **Agent 服务鉴权**（2026-09-17 部分完成）：`/api/agent/**` 已验 UM JWT
      （HS256 共享密钥，`UM_JWT_SECRET` 环境变量可覆盖，Spring 侧同步占位化）。
      剩余：非 agent 端点仍未鉴权（见 P3 边界说明）；`run.py` 仍绑 `0.0.0.0`
      （用户决策维持，若仅本机使用建议改绑 `127.0.0.1`）。

## P2（体验）

- [ ] 嵌入模式折叠 Agent 内侧栏（UM 230px + Agent 300px 双侧栏，窄屏对话区不足）。
- [ ] `/api/health` 深度化：附带 Ollama ping / vector store 状态，前端横幅区分
      "服务未启动"与"模型未就绪"（现状为静态桩，README 已知限制 #3）。
- [ ] review.html / kb.html 的 Vue 移植与深度集成（现为新标签页直达原版页面；
      用户隔离改造已就地给两页加 token-relay.js 接线，属副本分叉）。
- [ ] Agent 生成的文档回流到体系文档管理库（documents 模块）。
- [ ] **token 过期的完整前端处置**：UM 前端 axios 拦截器统一处理 401 → 清登录态并
      跳转登录页（现状：Agent 视图对 401 仅显示红色横幅提示重登，SPA 其他模块各自
      报错；UM token 24h 过期且无刷新机制，`app.js` restoreSession 无条件信任存量
      token）。

## P3（边界说明 / 远期）

- [ ] **用户隔离边界**（明确记录，防误判"全部已隔离"）：当前隔离仅覆盖
      `/api/agent/**`（对话历史/项目/附件/模板/下载）。`/api/kb/*`（知识库文件与
      检索）、`/api/generate`、`/api/upload` 等非 agent 端点对所有调用方开放——
      知识库为团队共享语料属有意设计；若未来需按部门/角色隔离知识库，需在
      UM 侧引入资源权限模型后再扩展 `agent_auth` 的依赖体系。
      **2026-09-20 源同步新增同边界项**：`skill_library`（用户技能库，跨项目/跨会话
      共享的指导命令与生成规则，JSON 持久化）在多用户环境下为**全员共享**（用户
      决策维持共享）；若需按用户隔离，存储需加 owner 字段并经 agent_auth 过滤。
