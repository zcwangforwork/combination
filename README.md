# combination — 体系文档管理系统 + 设计开发文档写作 Agent

合并产物：在体系文档管理系统（user_management）登录后的侧边栏新增 **「AI 文档写作」** 入口，
点击进入设计开发文档写作 Agent 的完整对话页面（原 agent.html 全部功能，忠实移植）。

- 生成时间：2026-09-16
- 来源项目（复制时**零改动**；用户隔离改造后，Agent 侧后端与 review/kb 两页已在副本内演进）：
  - `../design_plan_generation_local_model/design_planning_generation_local_model`（Agent 项目）
  - `../user_management`（体系文档管理系统）
- 评审流程：/plan-eng-review（含外部独立意见 10 条，2 条阻断级问题已修复）

## 架构

```
浏览器 http://localhost:3000 (npx http-server)
└─ Vue SPA (index.html)
   ├─ :8080 Spring Boot        体系管理后端（签发 JWT，密钥可经 UM_JWT_SECRET 覆盖）
   └─ 「AI 文档写作」视图 (#agent-root[v-pre])
      ├─ css/agent-chat.css    原样式命名空间化 + SPA 泄漏防护
      ├─ js/agent-chat.js      原对话引擎 IIFE 封装 + AGENT_BASE 前缀
      │                        + [PORT-AUTH] fetch 注入 Bearer JWT / 按用户分键
      │                        / UUID 项目 ID / 认证下载 / #jwt= 页面凭证中转
      └─ 运行时探测 :8002→:8003→:8004
         FastAPI Agent 服务 (+CORSMiddleware)
         ├─ /api/agent/** 全端点 JWT 鉴权（HS256 共享密钥验签，sub=用户名）
         │   └─ project_owners 表：项目归属，首写登记、跨用户 403、列表按用户过滤
         ├─ :11435 Ollama (qwen3.5:122b)
         ├─ project_store/     运行时检查点（4.1GB，随副本复制）
         └─ chroma_db_insulin_pump/  知识库向量库（368MB）
```

## 启动步骤

前置依赖：PostgreSQL（体系管理库）、Ollama 运行于 `:11435` 且已拉取 `qwen3.5:122b`、
conda `env_01`、Node.js（http-server）、Maven。

方式一（一键三窗口）：

```
combination\start_all.bat
```

方式二（分步）：

```
# 1. 体系管理后端 (:8080)
cd user_management\backend && mvn spring-boot:run

# 2. 体系管理前端 (:3000，不要用 file:// 打开)
cd user_management\frontend && npx http-server -p 3000

# 3. Agent 服务 (:8002，被占自动回退 8003/8004；前端会自动探测)
cd design_planning_generation_local_model
conda activate env_01 && python run.py

# 4.（一次性）存量项目归属迁移：把历史无主对话线程划归 admin
cd .. && python tools/migrate_project_owners.py admin
```

可选：设置环境变量 `UM_JWT_SECRET`（Spring 与 FastAPI 两服务同时生效，默认回退
内置密钥）以轮换 JWT 密钥；轮换后所有存量登录态失效，需重新登录。

访问 `http://localhost:3000`，登录后点击侧边栏「AI 文档写作」。

账号（体系管理）：admin/admin123、zhangsan/123456 等（同原项目 README）。

**验收**：启动后请按 `SMOKE-TEST.md` 逐项检查（约 10 分钟）。

## 移植说明（开发者）

所有移植产物由脚本生成，**勿手改生成文件**，改源头后重跑：

| 产物 | 生成方式 |
|------|---------|
| `user_management/frontend/css/agent-chat.css` | `tools/build_agent_port.py`（提取 agent.html 样式 → `#agent-root` 命名空间化，@keyframes 加 `ag-` 前缀，与 UM style.css 类名交集的 UM 独有属性发射 unset 守卫） |
| `user_management/frontend/js/agent-chat.js` | 同上脚本（提取 agent.html `<script>` → IIFE + 55 个内联 handler 函数导出到 window + 47 处 URL 加 AGENT_BASE + localStorage 项目持久化 + **[PORT-AUTH] 用户隔离变换**：fetch 包装注入 `Authorization: Bearer <UM JWT>`、401 横幅、localStorage 项目 key 按用户名分键、新建项目 ID 用 `crypto.randomUUID()` 防跨用户碰撞、5 处 `window.open` 下载改 `_agentDownload`（fetch→blob→a.click，凭证不进 URL）、review/kb 页 URL 附加 `#jwt=` 片段） |
| `user_management/frontend/agent-view-fragment.html` | 同上脚本（body HTML 包进 `v-show` 视图 + `#agent-root[v-pre]`） |
| index.html / app.js / main.py 的接线 | `tools/wire_spa.py`（幂等，9 处插入） |

用户隔离（后端，非生成产物，直接源码）：

| 文件 | 说明 |
|------|------|
| `app/services/agent_auth.py` | JWT 验签（PyJWT HS256，`UM_JWT_SECRET` 环境变量）+ `project_owners` 归属表 + `require_user` / `require_project_access` 两个 FastAPI 依赖（首写登记归属、跨用户 403） |
| `app/api/routes.py` | 全部 38 个 `/agent/*` 路由挂鉴权依赖；`GET /agent/projects` 按当前用户过滤 |
| `app/static/token-relay.js`（新） | review/kb 新标签页的凭证中转：读 URL `#jwt=` → sessionStorage → 包装 fetch 注入头（**就地修改了 review.html / kb.html 两页 `<head>`，属副本分叉**，见已知限制 #5） |
| `tools/migrate_project_owners.py` | 存量迁移：无主线程一次性划归 admin（幂等，可重跑） |
| `tests/test_agent_auth.py` | 鉴权/归属/迁移测试 + guard 测试（扫描全部 agent 路由必须挂鉴权依赖，防新端点漏锁） |

`v-pre` 的作用：Vue 编译器完全跳过 agent 子树——内联 `onclick="fn()"` 保持原生全局解析，
原生 JS 的 DOM 修改不会被 Vue 补丁回滚。

## 已知限制（评审决策 D3/D4 + 外部意见）

1. **Agent 服务鉴权范围有限**：`/api/agent/**` 已全部 JWT 鉴权（用户隔离，见上），
   但 `/api/kb/*`、`/api/generate` 等**非 agent 端点仍无鉴权**（共享资源，边界见
   TODOS P3）；且 `run.py` 仍绑定 `0.0.0.0`（维持原项目行为，用户决策）——局域网内
   机器可直接访问这些未鉴权接口。CORS 只是浏览器约束，不是访问控制。若仅本机使用，
   建议改绑 `127.0.0.1`（run.py 一行）。**共享密钥仍是仓库内默认值**：生产部署务必
   设置 `UM_JWT_SECRET` 环境变量轮换。
2. ~~**多用户共享 Agent 项目列表**~~ **已解决（用户隔离）**：全部 `/api/agent/**` 端点
   验 JWT 并按 `project_owners` 归属校验；列表按登录用户过滤，跨用户读/删/续写返回
   403；同浏览器多账号的项目持久化分键。存量项目已迁移划归 admin。token 过期的
   完整前端处置（自动跳登录）见 TODOS P2。
3. **`/api/health` 是静态桩**：前端端口探测只确认 FastAPI 进程存活，不代表 Ollama 就绪。
   Ollama 未启动时的表现为逐条消息失败（非顶部横幅）。
4. **全屏模式**：「AI 文档写作」以全屏浮层呈现（覆盖 UM 头部与侧边栏，还原原 agent.html
   独立页的完整可用宽度）；点击 Agent 工具栏首项「⟵ 返回系统」回到管理系统。
5. **副本分叉**：两个原目录后续更新不会自动同步到本目录；反向亦然。
   用户隔离改造在副本内**就地修改**了 `app/static/agent.html`、`review.html`、
   `kb.html`（各加 token-relay.js 引用；agent.html 加了 3 行，生成脚本行号常量已
   同步 +3）与后端源码——从源头同步这些文件时需重做该接线。
6. **项目持久化语义变化**：原版用 URL `?project=` 恢复会话；移植版用 localStorage——
   同一浏览器刷新/重登后自动恢复最后一次的项目（跨浏览器/隐身模式不共享）。
7. 强依赖本地 Ollama(:11435) + PostgreSQL + ChromaDB 就绪；模板/知识库页（`/kb`、
   `/agent/review/`）以新标签页打开原版页面，未做 Vue 移植（评审决策，功能完整可用）。
