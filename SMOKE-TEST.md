# SMOKE-TEST.md — 合并产物手动验收清单（约 10 分钟）

> 背景：本次合并按决策仅做静态验证（语法/审计/零改动检查已全部通过），运行时行为需要
> 由你启动服务后照单验收。每项打勾；任一项失败请记录现象（控制台 F12 报错截图最有用）。

## 0. 前置

- [ ] PostgreSQL 已运行，Ollama 已运行于 `:11435` 且模型 `qwen3.5:122b` 已拉取
- [ ] 运行 `combination\start_all.bat`（或按 README 分步启动三个服务）
- [ ] 三个窗口无报错；浏览器打开 `http://localhost:3000`

## 1. 登录与入口

- [ ] admin/admin123 登录成功，进入工作台
- [ ] 侧边栏「商业成本」之后出现 **「AI 文档写作」**（MagicStick 图标，所有角色可见）
- [ ] 点击后 **Agent 以全屏浮层铺满视口**（UM 头部与侧边栏被覆盖），出现 Agent 对话空状态
      （"👋 你好！我是设计开发文档写作助手"）
- [ ] Agent 工具栏首项有「⟵ 返回系统」按钮；点击后回到管理系统（默认切到工作台），
      再点「AI 文档写作」可重新全屏进入且会话状态保留
- [ ] **样式检查**：Agent 侧栏为白色 300px（不是深色 230px）、整体无双向滚动条、
      「新建聊天」按钮左对齐（右侧无泄漏的居中样式）

## 2. 服务探测（可选，破坏性场景）

- [ ] 停掉 Agent 服务窗口后点击菜单/点「重试连接」：出现红色横幅
      "⚠ 无法连接设计开发文档写作 Agent 服务"，SPA 其他功能不受影响
- [ ] 重启 Agent 服务 → 点横幅内「重试连接」→ 横幅消失、对话区可用

## 3. 对话核心（SSE 跨源）

- [ ] 输入一条消息发送：能看到流式打字输出（打字机效果），非一次性出现
- [ ] F12 Network：对 `:8002`（或 8003/8004）的 fetch 无 CORS 报错、无 404
- [ ] 生成中的「暂停」按钮可用；生成结束后恢复输入

## 4. 附件 / 模板 / 下载

- [ ] 上传一个附件（文件选择）：附件区出现条目，显示字符数
- [ ] 打开「模板管理」对话框：能新增/删除模板，无 JS 报错
- [ ] 对任一已生成文档点下载（docx）：新标签触发下载，URL 指向 `:8002`
- [ ] 「查看完整文档」链接指向 `:8002/agent/review/<project_id>` 且页面可打开
- [ ] 「知识库」按钮在新标签打开 `:8002/kb?project=...`

## 5. 流程图（mermaid 懒加载）

- [ ] 首次点「生成流程图」：Network 中此时才加载 mermaid.min.js，流程图正常渲染、可导出 PNG

## 6. 项目切换（移植最深的部分）

- [ ] 侧栏聊天列表出现当前项目；点「新建聊天」→ 对话区清空、徽标显示日期、
      顶部 review 链接更新为新项目（F12 检查 a.href 含新 project_id）
- [ ] 在旧项目里发过消息后：切回旧项目 → 显示"已切换聊天任务"，历史消息与步骤进度恢复
- [ ] **刷新页面（F5）** → 重新登录进「AI 文档写作」→ 自动恢复最后一次的项目
      （localStorage 语义，徽标显示"已恢复会话"）
- [ ] 删除当前项目 → 自动切换到新聊天；删除非当前项目 → 仅列表刷新

## 7. 登出中断

- [ ] Agent 回复流式输出进行中点击「退出登录」→ F12 Network 中该流被 aborted，
      回到登录页无报错；重新登录再进入可正常继续

## 8. 原项目隔离（合并未破坏源头）

- [ ] 原两个目录按原方式启动仍正常（本次合并零改动：MD5 已复核，可选抽查）

## 9. 用户隔离（对话历史按登录用户分隔）

前置：迁移脚本已执行（`python tools/migrate_project_owners.py admin`，存量 155 线程划归
admin）；两个不同浏览器（或普通+隐身窗口）分别准备 admin/admin123 与 zhangsan/123456。

- [ ] **强刷缓存**：Ctrl+F5 加载 SPA（旧缓存 agent-chat.js 无鉴权 shim，会全部 401）
- [ ] F12 Network：admin 会话中任一 `/api/agent/**` 请求头含
      `Authorization: Bearer eyJ...`，且无 401/403
- [ ] admin 新建聊天并发一条消息；**zhangsan 登录后聊天列表看不到 admin 的该项目**，
      反向同样互不可见
- [ ] zhangsan 浏览器 F12 控制台执行（模拟越权读，project_id 换成 admin 的）：
      `fetch('http://localhost:8002/api/agent/projects/<admin的项目id>/history',{headers:{Authorization:'Bearer '+JSON.parse(atob(localStorage.token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).sub&&localStorage.token}}).then(r=>r.status).then(console.log)`
      → 输出 **403**；无凭证访问同一 URL → **401**
- [ ] **同浏览器账号切换**：admin → 退出 → zhangsan 进入「AI 文档写作」：
      不恢复 admin 的当前项目（localStorage 按用户名分键），列表只见 zhangsan 自己的
- [ ] **下载**：对已生成文档点下载（docx / Excel / 修改稿）→ 正常触发浏览器下载，
      地址栏不出现 token（blob: 链接）；F12 Network 该请求带 Authorization 头
- [ ] **审阅页**：「查看完整文档」新标签打开 `:8002/agent/review/<pid>`：
      URL 的 `#jwt=...` 片段在页面加载后被清除（地址栏不再显示），文档正常渲染；
      直接复制该 URL 到新标签打开（无凭证）→ 页面顶部红色横幅提示缺少凭证
- [ ] **知识库页**：Agent 内打开「知识库」新标签 `:8002/kb?project=<pid>`：
      文件列表正常加载、可检索；从知识库批量加附件到当前项目成功
- [ ] **token 过期表现**（可选，改 UM 库 token 或等 24h）：Agent 视图任一请求 401
      → 顶部红色横幅"登录状态无效或已过期…"，非静默失败
- [ ] admin 登录：聊天列表可见迁移划入的存量项目（可正常打开/删除）
- [ ] **知识库隔离**（2026-09-21）：zhangsan 在「知识库」页上传文件 A → zhangsan
      检索问答可命中 A；admin 知识库页可见 A（标注 zhangsan）并可删除；
      zhangsan 删除按钮对他人文件（admin 库）无效（404）；zhangsan 的 agent
      对话中 search_kb 可检索到「自己上传的 A + 共享标准库内容」，但检索不到
      admin 上传的文件；admin 的 agent 可检索全部。存量上传文件（迁移划归
      admin）仅 admin 可检索

## 10. AI 文档审核（2026-10-12 集成）

前置：审核服务窗口已随 `start_all.bat` 启动（:8012，占用回退 8013/8014）。

- [ ] 侧边栏「AI 文档写作」之后出现 **「AI 文档审核」**（DocumentChecked 图标），
      点击后全屏浮层铺满视口，出现「文档审核数字员工」空状态与审核领域选择
- [ ] 工具栏首项「⟵ 返回系统」可回管理系统，再进会话状态保留
- [ ] **强刷缓存**（Ctrl+F5）：F12 Network 中审核请求发往 `:8012`（或 8013/8014），
      请求头含 `Authorization: Bearer eyJ...`，无 CORS 报错、无 401/403
- [ ] 无文件直接「开始对话审核」→ 进入自由对话模式，发一条消息能看到流式打字输出
      （fetch 流式 reader，非 EventSource）
- [ ] 上传一份体系文件（docx/pdf）审核：解析 → 逐章审核进度 → 审核报告生成；
      「导出审核报告」正常触发浏览器下载（blob: 链接，地址栏不出现 token）
- [ ] 停掉审核服务窗口 → 点「重试连接」出现红色横幅
      "⚠ 无法连接文档审核 Agent 服务"；重启后重试恢复
- [ ] **用户隔离**：admin 发起审核会话后，zhangsan 登录 F12 控制台模拟越权读
      （sessionId 换成 admin 的）：
      `fetch('http://localhost:8012/api/agent/conversation/state/<admin的sessionId>',{headers:{Authorization:'Bearer '+localStorage.token}}).then(r=>r.status).then(console.log)`
      → 输出 **403**；无凭证访问 → **401**；admin 本人访问 → 200
- [ ] 生成中点击「退出登录」→ SSE 流被中断，回到登录页无报错

## 11. 审核会话恢复与历史列表（2026-10-13 P0 优化）

前置：§10 全部通过；后端为本轮更新版（含 /api/sessions、restore、from_seq）。

- [ ] **历史会话列表**：header 出现「🕘 历史会话」按钮；发起一次自由对话后点开，
      列表显示该会话（自由对话/文件名、时间、单/多Agent、状态圆点）；
      F12 Network 确认 `GET /api/sessions` 带 Authorization 头且只返回本人会话
- [ ] **列表切换**：点另一条历史会话 → 聊天区清空并恢复该会话的消息/进度条/阶段；
      「删除」按钮确认后条目消失，再开列表不再出现；删除当前会话 → 界面重置为新自由对话
- [ ] **刷新恢复（内存会话）**：上传文档审核进行中 F5 刷新 → 页面自动恢复：消息
      历史、当前审核阶段、检查点卡片齐备；SSE 续连后 token 流继续（Network 中
      stream 请求带 `?from_seq=N`）
- [ ] **刷新恢复（完成后）**：审核完成后刷新 → 报告直接从 history 渲染（不重放），
      「导出审核报告」可用；断线后不再自动重连（Network 无反复重连的 stream 请求）
- [ ] **服务重启恢复**：审核进行中（最好停在 strategy_review/post_audit 检查点）停掉
      审核服务再启动 → 页面 SSE 断开后 2s 自动探测 → 自动调
      `POST .../conversation/restore/<id>` → 恢复到检查点等待输入，进度与已审
      章节不丢；history 中断前消息完整
- [ ] **SSE 断线续传**：审核进行中 DevTools → Network 选中 stream 请求右键
      Block/Unblock（或断网 5s 再恢复）→ 重连后漏掉的 token/checkpoint 事件补齐
      （Network 出现 `?from_seq=<断线前最大seq>` 请求），无内容跳变或重复渲染
- [ ] **过期降级**：删除服务端 checkpoints（或自由对话会话重启后）刷新 → 页面
      回退到全新自由对话，不白屏不报错弹窗
- [ ] **登出清理**：SSE 断线待重连状态下点「退出登录」→ 无重连请求再发出
      （deactivate 清 sseReconnectTimer）

## 12. 审核 Agent MCP 外部工具（联网搜索/网页抓取，2026-10-14 集成）

启动日志确认：`MCP 外部工具已加载: 2 个 (search_pro, web_fetch)`（未加载时打印降级
提示，审核/对话自动走内置工具，功能不受影响）。

- [ ] **启动加载**：启动审核服务（run.py）→ 控制台出现两台 qianwen 服务器
      `发现 1 个工具，注入 1 个`；`.env` 缺 DASHSCOPE_API_KEY 时对应服务器状态
      为 error 且 message 提示环境变量未设置（服务正常启动）
- [ ] **自由对话联网**：进入「AI 文档审核」→ 自由对话问实时性问题（如
      「搜一下 2026 年 NMPA 关于贴敷式胰岛素泵的最新公告」）→ 回答含实时信息
      且能给出处；对比知识库没有的内容也能答（说明走了联网而非仅 RAG）
- [ ] **指定网页读取**：自由对话给一个公开 URL 让它总结（如「读一下
      https://www.nmpa.gov.cn 某公告页并总结要点」）→ 返回该页内容摘要
- [ ] **审核中联网查证**：上传文档审核，在 strategy_review/post_audit 检查点
      提问「联网查一下 XX 标准最新版本号」→ 回答基于实时搜索结果
- [ ] **审核流工具调用**（单 Agent 模式）：审核进行中观察聊天流出现 🔧 工具调用
      状态卡（工具名含 search_pro / web_fetch 时即为 MCP 外部工具在参与审核）
- [ ] **多 Agent 模式对话**：多 Agent 会话中提问实时性问题同样能联网
      （章节审核本体仍是预检索+直接 LLM，不调用 MCP——设计如此）
