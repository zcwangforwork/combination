# TODOS — combination 后续改进

来源：合并评审（/plan-eng-review）决策 D3 延后项 + 外部独立意见。

## P1（安全/多用户，尽快）

- [ ] **Agent 项目用户隔离**：project_store 增加 `owner` 字段（登录用户名/ID），
      `/api/agent/projects` 按当前用户过滤；聊天列表、删除、续写均校验归属。
      现状：所有体系管理用户共享同一份项目列表，可互相删除/续写（README 已知限制 #2）。
- [ ] **Agent 服务鉴权**：FastAPI 侧校验体系管理的 JWT（网关转发或共享密钥），
      或至少绑定 `127.0.0.1` 限制局域网直连。
      现状：`run.py` 绑定 `0.0.0.0` 且无鉴权（用户决策维持现状，README 已知限制 #1）。

## P2（体验）

- [ ] 嵌入模式折叠 Agent 内侧栏（UM 230px + Agent 300px 双侧栏，窄屏对话区不足）。
- [ ] `/api/health` 深度化：附带 Ollama ping / vector store 状态，前端横幅区分
      "服务未启动"与"模型未就绪"（现状为静态桩，README 已知限制 #3）。
- [ ] review.html / kb.html 的 Vue 移植与深度集成（现为新标签页直达原版页面）。
- [ ] Agent 生成的文档回流到体系文档管理库（documents 模块）。
