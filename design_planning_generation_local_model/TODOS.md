# TODOS

## SQL Agent 集成（2026-08-11 /plan-eng-review）

- [ ] **种子数据扩充与版本维护** — 初始种子从现有领域文档/KB 提炼。后续从更多真实法规（GB 9706 系列、ISO 10993、IEC 60601-2-24 等）、材料标准、关键参数来源扩充领域库种子数据；维护 `seed_version` 元数据行支持增量更新，避免 seed-once 服务过期数据。
  - Why: 结构化 SQL 库数据过期会比 RAG 更具误导性（看似权威实则错误）。
  - 入口: `app/services/sql_db.py` 的 `init_db()` / 种子数据定义。

- [ ] **前端 SQL 查询结果专用展示** — 实现后检查 SSE 通用 `on_tool_end` 处理器对 SQL 工具结果的展示是否够用；若不足，为 SQL 查询结果加专用展示块（SQL 语句 + 返回行数/表格）。
  - Why: 让用户直观看到 agent 是如何查库得出结论的。
  - 入口: `app/static/agent.html` 的 SSE 事件处理。
