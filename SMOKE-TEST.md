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
