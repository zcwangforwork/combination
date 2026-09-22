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

- [x] **知识库用户隔离**（2026-09-21 完成）：个人知识库（`chroma_db_users/<用户名>/`）
      + 共享胰岛素泵库双层作用域；普通用户 RAG 检索=本人库+共享库，ADMIN=全部库；
      `/api/kb/*` 全端点 JWT 鉴权（上传入个人库 / 删除仅本人 / ADMIN 跨库）；
      agent 工具（search_kb / find_kb_reference_files / add_kb_files_as_attachment /
      ingest_attachment_to_kb）经 kb_scope ContextVar 按请求作用域；
      存量共享 uploads 已迁移划归 admin。测试 `tests/test_kb_isolation.py`。
- [ ] **用户隔离边界**（明确记录，防误判"全部已隔离"）：当前隔离覆盖
      `/api/agent/**`（对话历史/项目/附件/模板/下载）与 `/api/kb/**`（知识库）。
      仍开放：`/api/generate`、`/api/upload`、`/api/extract-status` 等旧版表单端点；
      且 Agent 会话附件仍摄入共享库 uploads collection（附件本身有项目归属校验，
      但其向量内容经 search_attachment 全局可检——历史行为，待评估是否分库）。
      **2026-09-20 源同步新增同边界项**：`skill_library`（用户技能库）在多用户环境
      下为全员共享（用户决策维持）；若需按用户隔离，存储需加 owner 字段。
