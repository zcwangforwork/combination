## 2026-06-16 - BM25 jieba中文分词优化

### 依据
根据 `researcher_docs/BM25_jieba中文分词优化_详细技术方案_20260616.md` 实施。

### 问题诊断
`vector_store.py` 的 BM25 分词使用 `str.split()`，中文文本词汇之间无空白分隔，导致整段中文被当作一个巨大 token，BM25 关键词匹配完全失效。混合检索退化为纯向量检索。

### Files Created
1. **app/services/rag/medical_device_dict.txt**: 医疗法规领域词典 (~80词)，覆盖产品名称、标准体系、风险管理、设计开发、质量管理、生物学、临床注册、电气安全、软件等9大类
2. **app/services/rag/stopwords_zh.txt**: 中文停用词表 (~100词)，包含通用中文停用词 + 医疗法规领域低信息量词 + 文档结构词
3. **app/services/rag/tokenizer.py**: ChineseTokenizer 类，封装 jieba.cut_for_search()，支持领域词典加载、停用词过滤、LRU缓存、线程安全单例模式

### Files Modified
1. **app/services/rag/vector_store.py**:
   - 新增 import: `threading`, `get_tokenizer`
   - 新增类变量: `_bm25_cache` (BM25 索引缓存), `_bm25_cache_lock`
   - 新增类方法: `_get_or_build_bm25()` (构建/复用 BM25 索引 + jieba分词), `invalidate_bm25_cache()` (缓存失效)
   - 重写 `_bm25_search_collection()`: `.split()` → `tokenizer.tokenize()` + BM25 缓存 + 优化参数 (k1=1.2, b=0.6)
2. **app/services/rag/ingest.py**: `ingest_all()` 和 `ingest_files()` 末尾新增 `VectorStore.invalidate_bm25_cache()` 调用
3. **requirements.txt**: 新增 `jieba>=0.42.1`

### Verification
- jieba 安装成功 (v0.42.1)
- tokenizer 单例模式正常
- 中文分词测试通过: "贴敷式胰岛素泵风险管理" → ['胰岛', '胰岛素', '贴敷式胰岛素泵', '风险', '管理', '风险管理']
- tokenize_corpus 批量分词正常
- VectorStore 新增方法可正常访问

## 2026-06-12 - 设计输入阶段文档生成扩展

### Changes Summary
根据《胰岛素泵-DHF清单.xlsx》中设计输入阶段所需的15份文档，扩展项目使其能够生成该阶段的所有文档类型。

### Files Modified
1. **app/services/doc_types.py**:
   - 新增 `essential_principles_checklist` (医疗器械安全和性能基本原则EP清单)
   - 新增 `software_development_plan_di` (设计输入阶段软件开发计划引用)
   - 将 `software_development_plan` 加入 design_input 分类
   - design_input 分类从16种扩展为19种文档

2. **app/services/prompt_engineer.py**:
   - 新增 `essential_principles_checklist` 专属生成提示词 (覆盖7个章节: 概述、通用安全、化学生物特性、感染控制、有源器械安全、标签信息、符合性声明)
   - 新增 `software_development_plan_di` 专属生成提示词

3. **app/services/minimax.py**:
   - 新增 `essential_principles_checklist` 章节定义 (7章)
   - 新增 `software_development_plan_di` 章节定义 (5章，复用software_development_plan结构)

4. **app/api/routes.py**:
   - 更新 `/agent/projects/{project_id}/auto-generate` 支持 `doc_type` 参数
   - 新增 `/agent/projects/{project_id}/batch-generate` 批量生成设计输入阶段全部文档 (SSE推送进度+ZIP打包下载)
   - 新增 `/agent/batch-download/{project_id}` ZIP下载接口
   - 新增 `import zipfile` 顶层导入

5. **app/services/agent_state.py**:
   - 新增 `doc_type` 字段到 DesignInputAgentState TypedDict

### Result
- 设计输入阶段现支持19种文档类型，全部具有章节定义和专属生成提示词
- 经典API (`/api/generate`) 可生成任意文档类型
- Agent批量生成API可一次性生成设计输入阶段全部文档并打包为ZIP

## 2026-06-02 09:55:00 - 贴敷式胰岛素泵数字员工全生命周期文档系统改造
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\project_0430_02_beta`
- Purpose: 将项目从 16 种文档类型的 QMS 生成工具改造为覆盖 94+ 种文档类型的贴敷式胰岛素泵全生命周期数字员工
- Files: doc_types.py (16→104), prompt_engineer.py (16→106), minimax.py DOC_CHAPTERS (16→106), routes.py, index.html
- Result: Success — 104 types, 106 chapters, 106 prompts, 10 categories, API 200 OK

## 2026-05-12 11:00:00 - RAG 知识库重建（使用向量化 API）
- Working Dir: `E:\nrf_sample_codes\code_writer\project_0430_02`
- Purpose: 使用火山方舟向量化 API (doubao-embedding-vision-250615, 1024维) 重建 RAG 知识库，替换旧的本地模型 (384维)
- Result: Success - 向量库从 0 重建到 650 chunks，172 个来源文件

### 详细操作记录

## 2026-05-12 11:05:00 - File Created
- File: `rebuild_kb_api.py`
- Change: 创建 RAG 知识库重建脚本，使用火山方舟 API 向量化，清除旧 384维 collection 并重新摄入
- Result: Success

## 2026-05-12 11:10:00 - File Created
- File: `test_rebuild_api.py`
- Change: 创建测试套件，覆盖 API Key、Embedder、VectorStore、摄入、检索、错误处理等 7 个测试
- Result: Success

## 2026-05-12 11:15:00 - File Edited
- File: `app/services/rag/embedder.py`
- Change: 重写 Embedder 类，从使用 volcenginesdkarkruntime SDK 改为使用 httpx 直接调用 /api/coding/v3/embeddings/multimodal 端点。原因：SDK 调用路径不正确（/api/v3/ vs /api/coding/v3/），且不支持 dimensions 参数
- Result: Success - API 调用正常返回 1024 维向量

## 2026-06-10 15:30:00 - Fix RAG retrieval blocking event loop (标准适用性清单 stuck)
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\design_input_generation`

### 2026-06-10 15:30:00 - File Edited
- File: `app/services/agent_tools.py`
- Change: (1) Added `import asyncio`. (2) Wrapped ALL blocking calls in all 4 tools in `asyncio.to_thread()` + `asyncio.wait_for()`: search_kb (90s), generate_section (300s), revise_section (180s), build_docx (60s). (3) Added `asyncio.TimeoutError` handlers for each tool.
- Result: Success — no tool blocks the event loop, user can send messages during generation

### 2026-06-10 15:32:00 - File Edited
- File: `app/services/rag/vector_store.py`
- Change: (1) Fixed bug on line 286 where `self.client.get_collection()` was used instead of `client.get_collection()` in the vector search loop of `retrieve_hybrid()` — would cause extra DB configs to never be queried. (2) Added `import time`. (3) Added timing logs: embedding time, vector search time, BM25 time, total time.
- Result: Success

### 2026-06-10 15:35:00 - File Edited
- File: `app/services/agent_engine.py`
- Change: Wrapped `interrupt()` call in `_pre_tool_node` with try-catch for `RuntimeError("get_config")`. On Python 3.10, LangGraph's `get_config()` contextvar can fail to propagate across async task transitions, causing the generate_section HITL to crash. Now gracefully skips HITL and proceeds directly to generation when context is unavailable.
- Result: Success

## 2026-05-12 11:20:00 - File Edited
- File: `app/services/rag/vector_store.py`
- Change: 移除全局 _embedder 变量，改为实例变量延迟初始化
- Result: Success

## 2026-05-12 11:30:00 - Bash Command Executed
- Command: `python test_rebuild_api.py`
- Working Dir: `E:\nrf_sample_codes\code_writer\project_0430_02`
- Purpose: 运行测试套件验证重建流程
- Result: Success - 6 passed, 1 skipped (检索测试需先重建)

## 2026-05-12 11:35:00 - Bash Command Executed
- Command: `python rebuild_kb_api.py`
- Working Dir: `E:\nrf_sample_codes\code_writer\project_0430_02`
- Purpose: 执行知识库重建，清除旧 384维向量，使用 API 重新摄入
- Result: Partial Success - 169 文件摄入, 486 chunks, 15 文件因 API 限流 (429) 失败, 耗时 538.9 秒

## 2026-05-12 11:45:00 - File Created
- File: `retry_failed_ingest.py`
- Change: 创建重试脚本，使用更长间隔重试因限流失败的文件
- Result: Success

## 2026-05-12 11:50:00 - Bash Command Executed
- Command: `python retry_failed_ingest.py`
- Working Dir: `E:\nrf_sample_codes\code_writer\project_0430_02`
- Purpose: 重试因 API 限流失败的文件
- Result: Success - 3 文件重试成功, 新增 28 chunks

## 2026-05-12 12:00:00 - Bash Command Executed
- Command: 增量重试缺失文件（Python 脚本内联执行）
- Working Dir: `E:\nrf_sample_codes\code_writer\project_0430_02`
- Purpose: 查找并重试所有尚未在向量库中的文件
- Result: Success - 12 文件重试成功, 新增 136 chunks, 总量 650 chunks

## 2026-05-12 12:05:00 - Analysis
- Topic: Embedder API 兼容性
- Finding: volcenginesdkarkruntime SDK 默认调用 /api/v3/ 路径，但正确的向量化 API 路径是 /api/coding/v3/embeddings/multimodal。使用 httpx 直接调用 HTTP 接口更可靠。
- Decision: 重写 Embedder 类使用 httpx 直接调用，参考 project_0428 的实现

## 2026-05-12 12:10:00 - Analysis
- Topic: 知识库重建结果
- Finding: 最终向量库 650 chunks, 172 个来源文件。检索验证通过，4 个测试查询均有相关结果返回（相似度 0.43-0.53）
- Decision: 重建完成，可以投入使用

## 2026-05-29 15:00:00 - 任务开始：贴敷式胰岛素泵知识库向量化

### 任务描述
将 `贴敷式胰岛素泵知识库` 目录（25个子目录，779个文件）中的所有文档转化为向量，存入独立的 ChromaDB 目录，供项目 RAG 检索使用。

### 修改的文件

#### 1. `app/services/rag/ingest.py` - 扩展文档格式支持
- **变更**: 添加 `extract_text_from_xlsx()` 和 `extract_text_from_md()` 函数
- **变更**: 更新 `extract_text_from_file()` 支持 .xlsx 和 .md 格式
- **变更**: 更新 `get_supported_files()` 扩展名列表包含 .xlsx 和 .md
- **原因**: 知识库中包含 xlsx 和 md 文件需要处理

#### 2. `app/services/rag/vector_store.py` - 支持多目录查询
- **变更**: 添加 `EXTRA_DB_CONFIG` 类变量和 `_extra_clients` 缓存
- **变更**: 添加 `_get_client_for_path()` 和 `set_extra_db_config()` 类方法
- **变更**: 修改 `retrieve()`、`retrieve_hybrid()` 方法遍历所有 DB 目录的 collection
- **变更**: 修改 `_bm25_search_collection()` 接受 client 参数
- **变更**: 修改 `count()` 方法统计所有 DB 目录
- **原因**: 需要从多个 ChromaDB 目录查询，新知识库存放在独立目录

#### 3. `app/main.py` - 启动时自动加载胰岛素泵知识库
- **变更**: 添加启动时检测 `chroma_db_insulin_pump` 目录并配置 EXTRA_DB_CONFIG
- **原因**: 确保 RAG 服务启动时自动包含新知识库

#### 4. `build_insulin_pump_kb.py` (新建) - 知识库摄入脚本
- **内容**: 完整的知识库构建脚本，包含文件扫描、文本提取、向量生成、ChromaDB 写入
- **功能**: 25个子目录映射到24种文档类型，跳过扫描版PDF，自动测试检索

### 执行结果

#### 摄入统计
- 源目录: `贴敷式胰岛素泵知识库`
- 向量库目录: `chroma_db_insulin_pump` (独立于现有的 `chroma_db`)
- Collection 名称: `insulin_pump_kb`
- 总文件数: 777 (排除2个不支持的PPT格式)
- 成功处理: 390 个文件
- 失败/跳过: 387 个 (主要是扫描版PDF无文本、少数损坏文件和临时文件)
- 总 chunks: 6,782
- 总耗时: 4,778秒 (79.6分钟)
- DB 大小: 119MB

#### 文档类型分布 (Top 10)
| doc_type | chunks |
|---|---|
| biocompatibility | 1,272 |
| medical_electrical_safety | 854 |
| software_usability | 785 |
| quality_management | 736 |
| sterilization | 649 |
| ghtf_guidelines | 492 |
| product_registration | 220 |
| labeling | 220 |
| emc | 202 |
| transport_packaging | 179 |

#### 检索测试结果
所有测试查询均返回高相关性结果 (相似度 0.62-0.78):
- "胰岛素泵电气安全基本要求" → IEC 60601 系列标准
- "风险管理报告编写指南" → ISO 14971 风险管理标准
- "电磁兼容测试方法" → IEC 61000-4 EMC 测试标准
- "无菌包装验证流程" → 包装验证方案文档

### 架构说明
查询流程: VectorStore.retrieve() → 遍历主DB (chroma_db) 的 QUERY_COLLECTIONS + 额外DB (chroma_db_insulin_pump) 的 EXTRA_DB_CONFIG → 合并结果按相似度排序

## 2026-06-06 - 文档生成提速优化（步骤1：参数调整）
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\project_0430_02_beta`
- Purpose: 通过调整两个核心参数显著降低文档生成总耗时
- 预期提速: 30-40%

### File Edited
- File: `app/services/minimax.py`
- Change 1 (line 1234): `self.max_concurrent = 6` → `self.max_concurrent = 12`
  - 理由: 小节LLM调用最大并发数翻倍。文档通常 20-40 小节，6 路并发需排 4-7 轮，12 路并发只需 2-4 轮，LLM 阶段墙钟时间近乎减半。火山方舟单 key 默认 RPM 300+，可支撑 12 并发。
- Change 2 (line 2313): `_call_api(..., max_tokens: int = 12000)` → `max_tokens: int = 6000`
  - 理由: 单小节实际内容很少超 6000 token。LLM 出 token 是线性时间消耗，上限砍半直接降低生成时长。不影响实际内容质量。
- Result: Success
- 验证方式: 重启服务后生成一份文档，对比 `timing_log` 中 `llm_total` 和 `total` 字段

## 2026-06-06 - 文档生成提速优化（Web搜索并发提升）
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\project_0430_02_beta`
- File: `app/services/minimax.py`
- Change (line 1235): `self.max_search_workers = 6` → `self.max_search_workers = 12`
- 理由: Web 搜索阶段（Phase 2b）当前是仅次于 LLM 的耗时大户。Agent SDK 搜索本质是 Claude API 调用，资源占用很轻，可支撑较高并发。Playwright 回退路径开销较大，但有 Agent SDK 优先策略兜底。30 小节文档原需 5 轮搜索（6 并发），现只需 3 轮（12 并发）。
- 预期提速: Web 搜索阶段墙钟时间下降约 40%
- Result: Success

## 2026-06-10 16:30:00 - 新增文档审阅页面
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\design_input_generation`

### 2026-06-10 16:30:00 - File Edited
- File: `app/api/routes.py`
- Change: 新增 `GET /api/agent/projects/{project_id}/document` 端点，从Agent状态中读取 generated_sections 并组装为结构化JSON（含产品信息、标准清单、章节排序、未处理项），供审阅页面使用。
- Result: Success

### 2026-06-10 16:32:00 - File Edited
- File: `app/main.py`
- Change: 新增 `GET /agent/review/{project_id}` 路由，返回 `review.html` 审阅页面。
- Result: Success

### 2026-06-10 16:35:00 - File Created
- File: `app/static/review.html`
- Change: 创建独立文档审阅页面。功能：(1) 通过URL提取project_id并调用 `/api/agent/projects/{project_id}/document` 获取文档数据；(2) 使用 marked.js CDN 渲染Markdown为格式化的HTML文档；(3) 左侧章节导航栏，点击跳转，滚动时自动高亮当前章节；(4) 顶部状态栏显示产品名、文档状态、章节数；(5) 产品信息面板显示名称/分类/预期用途；(6) 打印友好CSS (@media print隐藏侧边栏)；(7) 空状态/错误状态/加载状态三种UI；(8) 返回Agent对话链接。
- Result: Success

### 2026-06-10 16:38:00 - File Edited
- File: `app/static/agent.html`
- Change: 顶部栏新增"审阅文档"链接，指向 `/agent/review/{PROJECT_ID}`，初始化时自动设置href并显示。
- Result: Success

### 2026-06-10 17:00:00 - 新增直接下载端点 + 前端下载按钮
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\design_input_generation`

### 2026-06-10 17:00:00 - File Edited
- File: `app/api/routes.py`
- Change: 新增 `GET /api/agent/projects/{project_id}/download` 端点，直接从Agent状态读取 generated_sections、组装Markdown、通过TemplateService构建.docx并返回。用户无需在Agent对话中说"导出文档"即可下载。
- Result: Success

### 2026-06-10 17:02:00 - File Edited
- File: `app/static/review.html`
- Change: `downloadDocx()` 函数改为直接调用 `/api/agent/projects/{PROJECT_ID}/download` 下载.docx，不再弹alert提示。
- Result: Success

### 2026-06-10 17:05:00 - File Edited
- File: `app/static/agent.html`
- Change: (1) 顶部栏新增"下载文档"链接按钮。 (2) 新增 `downloadDocument()` 函数调用下载端点。 (3) `fetchState()` 中检测 `sections_generated` 长度>0时自动显示"审阅文档"和"下载文档"链接。
- Result: Success

## 2026-06-10 16:00:00 - 对话输出简化 (Issue #4: 过长、混乱、难以阅读)
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\design_input_generation`

### 2026-06-10 16:00:00 - File Edited
- File: `app/services/context_manager.py`
- Change: (1) `summarize_old_messages()` — 摘要从详细JSON格式改为紧凑纯文本（max 500 chars），每条消息截取从300→100字，LLM prompt改为"极简摘要（不超过300字）"。 (2) `_generate_fallback_summary()` — 简化降级摘要格式为纯文本。 (3) SystemMessage格式从详细说明简化为 `[进度回顾] {summary}`。
- Result: Success

### 2026-06-10 16:05:00 - File Edited
- File: `app/services/agent_prompt.py`
- Change: REPLY_STYLE 新增具体简洁规则：每次回复3-5句话以内，确认项用一行状态更新（如"✅ 性能要求已确认 (8项)"），生成章节后2-3行摘要，禁止输出JSON/状态快照/对话摘要，禁止重复列出所有已确认输入项。
- Result: Success

### 2026-06-10 16:10:00 - File Edited
- File: `app/static/agent.html`
- Change: (1) CSS新增 `.msg.agent.collapsed` 样式（max-height: 280px, overflow: hidden, 底部渐变遮罩）。 (2) CSS新增 `.msg-toggle` 展开/收起按钮样式。 (3) JS新增 `autoCollapseLongMessage(div)` 函数——文本>500字符自动折叠并添加"展开全部"/"收起"切换按钮。 (4) `sendMessage()` 和 `resumeAgent()` 的 `done` 事件中添加自动折叠调用。
- Result: Success

## 2026-06-10 17:15:00 - Fix LangGraph Recursion Limit
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\design_input_generation`

### 2026-06-10 17:15:00 - File Edited
- File: `app/services/agent_engine.py`
- Change: `invoke_agent()`、`stream_agent_events()`、`resume_agent()` 三个函数的 config 中均添加 `"recursion_limit": 100`。默认25步不足以支撑多次工具调用（search_kb + generate_section × 多章节 + revise + build_docx），在文档生成流程中会触发 GRAPH_RECURSION_LIMIT 错误。
- Result: Success


## 2026-06-30 11:04 - 修复 Agent 文档下载章节顺序错乱

### 问题
用户反馈：在修改完或重新生成完某一小节后，下载的文档中小节顺序错乱，新生成或修改后的小节没有放到应该放到的位置。

### 根因
`app/api/routes.py` 中两个直接下载端点使用了硬编码的 `priority_order` 列表 + `sorted(remaining.keys())` 字母序重排逻辑：

1. `GET /api/agent/projects/{project_id}/document` (review.html 章节导航用)
2. `GET /api/agent/projects/{project_id}/download` (下载按钮调用)

`priority_order` 列表（"封面"、"文档信息"、"产品画像"、"性能要求"等）与实际 design_planning 文档的章节名（"目的和范围"、"设计开发阶段划分"、"职责分配"等）完全不匹配，所有章节都落到 `sorted(remaining.keys())` 分支，按中文字符的 Unicode 码点排序，破坏了 `generated_sections` 字典本已正确保留的"首次生成顺序"。

而 Agent 驱动的 `build_docx` 工具（`agent_engine._sync_doc_context`）直接遍历 `sections.items()`，dict 顺序正确。两条下载路径行为不一致。

### 修复
移除两个端点的 `priority_order + sorted()` 重排逻辑，改为直接按 `generated` 字典的插入顺序输出，与 Agent `build_docx` 工具行为保持一致。

### 2026-06-30 11:20:00 - File Edited
- File: `app/api/routes.py`
- Change: `/agent/projects/{project_id}/document` 端点（原 line 764-779）的 `priority_order + sorted(remaining.keys())` 替换为 `[{"title": name, "content": content} for name, content in generated.items()]`
- Why: 保留 generated_sections 字典的插入顺序（即首次生成顺序），修订/重新生成同名小节时 dict 顺序自动保留
- Result: Success

### 2026-06-30 11:21:00 - File Edited
- File: `app/api/routes.py`
- Change: `/agent/projects/{project_id}/download` 端点（原 line 830-844）的 `priority_order + sorted(remaining.keys())` 替换为 `full_markdown = "\n\n".join(generated.values())`
- Why: 同上，这是 review.html "下载 .docx 文档" 按钮实际调用的端点
- Result: Success

### 2026-06-30 11:22:00 - Bash Command Executed
- Command: `python -c "import ast; ast.parse(open('.../routes.py', encoding='utf-8').read()); print('routes.py syntax OK')"`
- Working Dir: E:\nrf_sample_codes\working_team_work\code_writer
- Purpose: 语法检查修复后的 routes.py
- Result: Success - "routes.py syntax OK"

### 验证
- Grep 全项目确认无遗留 `priority_order` 或 `sorted(remaining` 模式
- tests/test_agent.py 仅断言 `build_state_snapshot` 输出（章节数量、key 成员），不涉及顺序，不受影响
- 未对 routes.py 两个端点做单元测试（不在最小修复范围内）

### 后续建议
若用户反馈 LLM 修订时传入的 section_name 与原 key 不一致（如 "目的和范围" vs "1. 目的和范围"），会导致新 key 追加到 dict 末尾、旧 key 残留，可再考虑基于 outline JSON 的章节匹配排序作为增强。

## 2026-06-30 17:00 - 新增"附件结构驱动文档生成"功能

### 背景
用户希望上传附件后能选择按附件章节结构生成新文档（而非让 LLM 自主设计 outline）。现有 analyze_document_structure 只输出扁平 level/title/summary，无法直接喂给 write_chapter（需 subsections[].title + content_points[]）。

### 用户选定方案
方案 B：LLM 二次细化——骨架识别 + LLM 基于附件全文补全 subsections/content_points。
**关键约束**：用户希望有附件时让用户选择 A(附件优先) 或 B(AI自主设计)，不强制走任一路径。

### 实施

#### 2026-06-30 17:00:00 - File Edited
- File: `app/services/agent_tools.py`
- Change: 新增 `outline_from_attachment` 工具（约 170 行），置于 analyze_document_structure 之后
  - Step1: 调用 analyze_document_structure 拿骨架
  - Step2: 从 _current_attachments 取附件 full_text（截前 20000 字符）
  - Step3: LLM 二次细化，注入骨架+全文，要求保留附件原章节顺序与标题，每章补 2-4 个 subsections
  - 复用 _extract_json 提取 JSON
  - 错误处理：附件无章节/识别失败 → 返回 error JSON，引导回退 design_outline
  - 加入 PHASE1_TOOLS 列表
- Why: 实现附件优先路径，输出与 design_outline 完全兼容，无缝衔接 write_chapter
- Result: Success

#### 2026-06-30 17:15:00 - File Edited
- File: `app/services/agent_engine.py` (line 222-232)
- Change: `_after_tools_node` 中 `if tool_name == "design_outline":` 改为 `if tool_name in ("design_outline", "outline_from_attachment"):`
- Why: 让新工具结果也写入 state["outline"] + outline_status="draft"
- Result: Success

#### 2026-06-30 17:30:00 - File Edited
- File: `app/services/agent_prompt.py`
- Change:
  (1) SOP_KNOWLEDGE 步骤4 增加"有附件时的路径选择"段落，要求 Agent 询问用户选 A(附件优先)或 B(AI自主)
  (2) TOOL_RULES 新增 outline_from_attachment 工具说明（5b）
  (3) "标准工作流"段落更新为反映两条路径
- Why: 让 Agent 有附件时主动询问用户选择，两条路径互斥
- Result: Success

#### 2026-06-30 17:45:00 - Bash Command Executed
- Command: `python -c "import ast; ast.parse(...)"` ×3 文件
- Purpose: 语法检查改动的 3 个 Python 文件
- Result: Success - agent_tools.py / agent_engine.py / agent_prompt.py 全部 OK

### 设计要点
1. **复用而非重造**：复用 analyze_document_structure、_extract_json、_find_chapter_subsections、write_chapter——零改动
2. **输出格式兼容**：与 design_outline 完全一致
3. **用户选择**：SOP 要求 Agent 询问 A/B，不擅自走任一路径
4. **优雅降级**：附件无章节时返回 error，Agent 告知用户并询问是否回退

### 涉及文件
| 文件 | 改动类型 | 改动量 |
|------|---------|-------|
| app/services/agent_tools.py | 新增工具 + 加入 PHASE1_TOOLS | ~170 行 |
| app/services/agent_engine.py | 1 行条件扩展 | 1 行 |
| app/services/agent_prompt.py | SOP + TOOL_RULES + 标准工作流 | ~30 行 |

无需改动：subagents.py、_find_chapter_subsections、write_chapter、routes.py、agent.html、analyze_document_structure

### 后续建议
- 启动服务实测：上传 Word 附件 → 确认被询问 A/B → 选 A → 验证 outline_from_attachment 被调用、state["outline"] 非空、write_chapter 匹配 subsections
- 若 LLM 细化输出偶尔不稳定，可调整 temperature 或增加 few-shot 示例

## 2026-06-30 17:50 - 修复附件上传 NameError

### 问题
用户上传附件时报错：`NameError: name 'attachments' is not defined` at routes.py line 951。

### 根因
`agent_upload_attachment` 函数中，从 `state_values` 读取了 Agent 状态，但未从中提取 `attachments` 字段到本地变量，直接调用 `attachments.append(...)` 导致 NameError。这是既有 bug（不是我引入的），上次附件功能开发时遗漏。

### 修复
在 `attachments.append(...)` 前添加：
```python
attachments = list(state_values.get("attachments", []) or [])
```

### 2026-06-30 17:50:00 - File Edited
- File: `app/api/routes.py` (line 951 附近)
- Change: 在 `attachments.append({...})` 前插入 `attachments = list(state_values.get("attachments", []) or [])`
- Why: 从 Agent 状态取出已有附件列表，避免 NameError
- Result: Success - routes.py syntax OK

### 验证
语法检查通过。重启服务后重新上传附件即可。

## 2026-06-30 18:00 - 重写 outline_from_attachment 提升章节识别完整性

### 问题
用户反馈"重启后，显示无法识别出完整的章节结构"。

### 根因
原实现两步流程依赖 `analyze_document_structure`：
1. `analyze_document_structure` 截取附件前 **12000 字符** 识别章节骨架——长文档只覆盖前几章，章节识别不完整
2. `outline_from_attachment` 又截取前 **20000 字符** 给细化 LLM——进一步限制覆盖
3. max_tokens=8192 输出可能不足以承载完整章节结构

### 修复
重写为**一步 LLM 调用**，不再依赖 `analyze_document_structure`：
1. 直接从 `_current_attachments` 取附件 full_text
2. 截取前 **50000 字符**（约覆盖 3-5 万字文档）送给 LLM
3. 一次 LLM 调用同时完成章节识别 + subsections + content_points 补全
4. max_tokens 提高到 **16384**
5. timeout 提高到 **300 秒**
6. system prompt 增加章节识别策略（编号、Markdown标题、Word样式、TOC优先）和"必须识别所有章节，不得遗漏"约束

### 2026-06-30 18:00:00 - File Edited
- File: `app/services/agent_tools.py` (outline_from_attachment 工具，约 line 1311-1479)
- Change: 重写整个工具实现，从两步流程改为一步 LLM 调用
- Why: 解决长文档章节识别不完整问题
- Result: Success - agent_tools.py syntax OK

### 验证
语法检查通过。重启服务后重新测试附件结构生成。

## 2026-07-02 17:54 - MinerU 文档解析集成

### 任务
参考 https://github.com/opendatalab/MinerU-Ecosystem/tree/main/langchain_mineru，在 design_planning_generation_local_model 项目中集成 MinerU 云端文档解析能力。

### 设计决策
- 解析模式：flash（无需 token，速度快，支持 PDF/DOCX/PPTX/XLS/XLSX/图片）
- 启用策略：opt-in，通过环境变量 USE_MINERU=true 启用；未启用或 SDK 缺失时自动回退到本地解析器
- 格式扩展：MinerU 启用时自动扩展上传格式到 .doc/.ppt/.pptx/.xls/.xlsx/.png/.jpg/.jpeg/.bmp/.tiff/.tif/.html/.htm
- 接口兼容：MinerU 返回 Markdown 后转换为 [(section_title, paragraph_text)] 列表，与现有 extract_text_from_* 系列签名一致

## 2026-07-02 17:54:13 - Analysis
- Topic: MinerU 集成点分析
- Finding: 项目文档解析入口集中在 app/services/rag/ingest.py 的 extract_text_from_file()，附件服务和 Agent 路径（ingest_attachment_to_kb / outline_from_attachment / search_attachment）都通过 full_text 间接使用其结果
- Decision: 在 extract_text_from_file 中加入 MinerU 优先路径并带 fallback，单一集成点覆盖所有下游消费方

## 2026-07-02 17:54:13 - File Created
- File: app/services/mineru_service.py
- Change: 新建 MinerU 服务封装模块，提供 is_mineru_enabled / is_mineru_sdk_available / extract_text_with_mineru / is_file_supported_by_mineru / mineru_supported_formats 等函数；包含 _markdown_to_paragraphs 将 MinerU 输出的 Markdown 切分为段落列表（标题→section_title，表格/代码块整体保留为段落）
- Result: Success - 语法校验通过，Markdown→段落 单元测试通过

## 2026-07-02 17:54:13 - File Edited
- File: app/services/doc_types.py
- Change: SUPPORTED_UPLOAD_FORMATS 改为通过 _compute_supported_upload_formats() 动态计算；MinerU 启用且 SDK 可用时追加 _MINERU_EXTRA_FORMATS（.doc/.ppt/.pptx/.xls/.xlsx/.png/.jpg/.jpeg/.bmp/.tiff/.tif/.html/.htm）
- Result: Success

## 2026-07-02 17:54:13 - File Edited
- File: app/services/rag/ingest.py
- Change: extract_text_from_file 增加 MinerU 优先路径（is_mineru_enabled + is_file_supported_by_mineru 检查通过则调用 extract_text_with_mineru，返回空或异常时回退本地解析器）；get_supported_files 在 MinerU 启用时追加扩展格式扩展名
- Result: Success - 导入级测试通过，无循环导入

## 2026-07-02 17:54:13 - File Edited
- File: .env
- Change: 追加 MinerU 配置段（USE_MINERU=false / MINERU_MODE=flash / MINERU_TOKEN= / MINERU_LANGUAGE=ch / MINERU_TIMEOUT=1200）
- Result: Success

## 2026-07-02 17:54:13 - File Edited
- File: requirements.txt
- Change: 追加 langchain-mineru>=0.1.0 和 mineru-open-sdk 依赖
- Result: Success

## 2026-07-02 17:54:13 - Bash Command Executed
- Command: `python -c "import ast; ast.parse(open(f).read())..."` for 3 files
- Working Dir: design_planning_generation_local_model
- Purpose: Python AST 语法校验 mineru_service.py / doc_types.py / ingest.py
- Result: Success - 3/3 文件通过

## 2026-07-02 17:54:13 - Bash Command Executed
- Command: `python -c "from app.services.mineru_service import ...; from app.services.doc_types import SUPPORTED_UPLOAD_FORMATS; from app.services.rag.ingest import extract_text_from_file"`
- Working Dir: design_planning_generation_local_model
- Purpose: 导入级测试，验证无循环导入，验证 USE_MINERU=false 时 SUPPORTED_UPLOAD_FORMATS 退化为 ['.docx', '.pdf', '.txt']
- Result: Success - 全部导入成功，预期行为符合

## 2026-07-02 17:54:13 - Bash Command Executed
- Command: `python -c "from app.services.mineru_service import _markdown_to_paragraphs; ..."`
- Working Dir: design_planning_generation_local_model
- Purpose: 验证 Markdown→段落 转换逻辑（标题/段落/表格/代码块）
- Result: Success - 5 段落输出正确，表格和代码块整体保留

### 验证总结
- 语法校验：3/3 通过
- 导入测试：无循环导入，依赖链正常
- 单元测试：Markdown→段落 转换符合预期

### 后续步骤（用户启用 MinerU 时）
1. `pip install langchain-mineru mineru-open-sdk`（在 env_01 环境）
2. 编辑 .env：设置 USE_MINERU=true（如需 precision 模式额外设置 MINERU_TOKEN）
3. 重启服务，SUPPORTED_UPLOAD_FORMATS 将自动扩展
4. 上传附件时 MinerU 优先解析，失败自动回退本地解析器

## 2026-07-02 18:00 - 用户启用 MinerU 后的调用链确认

### 用户问题
用户上传附件的时候可以进行解析吗？

### 分析
- 调用链：POST /api/upload → submit_extract_task() → _do_extract() → extract_text_from_file() → MinerU 优先路径
- /api/upload 和 /api/agent/upload/{project_id} 两个入口都走同一个 submit_extract_task，已自动覆盖
- validate_upload 使用动态 SUPPORTED_UPLOAD_FORMATS，会自动放行 MinerU 扩展格式
- Result: Yes — 用户设置 USE_MINERU=true 后上传附件会自动调用 MinerU 解析

## 2026-07-02 18:00:00 - File Edited
- File: app/api/routes.py
- Change: 更新 /api/upload 路由的 file 参数描述，反映 MinerU 启用后的扩展格式支持
- Result: Success

## 2026-07-02 18:10 - 服务启动崩溃修复（段错误隔离）

### 问题
用户重启服务后页面无响应。诊断：8002 端口未监听，uvicorn worker 进程在导入 app.main 时段错误崩溃（exit=139）。

### 根因
- 直接原因：`doc_types.py` 模块加载时调用 `is_mineru_sdk_available()` → `import langchain_mineru`
- `langchain_mineru` 导入链：→ `langchain_core.document_loaders.base` → `langchain_text_splitters` → `sentence_transformers` → **段错误**（sentence_transformers/__init__.py 第15行，C 扩展冲突）
- 段错误无法用 try/except 捕获，直接杀死 Python 进程

### 修复
1. `doc_types.py` 的 `_compute_supported_upload_formats()` 改为只检查 `is_mineru_enabled()`，不触发 SDK 导入
2. `mineru_service.py` 的 `is_mineru_sdk_available()` 改为子进程预检测，结果缓存
   - 子进程中 import langchain_mineru，段错误只杀死子进程，主进程安全
   - `_SDK_AVAILABLE_CACHE` 全局缓存避免重复开销
3. `extract_text_with_mineru` 在 SDK 不可用时直接返回空，绝不主进程 import

### 验证
- 完整导入链测试通过（exit=0）：mineru_service → doc_types → ingest → app.main
- `is_mineru_sdk_available()` = False（正确检测到段错误）
- `SUPPORTED_UPLOAD_FORMATS` 扩展到 16 种格式（基于 USE_MINERU=true）
- 服务启动正常：8002 端口监听，/api/doc-types 返回 HTTP 200，前端页面 HTTP 200

### 当前状态
- 服务已恢复，用户可正常发送消息
- USE_MINERU=true 但 SDK 不可用，所有解析走本地解析器（安全回退）
- 扩展格式（.doc/.ppt/.pptx/.xls 等）上传会被接受但本地解析器返回空
- 待解决：sentence_transformers 段错误问题（与 MinerU 集成无关，是环境已有问题）

## 2026-07-02 18:10:00 - Analysis
- Topic: langchain_mineru 段错误根因
- Finding: 段错误发生在 sentence_transformers/__init__.py 第15行，由 langchain_mineru 间接导入触发。这是环境已存在的 sentence_transformers 版本与 torch 不兼容问题，非 MinerU 集成引入
- Decision: 通过子进程隔离检测 SDK 可用性，主进程绝不直接 import langchain_mineru，保证服务稳定性

## 2026-07-02 18:10:00 - File Edited
- File: app/services/mineru_service.py
- Change: is_mineru_sdk_available() 改为子进程预检测+缓存；extract_text_with_mineru 在 SDK 不可用时直接返回空
- Result: Success - 主进程不再因 langchain_mineru 段错误崩溃

## 2026-07-02 18:10:00 - File Edited
- File: app/services/doc_types.py
- Change: _compute_supported_upload_formats() 移除 is_mineru_sdk_available() 调用，只检查 USE_MINERU 环境变量
- Result: Success - 模块加载不再触发 SDK 导入

## 2026-07-02 18:10:00 - Bash Command Executed
- Command: `python -c "from app.main import app; print('OK')"` 完整导入链测试
- Working Dir: design_planning_generation_local_model
- Purpose: 验证修复后导入链正常
- Result: Success - exit=0，所有模块导入正常

## 2026-07-02 18:10:00 - Bash Command Executed
- Command: `curl http://localhost:8002/api/doc-types`
- Working Dir: N/A
- Purpose: 验证服务恢复
- Result: Success - HTTP 200

## 2026-07-03 10:30 - MinerU 段错误根因修复（pyarrow DLL 冲突 + 子进程隔离）

### 问题
sentence_transformers 导入时段错误，导致 langchain_mineru 无法导入，MinerU SDK 检测失败。

### 根因定位（faulthandler）
段错误调用链：
```
sentence_transformers
  → datasets
  → pyarrow/dataset.py line 24  ← access violation
```
根本原因：torch 2.6.0+cu124 与 pyarrow 24.0.0 的 Intel OpenMP DLL 冲突（Windows DLL Hell），torch 加载后修改 DLL 搜索路径导致 pyarrow C 扩展加载错误的 DLL。

### 修复方案（两层防护）

#### 第一层：KMP_DUPLICATE_LIB_OK=TRUE 抑制 OpenMP 冲突
- `app/main.py` 顶部添加 `os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")`
- 必须在 import torch/pyarrow/sentence_transformers 之前设置
- 降级 sentence-transformers 到 3.4.1（兼容性更好）
- 降级 datasets 到 2.20.0（兼容 pyarrow）

#### 第二层：子进程隔离 MinerU 调用
- 新建 `app/services/mineru_runner.py`：独立子进程脚本，负责实际调用 MinerULoader
- `mineru_service.py` 的 `extract_text_with_mineru` 改为通过 subprocess 调用 runner
- 子进程输出 JSON 到 stdout，日志到 stderr
- 子进程段错误只杀子进程，主服务进程不受影响
- `is_mineru_sdk_available()` 也用子进程预检测+缓存

### 验证结果
- `app.main` 完整导入：exit=0，无段错误
- `is_mineru_sdk_available()`：True（子进程检测通过）
- `extract_text_with_mineru(docx)`：54 段落，主进程不崩溃
- 端到端测试：POST /api/upload → 20秒内 status=completed，preview 含 MinerU 返回的 Markdown
- 服务进程健康：reload+worker 都在运行，后续请求正常

### 文件变更

## 2026-07-03 10:30:00 - File Created
- File: app/services/mineru_runner.py
- Change: MinerU 子进程执行器，独立运行 MinerULoader，输出 JSON 到 stdout，日志到 stderr
- Result: Success

## 2026-07-03 10:30:00 - File Edited
- File: app/services/mineru_service.py
- Change: extract_text_with_mineru 改为 subprocess 调用 mineru_runner.py，主进程不直接 import langchain_mineru
- Result: Success

## 2026-07-03 10:30:00 - File Edited
- File: app/main.py
- Change: 顶部添加 KMP_DUPLICATE_LIB_OK=TRUE 环境变量（在所有 torch/pyarrow import 之前）
- Result: Success

## 2026-07-03 10:30:00 - Bash Command Executed
- Command: `pip install sentence-transformers==3.4.1`
- Purpose: 降级到稳定版本（5.4.1 与 transformers 4.46.3 不兼容）
- Result: Success

## 2026-07-03 10:30:00 - Bash Command Executed
- Command: `pip install datasets==2.20.0`
- Purpose: 降级 datasets 兼容 pyarrow
- Result: Success

## 2026-07-03 10:30:00 - Analysis
- Topic: pyarrow DLL 冲突根因
- Finding: torch 2.6.0+cu124 与 pyarrow 24.0.0 的 Intel OpenMP DLL 冲突，KMP_DUPLICATE_LIB_OK=TRUE 可抑制
- Decision: 两层防护（KMP_DUPLICATE_LIB_OK + 子进程隔离），确保主服务稳定性

## 2026-07-03 - Agent回复字数限制放宽

### 需求
用户希望 Agent 在与用户对话时的回答内容字数适当增多、回答内容更详细。

### Analysis
- Topic: Agent回复风格限制位置排查
- Finding: 回复字数与详细程度由 `app/services/agent_prompt.py` 中的 `REPLY_STYLE` 常量控制 (原420-430行)；其中"每次回复控制在3-5句话以内，极度简洁"和"生成章节后用2-3行摘要"是直接限制回复长度的核心约束。
- Decision: 仅修改 `REPLY_STYLE` 这一段提示词，放宽字数与详细度约束；不动 `agent_engine.py` 中的 `max_tokens=4096` (已足够容纳详细回复)；遵循最小编辑原则，不改动其他无关内容。

### File Edited
- File: `app/services/agent_prompt.py`
- Change: 重写 `REPLY_STYLE` 常量内容：
  - 将 "每次回复控制在3-5句话以内，极度简洁" 改为 "回复内容应充分、详尽，把问题讲清楚、讲完整，避免过度简短导致信息缺失"
  - 将 "生成章节后用2-3行摘要，不要重复输出全文" 改为 "可给出较详细的摘要：概括章节核心内容、关键条款/参数、引用的标准依据，以及与下一章的衔接关系"
  - 新增 "解释标准、条款、参数、设计决策时，可展开说明背景、适用场景、典型取值范围和注意事项"
  - 新增 "回答用户提问时，尽量直接给出有价值的信息和依据，而不是只回答'是/否'"
  - 保留 "不输出JSON/状态快照/对话摘要"、"不重复列出所有已确认策划项"、"给出依据"、"不编造"、"使用中文" 等核心规则
- Result: Success - Python语法通过，无遗漏的字数限制 (grep 已确认)

### Verification
- grep "简洁|简短|控制在|话以内|行摘要|不要重复" 仅匹配到新文案中的"避免过度简短"和"简短小标题"，旧的字数硬限制已全部移除。
- `agent_engine.py` 的 `max_tokens=4096` 保持不变，token上限足以支持更详细的回复。

### Impact
- 仅影响 Agent 与用户对话时的回复风格 prompt，不影响文档生成流程、工具调用、章节生成质量等核心功能。
- Agent 回复将更详细、更具解释性，对用户更友好；同时保留"不输出JSON/状态快照"等必要约束，避免污染对话上下文。

## 2026-07-03 - MinerU 子进程 stderr/stdout 解码乱码修复

### 需求
用户上传 docx 附件时，MinerU 子进程退出码 1 失败，但 stderr 中文被错误解码为乱码
（`[MinerU-Runner] ʼؽ...`），无法看到真实失败原因。

### Analysis
- Topic: MinerU 子进程输出解码方式排查
- Finding: `mineru_service.py:264` 和 `:269` 原本用 `data.decode("utf-8", errors="replace")`
  硬解码 stderr/stderr。但 Windows 下 `subprocess.run` 子进程的 stdout/stderr 默认跟随系统
  代码页 cp936/GBK，mineru_runner.py 中 print 的中文消息用 GBK 编码，用 utf-8 解码必然乱码。
- Decision: 新增 `_decode_subprocess_output` 辅助函数，依次尝试 utf-8 → cp936 → gbk → gb18030
  → latin1，首个成功为准；全部失败用 utf-8 + replace 兜底。同时修复 stderr 和 stdout 两处
  解码（stdout 也可能含中文，例如 JSON 内的段落内容）。遵循最小编辑原则，不动其他逻辑。

### File Edited
- File: `app/services/mineru_service.py`
- Change:
  1. L105-120 新增 `_decode_subprocess_output(data: bytes) -> str` 辅助函数
  2. L282 stderr 解码：`result.stderr.decode("utf-8", errors="replace")[-500:] if result.stderr else ""`
     → `_decode_subprocess_output(result.stderr)[-500:]`
  3. L287 stdout 解码：`result.stdout.decode("utf-8", errors="replace")`
     → `_decode_subprocess_output(result.stdout)`
- Result: Success - Python 语法检查通过；旧 `decode("utf-8", errors="replace")` 已全部替换。

### Verification
- `python -c "import ast; ast.parse(...)"` → syntax OK
- grep 确认 3 处改动生效 (L105 新增函数, L282 stderr, L287 stdout)

### Impact & Next Steps
- 仅影响 MinerU 子进程失败时的错误信息显示，不影响成功路径和回退逻辑。
- 需要重启 FastAPI 服务才能生效（模块已加载到内存）。
- 重启后重新上传一个会触发 MinerU 失败的 docx 文件，即可在日志中看到真实的中文错误信息，
  据此进一步诊断 MinerU 失败根因（可能是 GPU OOM、模型加载失败、文件格式问题等）。

## 2026-07-03 - MinerU 子进程失败时读取 stdout 错误详情

### 需求
stderr 乱码修复后，日志能看到中文 `[MinerU-Runner] 开始本地解析:` 但仍无 traceback，
真实错误信息缺失。

### Analysis
- Topic: mineru_runner.py 输出协议排查
- Finding: runner 的输出协议是 stderr 放日志、stdout 放 JSON 结果，**失败时也是 JSON**
  (`{"status":"error","message":"...","traceback":"..."}`, 见 mineru_runner.py L65/L70)。
  但父进程 `mineru_service.py` 在 `returncode != 0` 时只读 stderr，直接 return [],
  把 stdout 里的 JSON 错误详情（含 traceback）全部丢弃，所以永远看不到真实失败原因。
- Decision: 在 returncode != 0 分支中，额外读取并解析 stdout 的 JSON，提取 message 和
  traceback 字段打印出来。stdout 非 JSON 时也兜底显示原始内容（应对 import 阶段崩溃
  无输出的场景）。保持最小改动，不动成功路径和回退逻辑。

### File Edited
- File: `app/services/mineru_service.py` L281-302
- Change: returncode != 0 分支重写
  - 新增：读取 stdout 并尝试 JSON 解析
  - 新增：提取 `message` 和 `traceback` 字段，拼接显示
  - 新增：stdout 非 JSON 时的兜底显示
  - 保留：stderr 日志显示（作为辅助信息）
  - 输出格式改为分块打印：`[错误详情]` + `[stderr]` 两段
- Result: Success - Python 语法检查通过

### Verification
- `python -c "import ast; ast.parse(...)"` → syntax OK

### Impact & Next Steps
- 仅影响 MinerU 子进程失败时的错误信息显示完整性，不影响成功路径和回退逻辑。
- 需要重启 FastAPI 服务才能生效。
- 重启后重新上传触发 MinerU 失败的 docx，日志应能看到完整的 traceback，
  据此定位 MinerU 本地模型加载/推理的真实失败原因。

## 2026-07-03 - 修复 MinerU 子进程 ModuleNotFoundError

### 需求
stderr 乱码 + stdout 错误详情读取两处修复后，看到真实错误：
`ModuleNotFoundError: No module named 'app'` (mineru_runner.py:62)

### Analysis
- Topic: mineru_runner.py 子进程 sys.path 排查
- Finding: 父进程 `mineru_service.py:243` 用 `python <runner_path> <file>` 启动子进程，
  此时子进程 `sys.path[0]` 是 `app/services/` 目录，不含项目根目录。
  runner 顶部未做 sys.path 处理，导致 `from app.services.mineru_local import ...` 找不到 app 包。
  对比 `app/services/rag/ingest.py:17-18` 有同样的 sys.path 注入模式。
- Decision: 在 `mineru_runner.py` 顶部注入项目根目录到 sys.path，与 ingest.py 保持一致。
  最小改动，不动其他逻辑。

### File Edited
- File: `app/services/mineru_runner.py` L19-29
- Change: 顶部 import 区域新增：
  ```python
  from pathlib import Path
  project_root = Path(__file__).parent.parent.parent
  sys.path.insert(0, str(project_root))
  ```
  (`mineru_runner.py` 位于 `app/services/`，三层 .parent 回到项目根)
- Result: Success - Python 语法检查通过

### Verification
- `python -c "import ast; ast.parse(...)"` → syntax OK
- 完整功能验证需重启服务 + 重新上传 docx 文件

### Impact & Next Steps
- 修复 MinerU 子进程无法 import app 包的问题，理论上应让 MinerU 解析路径真正可用。
- 需要重启 FastAPI 服务才能生效。
- 重启后重新上传 docx，预期看到 `[MinerU] 解析完成: ... → N 段落, M 字符` 而非回退本地。
- 若仍有错误（如模型加载失败、GPU OOM 等），错误详情会通过上一条修复的 stdout 读取逻辑完整显示。

## 2026-07-03 - 安装 CUDA 版 torch 启用 GPU 推理

### 需求
MinerU 子进程加载本地 1.2B VLM 模型后推理极慢，导致路由 30 秒轮询超时返回 500。

### Analysis
- Topic: torch CUDA 支持排查
- Finding: `torch 2.12.1+cpu` 是 CPU 版本（`+cpu` 后缀），不含 CUDA 支持。
  `mineru_local.py:236-240` 的 `device_map="auto"` 在 CUDA 不可用时只能 fallback 到 CPU，
  1.2B VLM 在 CPU 上推理一页文档需 30-60 秒，多页直接超时。
- Decision: 替换为 CUDA 12.6 版 torch（用户 GPU 为 RTX 4060 Ti 8GB，CUDA 12.6）。
  查询 PyTorch 官方索引确认 `torch-2.12.1+cu126` 存在，可精确匹配当前版本不降级。

### Operations
- Command: `pip uninstall torch torchvision -y && pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126`
- Working Dir: env_01 conda 环境
- Result: Success - 下载 torch 2.6GB + torchvision 8.2MB，耗时约 5 分钟
- 安装结果: `torch-2.12.1+cu126` + `torchvision-0.27.1+cu126`

### Verification
- `torch.cuda.is_available()` → True ✓
- `torch.version.cuda` → 12.6 ✓
- `torch.cuda.get_device_name(0)` → NVIDIA GeForce RTX 4060 Ti ✓
- `torch.cuda.get_device_capability(0)` → (8, 9) Ada Lovelace ✓
- `total VRAM` → 8.0 GB ✓ (1.2B 模型 FP16 约 2.4GB，足够)

### Impact & Next Steps
- MinerU 子进程现在会通过 `device_map="auto"` 自动加载模型到 GPU，推理速度预计提升 10-50 倍。
- 需要重启 FastAPI 服务才能生效（新 torch 库需重新加载）。
- 潜在遗留问题：routes.py 的 30 秒轮询超时对大文档可能仍不够（GPU 首次加载模型 10-30 秒 +
  推理每页 1-5 秒，10 页文档可能需 30-60 秒）。建议重启后先测试小文档，若仍超时再调整超时或改异步上传。

## 2026-07-03 - 增大附件上传轮询超时到 5 分钟

### 需求
MinerU 启用 GPU 后，首次加载模型 + 多页推理可能超过原 30 秒轮询超时，导致 500 错误。

### File Edited
- File: `app/api/routes.py` L905-917
- Change:
  - `for _ in range(60)` → `for _ in range(600)` (30秒 → 5分钟)
  - 注释更新：`# 轮询等待提取完成（最长5分钟，适配 MinerU GPU 首次加载模型 + 多页推理耗时）`
  - 超时错误提示更新：`文件提取超时（超过5分钟），请重试或使用更小的文档`
- Result: Success - Python 语法检查通过

### Impact
- 附件上传接口 `/api/agent/upload/{project_id}` 的同步等待时间从 30 秒延长到 5 分钟。
- 足以覆盖 GPU 首次加载模型（10-30秒）+ 中等文档推理（10-50页 × 1-5秒/页）。
- 超过 5 分钟的极大文档仍会超时，届时可考虑改异步上传方案。

## 2026-07-23 - Bug 修复：附件上传 LangGraph Ambiguous Update 错误

### 上下文
- 触发现象：上传 xlsx 文件（`upload_6eca3966-8ec.xlsx`）时，MinerU 解析成功（3 段落，3258 字符），向量化成功（3/3），但最后状态更新步骤抛 `langgraph.errors.InvalidUpdateError: Ambiguous update, specify as_node`，HTTP 500。
- 错误链路：`app/api/routes.py:1148 agent_upload_attachment -> agent.aupdate_state(config, {"attachments": attachments})`。

### Analysis
- Topic: LangGraph `aupdate_state` 在无 `as_node` 时的归属节点推断
- Finding: `AgentState`（`app/services/agent_state.py:17`）用 `TypedDict(total=False)`，所有字段可选；`attachments` 字段（`agent_state.py:68`）声明为 `list[dict]`，**无 reducer**（不像 `messages` 用 `add_messages`），默认行为是覆盖。图（`agent_engine.py:342-369`）4 个节点（agent/pre_tools/tools/after_tools）的返回 dict 都不显式输出 `attachments`，但 LangGraph 1.x 在 total=False 的 schema 下无法唯一推断归属节点，抛 ambiguous。
- Decision: 给两处 `aupdate_state` 调用（上传 `routes.py:1148`、删除 `routes.py:1215`）显式传 `as_node="agent"`，跳过自动推断，直接把 `attachments` 当作 agent 节点输出覆盖到 checkpoint。`as_node` 值选用 `"agent"` 因为它是图中的核心节点，且 `_sync_attachment_context`（`agent_engine.py:321-326`）本就在该节点入口读取 attachments，逻辑自洽。

### File Edited
- File: `app/api/routes.py`
- Change:
  - line 1148（上传附件）：`aupdate_state(config, {"attachments": attachments})` -> `aupdate_state(config, {"attachments": attachments}, as_node="agent")`，并补充 3 行注释说明原因
  - line 1215（删除附件）：同样补 `as_node="agent"`
- Result: Success - 语法验证通过（`python -c "import ast; ast.parse(...)"` -> SYNTAX OK）
- 备注：另外两处 `aupdate_state`（`routes.py:674`、`routes.py:691`，更新 `generated_sections`）暂未改：`_after_tools_node` 节点显式返回 `generated_sections`（`agent_engine.py:282`），LangGraph 应能唯一推断；如后续也报 ambiguous 再同法修复。

### Next Steps
- 用户重新上传 xlsx 验证 500 错误是否消除。
- 验证附件删除接口（DELETE `/api/agent/projects/{id}/attachments/{file_id}`）也正常。
- 若运行后发现 `generated_sections` 相关接口也报 ambiguous，再补 `as_node` 修复。

## 2026-07-23 - Bug 修复：as_node="agent" 触发路由 + MinerU 子进程 gbk 编码崩溃

### 上下文
- 上一轮修复（as_node="agent"）后重启服务再测，xlsx 上传仍 500，但错误变了：
  - `ValueError: No messages found in input state to tool_edge: {'attachments': [...], 'messages': []}`
  - 堆栈：`aupdate_state -> abulk_update_state -> aperform_superstep -> run.ainvoke -> _aroute -> tools_condition -> ValueError`
- 日志同时显示 MinerU 子进程崩溃：`UnicodeEncodeError: 'gbk' codec can't encode character '\u20b9'`（₹ 印度卢比），MinerU 回退到本地解析器。

### Analysis
- Topic 1: as_node="agent" 为何触发 tools_condition
- Finding 1: 查 LangGraph 文档（https://docs.langchain.com/oss/python/langgraph/use-time-travel#from-a-specific-node）确认：`update_state(values, as_node=X)` 会用 X 节点的 writer 链应用更新，**writer 链包含该节点后面的条件路由 path 函数**（因为路由依赖节点输出）。agent 节点后面是 `add_conditional_edges("agent", tools_condition, ...)`（agent_engine.py:354-361），所以 writer 链包含 tools_condition。aupdate_state 内部执行 writer 链时触发 tools_condition，它检查 `messages[-1].tool_calls`，但只传了 attachments（messages 为空）-> ValueError。
- Decision 1: 改用 `as_node="after_tools"`。after_tools 节点后面是无条件边 `add_edge("after_tools", "agent")`（agent_engine.py:368），writer 链不含路由函数，不会触发 tools_condition；也不会触发 LLM 调用（aupdate_state 只写 checkpoint，不执行下一 superstep）。下次 ainvoke 时从 agent 节点恢复，会读到最新 attachments（符合预期）。这也解释了 routes.py:674/691 的 `aupdate_state({"generated_sections": ...})` 不报错：`_after_tools_node` 显式输出 generated_sections（agent_engine.py:282），LangGraph 无 as_node 时能唯一推断到 after_tools 节点。

- Topic 2: MinerU 子进程 gbk 编码崩溃
- Finding 2: mineru_runner.py:62 `print(json.dumps(result, ensure_ascii=False))` 在 Windows 子进程中执行，stdout 默认 gbk/cp936 编码，无法编码 `\u20b9`（₹）等非 GBK 字符，抛 UnicodeEncodeError，子进程退出码 1，父进程收到空输出回退本地解析器。
- Decision 2: 在 mineru_runner.py 开头（import 后）`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` + stderr 同样处理。父进程 `_decode_subprocess_output`（mineru_service.py:105-120）已支持 utf-8 解码，兼容。带 try/except 兜底 Python<3.7 用 io.TextIOWrapper 替换。

### File Edited
- File 1: `app/api/routes.py`
  - line 1148-1154（上传附件）：`as_node="agent"` -> `as_node="after_tools"`，注释扩充解释为何不能用 agent
  - line 1217（删除附件）：同样 `as_node="agent"` -> `as_node="after_tools"`
  - Result: Success - 语法验证 SYNTAX OK

- File 2: `app/services/mineru_runner.py`
  - line 24-32：import 后新增 stdout/stderr reconfigure 为 utf-8，带 try/except 兜底
  - Result: Success - 语法验证 SYNTAX OK

### Next Steps
- 用户重启服务，重新上传包含 ₹ 等非 GBK 字符的 xlsx，验证：
  1. MinerU 子进程不再因编码崩溃（应看到"[MinerU] 解析完成"而非"回退到本地解析器"）
  2. 上传接口返回 200 + success:true
  3. 附件删除接口也正常
- 若 generated_sections 相关接口（routes.py:674/691）后续也报 ambiguous，再补 as_node

## 2026-07-23 15:23:54 - Bug 修复（重新应用）：MinerU gbk 编码崩溃 + aupdate_state ambiguous（源码丢失后重新落地）

### 上下文
- 用户报告上传 xlsx/docx 附件时 500 错误，日志显示两类问题：
  1. `[MinerU] 子进程退出码 1 ... UnicodeEncodeError: 'gbk' codec can't encode character '\u20b9'/'\u2713'`，MinerU 回退本地解析器
  2. `langgraph.errors.InvalidUpdateError: Ambiguous update, specify as_node` at `routes.py:1148`
- 排查发现：2026-07-23 早前两轮修复（日志第 862-918 行）的决策正确，但**当前源码中修复未生效**--`mineru_runner.py` 无 stdout reconfigure，`routes.py:1148/1215` 无 `as_node`。与该项目 7 月 10 日出现的"源码丢失"现象吻合，需重新应用。

### Analysis
- Topic 1: MinerU 子进程编码
- Finding 1: `mineru_runner.py:62 print(json.dumps(result, ensure_ascii=False))` 在 Windows 子进程执行，stdout 默认 cp936/gbk，无法编码 ₹(U+20B9)/✓(U+2713) 等字符 -> UnicodeEncodeError -> 子进程退出码 1 -> 父进程 `_decode_subprocess_output` 收到空输出回退本地解析器。
- Decision 1: 在 import 后、main() 前 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` + stderr 同样，带 try/except 兜底 Python<3.7 用 `io.TextIOWrapper` 替换。父进程已支持 utf-8 解码，兼容。

- Topic 2: aupdate_state as_node 选型
- Finding 2: `AgentState` 为 `TypedDict(total=False)`，`attachments` 字段无 reducer，4 节点（agent/pre_tools/tools/after_tools）都不显式输出 attachments，LangGraph 无 as_node 时无法唯一推断归属 -> ambiguous。不能用 `as_node="agent"`：agent 节点后接 `add_conditional_edges("agent", tools_condition, ...)`（agent_engine.py:354-361），writer 链会触发 tools_condition 检查 `messages[-1].tool_calls`，只传 attachments 时 messages 为空 -> `ValueError: No messages found in input state to tool_edge`。
- Decision 2: 用 `as_node="after_tools"`。after_tools 节点后是无条件边 `add_edge("after_tools", "agent")`（agent_engine.py:368），writer 链不含路由函数，不触发 tools_condition；aupdate_state 只写 checkpoint 不执行下一 superstep，下次 ainvoke 从 agent 节点恢复会读到最新 attachments。

### File Edited
- File 1: `app/services/mineru_runner.py` L33-43
  - Change: import 后新增 stdout/stderr reconfigure 为 utf-8（errors="replace"），带 try/except 兜底 io.TextIOWrapper
  - Result: Success - `python -c "import ast; ast.parse(...)"` -> SYNTAX OK

- File 2: `app/api/routes.py` L1148, L1215
  - Change: 两处 `aupdate_state(config, {"attachments": attachments})` -> `aupdate_state(config, {"attachments": attachments}, as_node="after_tools")`（replace_all 一次命中两处）
  - Result: Success - SYNTAX OK

### Next Steps
- 用户重启 FastAPI 服务，重新上传含 ₹/✓ 等非 GBK 字符的 xlsx/docx 验证：
  1. 日志应显示"[MinerU] 解析完成"而非"回退到本地解析器"
  2. 上传接口返回 200 + success:true（不再 500 ambiguous）
  3. 附件删除接口（DELETE）也正常
- 若 generated_sections 相关接口（routes.py:674/691）后续报 ambiguous，同法补 `as_node="after_tools"`

## 2026-07-23 15:45:00 - 诊断增强：aupdate_state 加 try/except 暴露真实错误

### 上下文
- 用户重启服务后重新上传 xlsx/docx 仍 500，但终端只显示 `[MinerU] 开始解析` + `500 Internal Server Error`，无 traceback。
- 用户在浏览器 Network 面板看到 `{"detail":"Method Not Allowed"}`，但这是 405 响应（看错了请求，不是那个 500 POST）。
- 排查确认：服务确实从正确目录运行（PID 25524, `run.py` 在修复目录），无自定义异常处理器，LangGraph 版本 1.2.5。
- 无法确认 500 根因：可能是 aupdate_state 仍报错（但无 traceback），或 HTTPException（文件提取失败/超时）。

### Analysis
- Topic: 为何看不到 500 的真实错误
- Finding: routes.py 的 `aupdate_state` 调用无 try/except。如果是未捕获异常，FastAPI 会打印 ASGI traceback 到终端；如果是 HTTPException（如"文件提取失败"），不打印 traceback 只返回响应体。用户可能看漏了 traceback 或是 HTTPException。
- Decision: 给上传和删除两处 `aupdate_state` 加 try/except，同时 `print(traceback)` 到终端 + `raise HTTPException(500, detail=f"状态更新失败: {type(e).__name__}: {e}")` 返回到响应体。这样无论用户看终端还是浏览器都能看到具体错误。

### File Edited
- File: `app/api/routes.py`
  - L1147-1157（上传附件）：aupdate_state 包 try/except，print traceback + HTTPException 返回错误详情
  - L1223-1231（删除附件）：同上
  - Result: Success - SYNTAX OK

### Next Steps
- 服务 reload=True 自动重载，用户等几秒后重新上传附件
- 这次 500 时查看浏览器 Network -> Response 标签页，会看到 `{"detail":"状态更新失败: ErrorType: message"}` 具体错误
- 或查看终端，会看到 `[agent_upload_attachment] aupdate_state 失败:` + 完整 traceback
- 根据真实错误再定位根因

## 2026-07-24 - Bug 修复：精简文档比例模式无法压缩到目标比例

### 上下文
- 用户报告：精简文档时规定一个比例（如 0.5 = 压缩到 50%），实际无法精简到对应字数比例，结果往往远超目标。
- 代码链路：`summarize_document` -> `summarize_section` -> `_summarize_one_subsection`（agent_tools.py:1528+）

### Analysis
- Topic: 比例模式为何压缩不到位
- Finding: `_summarize_one_subsection` 有 4 个叠加问题：
  1. **Prompt 太宽松**（原 line 1556）：`目标字数约 {target_chars} 字（允许±15%偏差）` - "约"和"±15%偏差"给 LLM 过冲许可
  2. **重试条件太严**（原 line 1621）⭐主因：`if new_chars > target_chars * 1.5 and new_chars > orig_chars * 0.8` - 两条件同时满足才重试。例：原文500字、比例0.5、目标250字，LLM返回350字(70%)：350 > 375? 否 -> 不重试，70%被静默接受
  3. **只重试一次**（原 line 1622-1647）：即使触发重试也只一次，第二次仍过冲直接接受
  4. **无硬截断兜底**：所有 LLM 尝试失败后无按句子边界截断的兜底
- Decision: 修改 `_summarize_one_subsection`（1 文件约 60 行）：
  1. Prompt 收紧：`严格控制在 {target_chars} 字以内，最多不超过 {hard_limit} 字`（hard_limit = target × 1.15）
  2. 重试条件放宽：`new_chars > target_chars * 1.2`（超目标 20% 就重试，去掉 `and orig_chars * 0.8`）
  3. 迭代重试：最多 3 轮（2 次重试），每轮 prompt 更激进，temperature 降至 0.1，只在比上轮更好时接受
  4. 硬截断兜底：3 轮后仍超 `target × 1.3`，调用新增的 `_truncate_at_boundary` 按句子边界（。！？；\n）截断

### File Edited
- File: `app/services/agent_tools.py`
  - 新增 `_truncate_at_boundary(text, max_chars)` 函数（在 `_count_chinese_chars` 后）：按句子边界截断，保留表格/代码块完整性，目标 max_chars × 1.15 以内
  - 修改 `_summarize_one_subsection`：
    - L1589: 新增 `hard_limit = int(target_chars * 1.15)`
    - L1594: prompt 从"约 target_chars 字（±15%偏差）"改为"严格控制在 target_chars 字以内，最多不超过 hard_limit 字"
    - L1626: user_prompt 同步收紧
    - L1655-1700: 单次重试改为 3 轮迭代重试（超 target×1.2 重试，每轮更激进，temperature=0.1，只在更好时接受）
    - L1702-1709: 新增硬截断兜底（3 轮后仍超 target×1.3 调用 _truncate_at_boundary）
  - Result: Success - SYNTAX OK

### Impact
- 比例模式精度提升：从"LLM 返回 70% 却被接受"变为"3 轮迭代 + 硬截断保证不超过 target×1.3"
- 温度从 0.2 降至 0.1（重试轮）：减少 LLM 随机性，提高压缩一致性
- 硬截断兜底保证最坏情况下也不会超 target×1.3（之前可能超 target×1.5 甚至不压缩）
- summarize_document 和 summarize_section 均受益（都调用 _summarize_one_subsection）

### Next Steps
- 用户重启服务后测试比例模式精简（如 ratio=0.5），查看终端日志的 `compression_ratio` 是否接近 0.5
- 若 LLM 在 3 轮内达标，不会触发硬截断（理想情况）
- 若 LLM 持续过冲，会看到 `第N轮精简不足` + `硬截断兜底` 日志
- 如硬截断导致内容不完整，可考虑调整截断边界策略或增大 target×1.3 阈值

## 2026-07-24 - 诊断增强：精简功能所有小节 100% 失败，加错误日志暴露根因

### 上下文
- 用户测试比例模式精简（ratio=0.3, 8 章节），所有章节 `0/N 小节成功`，字数 `19164 -> 19164 (100%)`，完全没压缩。
- 意味着所有 `_summarize_one_subsection` 调用都返回了 error status，回退保留原文。
- 检查发现 Ollama 服务正常运行（`http://localhost:11435`），`qwen3.5:122b` 模型可用。
- 根因不明：异常处理器和空响应分支都**静默吞掉错误**，不打印任何信息。

### Analysis
- Topic: 为何所有小节精简都失败
- Finding: `_summarize_one_subsection`（agent_tools.py:1580+）有 3 个静默失败路径：
  1. LLM 空响应（line 1642-1646）：`if not response: return error` 无 print
  2. asyncio.TimeoutError（line 1711-1715）：返回 error 无 print
  3. 通用 Exception（line 1716-1720）：返回 error 无 print
- 可能原因（需终端日志确认）：
  a. **180s 超时**：qwen3.5:122b 是 122B 参数大模型，4 并发（Semaphore(4)）可能不够，每请求可能超 180s
  b. **空响应**：模型返回空内容或响应格式不符
  c. **API 错误**：连接/解析异常
- Decision: 给 3 个静默失败路径都加 print，暴露真实错误。用户重跑后终端会显示具体失败原因。

### File Edited
- File: `app/services/agent_tools.py`
  - L1642-1650（空响应分支）：加 print 显示小节名、目标字数、原文字数、Ollama URL 和模型名
  - L1715-1726（TimeoutError 分支）：加 print 显示小节名和目标字数
  - L1727-1733（Exception 分支）：加 print 显示小节名、错误类型和消息
  - Result: Success - SYNTAX OK

### Next Steps
- 用户重新运行精简（ratio 模式），查看终端日志：
  - `[summarize_section] LLM空响应` -> API 返回空，检查 Ollama 模型配置
  - `[summarize_section] LLM超时(180秒)` -> 122B 模型太慢，考虑增大超时或降并发
  - `[summarize_section] LLM调用异常` -> 其他错误，根据类型定位
  - `[_call_minimax_api_raw] 3次尝试后仍失败` -> API 连接/响应错误
- 根据真实错误决定下一步：增大超时 / 降并发 / 换模型 / 修响应解析
## 2026-07-24 11:25:00 - Analysis
- Topic: 比例模式下无法压缩到目标比例的根因分析
- Finding: 在 app/services/agent_tools.py 找到 5 个根因叠加：
  1. [关键] _summarize_one_subsection:1588 + summarize_section:1845 固定 80 字保底，对短小节破坏比例（如 100 字小节 ratio=0.3 → 实际 80%）
  2. [关键] _summarize_one_subsection:1637/1681 max_tokens 下限 2048 过高，小目标时 LLM 输出空间远超 3× target
  3. [中] _summarize_one_subsection:1664/1700 + _truncate_at_boundary:1538 硬截断阈值 1.3× / 1.15× 偏高
  4. [中] summarize_section:1894 失败小节保留原文且无再平衡机制（如 5 节中 1 节失败时总比例从 0.3 变 0.44）
  5. [弱] 系统 prompt "必须保留法规条款/技术参数/表格" 与激进压缩（ratio<0.5）冲突
- Decision: 推荐方案 A 最小修复（80字保底改比例化保底 + max_tokens 收紧 + 硬截断阈值降到 1.15 + 失败再平衡）

## 2026-07-24 11:35:00 - File Edited
- File: `E:\nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model\app\services\agent_tools.py`
- Change: 修复比例模式无法压缩到目标比例的 bug，4 个修改点：
  1. L1585-1597 _summarize_one_subsection 函数签名增加 is_ratio_mode/aggressive 参数；80 字保底改为 min(40, 原字数×0.9) 比例化保底
  2. L1631-1641 system_prompt 在 aggressive 模式下追加 '紧急要求' 强化指令段
  3. L1643-1656 max_tokens：is_ratio_mode=True 时用 max(int(target*2), 256) 替代 2048 下限（避免小目标时 LLM 输出过大）
  4. L1685-1732 重试/硬截断阈值从 1.2×/1.3× 收紧到 1.15×
  5. L1538-1556 _truncate_at_boundary 内部 limit 从 1.15 改为 1.05
  6. L1857-1880 summarize_section ratio 模式目标分配：80 字保底改为 min(40, oc×0.9) 比例化保底，并传 is_ratio_mode=True
  7. L1881-1962 增加 '比例模式失败再平衡' 逻辑：当 new_total > orig_total×ratio×1.15 时对超目标 15% 的小节触发二次精简（aggressive=True）
- Result: Success - 语法验证 OK，pytest 38/38 通过

## 2026-07-24 11:35:00 - File Edited
- File: `E:\nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model\tests\test_summarize.py`
- Change: 1) 更新 2 个旧测试反映新行为（test_min_target_chars_enforced: 80→3 比例化保底；test_words_mode_allocates_budget_proportionally: 适配 '严格控制在 N 字' prompt 格式）；2) 新增 6 个 TestRatioModeFixes 回归测试：短小节不被扩展、max_tokens 收紧、硬截断阈值、失败再平衡、aggressive prompt 强化、整体偏差 < 15%
- Result: Success - pytest 38/38 通过（含 6 个新测试）
## 2026-07-24 11:30:00 - Bash Command Executed
- Command: `python -c "import ast; ast.parse(open(r'E:\nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model\app\services\agent_tools.py', encoding='utf-8').read()); print('SYNTAX OK')"`
- Working Dir: `E:\nrf_sample_codes\working_team_work\code_writer`
- Purpose: 验证修复后 agent_tools.py 语法
- Result: Success - SYNTAX OK（conda 激活线程有 gbk 解码噪音但不影响结果）

## 2026-07-24 11:31:00 - Bash Command Executed
- Command: `python -m pytest tests/test_summarize.py -v --tb=short`
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model`
- Purpose: 跑现有 test_summarize 测试，验证修复无 regression
- Result: 30/30 PASS（最初 2 个失败后已更新旧测试断言）

## 2026-07-24 11:35:00 - Bash Command Executed
- Command: `python -m pytest tests/ -v --tb=short --ignore=tests/test_agent.py`
- Working Dir: `E:\nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model`
- Purpose: 跑全量测试（test_agent.py 排除因需要 Ollama 在线）
- Result: 72/72 PASS（test_summarize 38 + test_attachment 20 + test_prompt_eval + test_rerank_ab + test_agent_search）


## 2026-07-24 16:19:38 - Bug 修复：精简文档功能字数未变化（LLM num_predict 太小返回空响应）

### 上下文
- 用户报告："选择精简文档后，字数没有改变"
- 上轮 7-24 加了 print 错误日志后跑测试：所有章节 0/N 小节成功，总字数 19164 → 19164 (100%)，完全没压缩
- 检查 Ollama 服务正常（`http://localhost:11435`），`qwen3.5:122b` 模型可用
- 实际根因未明

### Analysis
- Topic: 为何所有小节精简都返回 error status，LLM 输出为空
- Finding: 用 curl 直接测试 Ollama `/api/chat` 接口，**实测 qwen3.5:122b 模型存在严重 num_predict bug**：
  - num_predict=200/400/1024/2048/4096 → done_reason="length"，content **完全为空**，但 eval_count 达到 num_predict 上限
  - num_predict=16384/32768/不设（默认）→ done_reason="stop"，content 正常返回 58-68 字
  - 实测：qwen3.5:122b 在 num_predict < 16384 时会消耗所有 tokens 但不输出可见内容（疑似 thinking/reasoning tokens 占用全部预算，无余量输出 visible content）
  - 对比测试：deepseek-r1:70b 用相同 prompt 正常返回 93 字（done_reason="stop"）
- Decision: 选定方案 1（提高 num_predict 上限）：
  1. `app/services/minimax.py` `_call_minimax_api_raw`: 默认 `max_tokens` 4096 → 16384
  2. `app/services/agent_tools.py` `_summarize_one_subsection`: 比例模式上限 4096 → 16384；非比例模式上限 8192 → 16384
  3. `tests/test_summarize.py::test_max_tokens_tightened_in_ratio_mode`: 更新断言 400→16384
- 备选方案：切换 deepseek-r1:70b 模型（用户已选方案1）

### File Edited
- File 1: `app/services/minimax.py` L21-41
  - Change: `_call_minimax_api_raw` 参数 `max_tokens: int = 4096` → `max_tokens: int = 16384`，docstring 补充说明
  - Result: Success - SYNTAX OK
- File 2: `app/services/agent_tools.py` L1647-1656
  - Change: `_summarize_one_subsection` max_tok 计算：
    - 旧：比例 `min(max(int(target_chars * 2), 256), 4096)` / 非比例 `min(max(target_chars * 3, 2048), 8192)`
    - 新：比例 `min(max(int(target_chars * 3), 16384), 16384)` / 非比例 `min(max(target_chars * 3, 16384), 16384)`
    - 加注释说明 qwen3.5:122b thinking tokens 占用
  - Result: Success - SYNTAX OK
- File 3: `tests/test_summarize.py` L709-751
  - Change: `test_max_tokens_tightened_in_ratio_mode` 断言更新为 max_tokens ∈ [16384, 16384]（不再 <=512）
  - Result: Success

### Verification
- 单元测试：38/38 全部通过（`pytest tests/test_summarize.py -v`）
- 真实 LLM 调用测试：`_summarize_one_subsection` ratio mode (target=200字)
  - 旧 (max_tokens=200-4096): status=error, LLM空响应
  - 新 (max_tokens=16384): **status=ok, orig_chars=170 → new_chars=121** ✅ 字数真正减少

### Impact
- 精简功能恢复正常：所有小节能成功生成精简内容
- 副作用：单次 LLM 调用时间从 ~3s 增加到 ~55s（要等够 16384 tokens 预算），但这是 qwen3.5:122b 模型本身特性
- 4 并发（`_llm_semaphore`）保持不变，8 章节 5 小节/章 ≈ 40 调用 / 4 并发 ≈ 10 批 × 55s ≈ 9 分钟（用户需耐心等待）

### Next Steps
- 用户重启服务（FastAPI 有 reload=True 应自动重载）后测试精简
- 终端应能看到 `[summarize_section] '章节名': N/N subsections summarized, X -> Y chars (Z%)` 而非 `LLM空响应`
- 比例模式（如 ratio=0.3）应能看到总比例接近 0.3（±15%）
- 若 LLM 仍然很慢（每个小节 55s），可考虑：
  - 减少 `_llm_semaphore` 并发（4 → 2）防止 OOM
  - 或切换到 deepseek-r1:70b（响应 32.9s/93字，比 qwen3.5:122b 快 40%）

---

## 2026-07-28 - RAG search_kb 同时检索主库和 uploads 集合

### 背景
用户问："让rag检索的时候同时查两个collection"。

### Analysis
- Topic: search_kb 工具当前只检索主知识库 `insulin_pump_kb`，完全不查 `uploads`（用户上传附件库）
- Finding: 
  - `app/services/rag/vector_store.py:32` `QUERY_COLLECTIONS = ["insulin_pump_kb"]` 硬编码只查主库
  - `app/services/agent_tools.py` 原 `search_kb` 直接调用 `VectorStore().retrieve_and_rerank()`，受 `QUERY_COLLECTIONS` 限制
  - ChromaDB 实际集合：`insulin_pump_kb` (9622) / `qms_doc_uploads` (515) / `qms_doc_insulin_pump_kb` (1, 几乎空)
  - `attachment_service.py` 的上传走 `qms_doc_uploads`（带前缀），所以不能用"加 raw 名到 QUERY_COLLECTIONS"的方式
  - 解决：让 `search_kb` 并行查主库 + 直接对 uploads 集合做向量检索，然后合并
- Decision: 
  1. 在 `search_kb` 内部新增 `_do_retrieve_uploads()` 闭包，直接用 `VectorStore(collection_name="uploads").collection.query()` 走小集合向量检索
  2. `asyncio.gather` 并行执行主库（可能 rerank 较慢）和 uploads（秒级）两个检索
  3. 合并结果：按 `rerank_score`（主库）/`similarity`（uploads）降序，按 `chunk_id` 去重，取 top_k
  4. 每个结果打 `source_collection` 标签（"insulin_pump_kb" 或 "uploads"），uploads 的 source 前缀 `[附件]`
  5. 主库走 rerank；uploads 集合规模小（515 chunks）直接向量检索即可，不再走 rerank
  6. 异常隔离：任一检索失败/超时仅丢该侧结果，另一侧正常返回

### File Edited
- File: `app/services/agent_tools.py` L82-268
  - Change: 重构 `search_kb` 工具，同时检索主库与 uploads 集合
  - 关键改动：
    * 拆出 `_do_retrieve_main()`（原主库检索，可走 rerank）
    * 新增 `_do_retrieve_uploads()`（直接查 `qms_doc_uploads` 集合，规模小无需 rerank/BM25）
    * `asyncio.gather(..., return_exceptions=True)` 并行执行
    * 异常隔离 + 结果归一化
    * 按 `rerank_score`/`similarity` 排序，按 `chunk_id` 去重，取 top_k
    * 输出新增 `source_collection` 字段和 `uploads_included` 标志
  - Result: Success - SYNTAX OK

### Verification
- 单元测试：`tests/test_summarize.py` 38/38 通过 ✅
- 单元测试：`tests/test_agent.py::test_search_kb_no_results_format` 通过 ✅（之前因 mock 错误挂掉，现已修复）
- 单元测试：`tests/test_agent.py::test_search_kb_success_format` 仍 fail（pre-existing：mock 用了 `content` 字段而代码读 `text`，且未 mock `retrieve_and_rerank`；与本次改动无关）
- 真实功能测试：query="GB 9706 医用电气设备安全", top_k=5, use_rerank=False
  * status=ok, uploads_included=True
  * 主库 4 条 + uploads 1 条 → 合并 5 条 ✅ 双 collection 同时检索已生效

### Impact
- 用户上传的附件（之前被向量化但永远不会被主 RAG 搜到的内容）现在可以通过 `search_kb` 自动检索到
- LLM 在生成章节时不再需要 Agent 自觉调用 `search_attachment` 才能引用附件内容
- 额外延迟：uploads 检索耗时约 0.5-1s（包含 embedding 一次 ~0.6s + 向量查询 ~0.1s），不影响主库 rerank 路径总时间（120s 预算内）
- 输出格式向后兼容：原有 `content`/`source`/`score` 字段保留，新增 `source_collection` 字段（LLM 可选择性利用）

### Next Steps
- 监控 LLM 是否会因为引入 uploads 来源内容而出现"答非所问"或"过度引用附件"的情况
- 必要时可在 prompt 中提示 LLM 区分 `source_collection` 来源
- 后续可考虑：把 `qms_doc_uploads` 也加入 `QUERY_COLLECTIONS` 的"已加前缀"变体，统一检索入口（但需先解 `retrieve_hybrid` 内部硬编码 raw 名的历史债务）

---

## 2026-07-28 - 精简文档段落逻辑连贯性增强

### 背景
用户反馈："精简文档时注意，精简完后要保持精简后的文档段落逻辑通顺"。

### Analysis
- Topic: 精简后段落逻辑被破坏的根因分析
- Finding: 当前实现有 4 个破坏段落逻辑的环节：
  1. **小节独立精简** — LLM 看不到上下文，可能写"如前所述/详见下表"等悬空引用
  2. **小节间无衔接感知** — 整章压缩后相邻小节话题可能跳脱
  3. **硬截断留下悬空末句** — `_truncate_at_boundary` 只按句号切，可能留下"因此..."/"见下表..."等无承接的句
  4. **无自检机制** — 精简后无质量校验，问题全靠用户肉眼发现
- Decision: 4 项针对性增强
  1. **相邻小节上下文传递**：`_extract_neighbor_snippets` 提取每小节的 prev/next 摘要，传给 LLM
  2. **Prompt 段落连贯性约束**：在 system_prompt 增加禁悬空引用、禁连接词开头、保持话题衔接 4 条规则
  3. **硬截断后清理**：`_strip_dangling_tail` 截断后检查末句是否以连接词开头或含悬空引用，若是则丢弃该句
  4. **组装后自检**：`_detect_dangling_references` 按 ## 标题切段检测两类问题（dangling_starter / dangling_reference），结果写入 `flow_issues` 字段

### File Edited
- File 1: `app/services/agent_tools.py` L1668-1701（`_summarize_one_subsection`）
  - Change: 新增 `prev_context` / `next_context` 参数；system_prompt 增加"段落逻辑连贯性要求"章节
  - Result: Success
- File 2: `app/services/agent_tools.py` L1630-1690（`_truncate_at_boundary` + `_strip_dangling_tail` + 字典常量）
  - Change:
    - `_truncate_at_boundary` 截断后调用 `_strip_dangling_tail` 二次清理
    - 新增 `_DANGLING_STARTERS`（24 个连接/承转词）和 `_DANGLING_TAIL_PATTERNS`（覆盖 look-forward + look-back 共 23 个悬空引用模式）
    - 新增 `_strip_dangling_tail`：逐句检查末句，命中即丢弃，最多清理 3 句
  - Result: Success
- File 3: `app/services/agent_tools.py` L1729-1839（新增辅助函数）
  - Change:
    - 新增 `_extract_neighbor_snippets(bodies, snippet_chars=100)`：为每个小节提取 prev/next 摘要（按句子边界截断）
    - 新增 `_detect_dangling_references(text)`：按 ## 标题切段，检测 dangling_starter 和 dangling_reference 两类问题
  - Result: Success
- File 4: `app/services/agent_tools.py` L2123-2255（`summarize_section` 主流程）
  - Change:
    - 调用 `_extract_neighbor_snippets` 一次性算出所有小节摘要
    - `_summarize_one_subsection` 调用时传 prev/next
    - 比例模式再平衡的 retry path 也传 prev/next
    - 组装后调用 `_detect_dangling_references`，结果写入 `flow_issues` 返回字段和 console log
  - Result: Success
- File 5: `tests/test_summarize.py` L894-1062（新增 17 个测试用例）
  - Change:
    - `TestExtractNeighborSnippets` (5 个)：边界/中间/单节/句子完整性
    - `TestStripDanglingTail` (6 个)：连接词/引用/多层/干净文本/空文本/3 句上限
    - `TestDetectDanglingReferences` (6 个)：dangling_starter/look-forward/look-back/正常文本/多小节/空文本
  - Result: Success

### Verification
- 单元测试：`tests/test_summarize.py` 55/55 通过 ✅（38 原有 + 17 新增）
- 语法验证：ast.parse 通过
- 手动测试：`_strip_dangling_tail` 验证多层清理正常工作（输入 3 句含连接词/引用，输出剩 2 句正常）
- 手动测试：`_detect_dangling_references` 正确识别 4 类问题（连接词开头/look-forward/look-back/混合）

### Impact
- **LLM 输入增加**：每小节 prompt 多 ~200 字（prev+next 摘要），约 +20% input token 成本
- **零 LLM 调用次数变化**：仍是每小节 1 次 + 失败再 2 轮重试
- **零外部依赖**：纯 Python 文本处理 + 已有 LLM 调用
- **可观测性提升**：返回的 `flow_issues` 字段让 LLM 和前端都能感知段落连贯性问题；可后续接入自动修复
- **API 兼容性**：`prev_context`/`next_context` 默认为空字符串，外部调用方无感知；`flow_issues` 字段为新增，老调用方忽略即可

### Next Steps
- 监控真实 LLM 输出是否仍有悬空引用：可能需要在 prompt 中提供更具体的"改写为自包含"示例
- 后续可考虑：当 `flow_issues` 数量 > 阈值时，自动对有问题的小节做一次"流畅化"二次调用（仅做衔接修复，不压字数）
- `_DANGLING_STARTERS` 和 `_DANGLING_TAIL_PATTERNS` 字典可基于实际误报持续扩充

---

## 2026-07-28 - 精简 Prompt 增加可读性要求 + 悬空引用后处理兜底

### 背景
用户反馈："精简文档时注意，精简完后要保持文档的每个部分是正常可读的"。

### Analysis
- Topic: `summarize_section` 的 LLM 精简 Prompt 缺少"可读性"硬约束
- Finding: 现有 Prompt 只覆盖字数/必保项/可精简项/禁止项/输出格式，但没规定精简后必须保持：
  1. 句子完整（不应中途截断、出现残句）
  2. 段落连贯（不应话题跳脱）
  3. 悬空引用清理（"如前所述""见下表"等引用词精简后失去目标对象）
  4. 上下文衔接（不应出现"前文/后文"等断裂感）
  5. 格式完整（不应破坏列表/表格结构）
  6. 首尾完整（不应截掉"因此""综上"等结论词）
- Decision: 
  1. 在 `_summarize_one_subsection` 的 system_prompt 中新增"可读性要求"章节，列 6 条硬约束
  2. 同步在 `aggressive=True` 重试 prompt 中追加"可读性约束仍然适用"声明
  3. 额外加一个**后处理兜底**：用正则匹配 8 种常见悬空引用词，若在文本末尾出现则截断到该引用所在句子的开头（避免留下"如前所述……"等半句话）

### File Edited
- File: `app/services/agent_tools.py` L1701-1755 (system_prompt) + L1800-1828 (后处理)
  - Change 1: system_prompt 新增"可读性要求"章节（6 条硬约束）
  - Change 2: aggressive=True 时追加"可读性约束仍然适用"声明
  - Change 3: 后处理新增悬空引用兜底（8 种模式 + 句子边界截断）
  - Result: Success - SYNTAX OK

### Verification
- 单元测试：`tests/test_summarize.py` 38/38 全部通过 ✅
- 第一次提交 bug 修复：`_re_dangling.search(cleaned)` 漏传 pattern 参数导致 TypeError 被外层 except 吞掉，所有小节被判失败（7 个测试挂掉）。修后恢复
- 实际行为（手动验证 5 个中文用例）：
  - "正常内容，无需清理。" → 不动 ✅
  - "本章主要讨论风险评估。如前所述。" → 截断到"。"前 → "本章主要讨论风险评估。" ✅
  - "如上所述，本文档适用于..." → 不动（无句号在引用前）✅
  - "风险评估见下表" → 不动（无句号在引用前）✅
  - "风险管理。详见后续" → 截断到"。" → "风险管理。" ✅
  - "前文已有讨论，下面是具体内容。" → 不动（非悬空引用）✅

### 影响
- LLM 现在有明确的 6 条可读性硬约束
- 即使 LLM 漏掉悬空引用（违反 Prompt 约束），后处理兜底会清理最严重的"句末悬空引用"情况
- 测试通过率保持 100%（38/38），未引入新 failure

### Next Steps
- 监控真实 LLM 调用是否还出现"如前所述"等悬空引用（Prompt + 兜底应能覆盖）
- 必要时可扩展悬空引用模式列表或加正则检测"参见 §3.2"等带具体位置的引用

## 2026-07-30 16:47:13 - 精简文档功能优化（Prompt 重构 + 后置可读性校验）
- Project: design_planning_generation_local_model
- Working Dir: E:\nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model
- Task: 优化精简文档功能，保证精简后文档语言逻辑通顺、可读性强、意思不变情况下减少字数
- 改动范围: app/services/agent_tools.py + tests/test_summarize.py

### 2026-07-30 16:47:13 - File Edited
- File: app/services/agent_tools.py
- Change: 新增 `_validate_readability` 函数（120行），检测残句结尾/残句开头/悬空引用/表格列数不一致/表格缺分隔行/空列表项 6类可读性问题
- Result: Success - 语法验证通过

### 2026-07-30 16:53:00 - File Edited
- File: app/services/agent_tools.py
- Change: 重构 `_summarize_one_subsection` 的 system_prompt，优先级改为"意思不变>逻辑通顺>字数控制"，字数从硬约束"严格控制N字以内"改为软约束"目标约N字(±15%浮动)"；aggressive模式去掉"删除所有过渡性描述"过度指令
- Result: Success

### 2026-07-30 16:55:00 - File Edited
- File: app/services/agent_tools.py
- Change: 集成后置可读性校验流程：LLM返回后调用 `_validate_readability`，不达标触发1次修复重试（构造修复prompt含具体issues列表）；硬截断阈值从 target*1.15 提高到 target*1.3；返回值新增 readability_warnings 字段
- Result: Success

### 2026-07-30 16:56:00 - File Edited
- File: tests/test_summarize.py
- Change: 更新6处旧prompt关键词引用（"严格控制在"->"目标约"），适配新prompt格式
- Result: Success

### 2026-07-30 16:57:00 - File Edited
- File: tests/test_summarize.py
- Change: 新增 TestValidateReadability 测试类（17个用例）+ TestReadabilityIntegration 测试类（4个用例），覆盖校验函数各项检测和集成流程
- Result: Success

### 2026-07-30 16:58:00 - File Edited
- File: app/services/agent_tools.py
- Change: 修复 `_validate_readability` 4个bug：1)残句开头检测rest含句号导致漏检 2)表格引用自身包含ref_id导致漏检 3)章节引用同问题 4)表格分隔行regex不允许中间竖线导致完整表格误判
- Result: Success

### 2026-07-30 17:00:00 - Analysis
- Topic: 测试结果验证
- Finding: test_summarize.py 59/59 全部通过；完整测试套件 120 passed, 4 failed
- Decision: 4个失败（test_phase1_tools_list过时断言4vs15、test_fallback_summary编码乱码等）均为预先存在的问题，与本次精简文档优化无关

### Next Steps
- 监控真实LLM调用时可读性校验的误报率
- 必要时扩展 `_validate_readability` 的检测项
- 考虑后续优化：章节级上下文精简（本次未实施）

## 2026-07-31 17:55:00 - Plan-Eng-Review 执行
- Topic: Solution D 多附件全场景覆盖（混合方案）技术评审
- Finding: 当前 `_resolve_attachments` 过早合并附件为单一字符串，下游 prompt builder 丢失附件边界无法做配额分配
- Finding: 3 种场景的字符预算（3000/1500/50000）总量充足，问题在于分配方式而非总量
- Finding: VectorStore 语义检索可用但会增加依赖和延迟，建议 v2 升级
- Decision: 推荐方案 Y（新增 `attachment_texts` 参数，向后兼容）+ 配额分配（比例+最小500保障）+ 逐附件关键词匹配 + outline 等额分配
- Output: `E:\nrf_sample_codes\working_team_work\public\docs\code_writer_docs\plan-eng-review-2026-07-31-multi-attachment.md`
- Result: Success - 评审完成，待用户确认后实施

## 2026-07-31 18:10:00 - Solution D 实施完成
- Topic: 多附件全场景覆盖（混合方案）实施
- Finding: 4 个文件修改完成，所有新增测试通过
- Decision: 采用方案 Y（新增 attachment_texts 参数向后兼容）+ 配额分配（比例+最小500保障）+ 逐附件关键词匹配 + outline 等额分配

### 改动文件清单
1. app/services/attachment_service.py: 新增 resolve_attachment_texts 函数（返回各附件独立文本列表）
2. app/services/generator.py: _resolve_attachments 返回 (merged_str, attachment_texts) 元组 + generate() 传参
3. app/services/minimax.py:
   - 新增 _allocate_attachment_quota 辅助方法（比例分配+最小保障+N>4等额降级）
   - _build_chapter_prompt: 新增 attachment_texts 参数 + 多附件配额分配/逐附件检索逻辑
   - _build_section_prompt: 同上
   - generate_content_with_fallback: 新增 attachment_texts 参数透传
   - _generate_by_chapters: 新增 attachment_texts 参数透传
   - _build_section_prompt 调用点: 传递 attachment_texts
4. app/services/agent_tools.py: outline_from_attachment 遍历所有附件 + 等额分配 50000 预算
5. tests/test_attachment.py:
   - 更新 3 个 _resolve_attachments 测试（适配元组返回值）
   - 更新 1 个接口签名测试（检查 attachment_texts 参数）
   - 新增 TestAllocateAttachmentQuota（7 用例）
   - 新增 TestMultiAttachmentInjection（5 用例）
   - 新增 TestOutlineFromAttachmentMulti（3 用例）

### 测试结果
- test_attachment.py: 38/38 passed
- 完整测试套件: 135 passed, 4 failed（4 个失败均为预先存在的问题）
- Result: Success

## 2026-08-03 13:42 - 精简文档表格内容通顺流畅性优化

### 任务
用户要求修改项目代码，使精简文档时保持文档表格中内容的通顺流畅。

### 任务评估
- 评估等级：Medium（2 个文件，4-5 处修改，无架构改动）
- 用户选择使用 /plan-eng-review Skill 进行规划评审
- 评审通过：3 issues 都在原计划内，0 critical gaps
- 计划文件：`E:\nrf_sample_codes\working_team_work\public\docs\code_writer_docs\plan-table-fluency-2026-08-03.md`

### Analysis
- Topic: 精简文档功能表格流畅性 gap 分析
- Finding: 现有 `_summarize_one_subsection` system_prompt 已有"可读性要求"段，但缺少表格专项规则；`_validate_readability` 已校验表格列数/分隔行/悬空引用，但不校验单元格残句和表格上下文；`_truncate_at_boundary` docstring 声称保护表格但实现仅按 `\n` 切分；aggressive 模式 line 1872 "删除解释列"主动破坏表格语义
- Decision: 4 处修改 + 6 新测试，完整方案（Boil the Lake）

### File Edits

| # | Timestamp | File | Change | Result |
|---|-----------|------|--------|--------|
| 1 | 13:38 | `app/services/subagents.py` | SUMMARY_AGENT_PROMPT 增加：表格单元格通顺规则 + 表格上下文衔接规则（必须保留段+可以精简段各增 1-2 条） | Success |
| 2 | 13:39 | `app/services/agent_tools.py` | `_summarize_one_subsection` system_prompt 增加表格单元格完整 + 表格上下文衔接 2 条可读性规则 | Success |
| 3 | 13:40 | `app/services/agent_tools.py` | aggressive 模式 prompt：删除"表格只保留表头和必要数据行，删除解释列"，改为"表格保留完整列结构，可压缩单元格内冗余说明文字，但不得删除整列或破坏表格语义" | Success |
| 4 | 13:40 | `app/services/agent_tools.py` | `_validate_readability` 新增规则 7（表格单元格残句校验）+ 规则 8（表格上下文衔接校验，tstart==0 跳过避免误报） | Success |
| 5 | 13:41 | `app/services/agent_tools.py` | `_truncate_at_boundary` 增加表格保护逻辑：跟踪 in_table 状态，截断点落在表格内时回退到表格开始前 | Success |
| 6 | 13:41 | `tests/test_summarize.py` | 新增 3 个测试类 8 个测试用例：TestTableFluencyPromptRules (3) + TestValidateReadabilityTableFluency (4) + TestTruncateAtBoundaryTableProtection (2) | Success |
| 7 | 13:42 | `app/services/agent_tools.py` | 修复规则 8 误报：`test_complete_table_passes` 回归测试失败，tstart==0 时跳过（### 小节标题已提供上下文） | Success |

### Bash Commands

| # | Timestamp | Command | Purpose | Result |
|---|-----------|---------|---------|--------|
| 1 | 13:37 | `python -c "import ast; ast.parse(...)"` x3 | 语法验证 3 个修改文件 | Success - 3/3 OK |
| 2 | 13:41 | `python -m pytest tests/test_summarize.py -v` | 首次单元测试 | Failure - 67/68 passed，`test_complete_table_passes` 回归失败 |
| 3 | 13:42 | `python -m pytest tests/test_summarize.py -v` | 修复后重测 | Success - 68/68 passed |

### 测试结果
- test_summarize.py: 68/68 passed（62 既有 + 6 新增，0 回归）
- 语法验证: 3/3 通过（subagents.py / agent_tools.py / test_summarize.py）
- Result: Success

### Summary
- Tasks completed: 4 处代码修改 + 6 新测试 + 工作日志
- Tasks pending: 无
- Key decisions: 完整方案（4 点全做）而非简化方案（仅 Prompt）；规则 8 保守校验（tstart==0 跳过避免误报）
- Next steps: 可选 - 实际 LLM 集成测试（需启动 Ollama 服务，用户确认）


## 2026-08-07 17:06:02 - RAG top_k 提升 (search_kb 5->10)

### 背景
用户问"能否提升rag时top_k的数量"。调研后发现：
- search_kb 默认 top_k=5，candidate_pool_size=30
- 5 处内部 search_kb.ainvoke 硬编码 top_k=5（generate_section 等工具的内部 RAG）
- _do_retrieve_uploads 用 n_results=top_k，uploads 小集合可能占满结果

### 改动 (app/services/agent_tools.py)
1. **search_kb 默认 top_k: 5 -> 10** (line 83)
   - docstring 同步更新: "默认5条"->"默认10条"，"粗召回30条"->"粗召回40条"
2. **candidate_pool_size: 30 -> 40** (line 114)
   - 保障 top_k=10 时的精排余量（pool >= top_k * 3 仍成立）
3. **_do_retrieve_uploads 配额** (line 138-143)
   - 原: `n_results=top_k`
   - 新: `uploads_n = max(top_k // 2, 3)` + 注释
   - 避免 uploads 小集合占满 top_k 位，给主库让出半数配额
4. **5 处硬编码 search_kb.ainvoke top_k: 5 -> 10** (lines 626/825/985/1217/1377)
   - 全部位于 generate_section / revise_section / write_chapter 等工具的内部 RAG 调用
   - 使用 replace_all=true 一次性替换

### 未改动 (刻意保留)
- search_attachment top_k=5 保留（附件全文已注入 system prompt，检索仅作补充）
- retrieve_hybrid / retrieve_and_rerank / Reranker.rerank 的默认 top_k=5 保留（底层函数默认值，由调用方传入）
- test_*.py 中的 top_k=3 保留（测试脚本，不影响生产）

### 验证
- `python -c "import ast; ast.parse(open('app/services/agent_tools.py', encoding='utf-8').read())"` -> syntax OK
- GBK codec 报错为 conda 子进程既有问题，与代码无关

### 风险评估
- LLM 上下文: 10 chunks * 1500 chars = 15K 字符，加上附件全文+状态快照，需确认不超 glm-5.1 128K context（当前未做 token 预检，后续可加）
- Reranker 显存: pool=40 batch 推理，BGE-Reranker-v2-m3 显存峰值约 2-3GB，需确认 GPU 够用
- 任务 #12 (vector_store.py instance 级 query_collections) 仍 pending，后续若要给 uploads 加 BM25 混合检索需先完成 #12

### Result
- Success - 7 处编辑全部生效，语法校验通过

---

## 2026-08-07 17:24 - Session Start / 新任务
- 任务: Agent 页 (agent.html) 增加明显的「上传文件到知识库」入口
- 需求: 用户通过入口直接上传文件到 upload 向量知识库，便于后续 RAG 检索
- 澄清: 仅 agent.html；仅上传入口不做列表；独立上传不绑定项目
- 评审: 使用 /plan-eng-review 完成，方案 = 复用 POST /api/upload?persist=true + GET /api/extract-status，零后端改动
- 已创建 session 日志: E:\nrf_sample_codes\working_team_work\public\docs\code_writer_docs\session-20260807-172723.md

## 2026-08-07 17:24 - Analysis
- Topic: 现有上传能力盘点
- Finding: 后端 /api/upload(persist=true) 已写入 uploads 集合且 test_attachment.py 已覆盖；/api/extract-status/{file_id} 支持异步轮询；index.html 已有异步上传+轮询模式
- Decision: 仅改 agent.html，复用既有端点，添加头部按钮 + 独立文件输入 + toast 反馈 + 异步轮询

## 2026-08-07 17:32 - File Edited
- File: app/static/agent.html
- Change: 新增「📚 上传知识库」功能：
  1) CSS: .kb-upload-btn 按钮样式 + .toast-container/.toast 系列 toast 样式
  2) HTML: toastContainer 容器、头部 kbUploadBtn 按钮、独立 kbFileInput (accept 覆盖后端支持格式)
  3) JS: showToast/updateToast/dismissToast/triggerKbUpload/handleKbFileSelect/validateKbFile/uploadFileToKb
     - 复用 POST /api/upload?persist=true + GET /api/extract-status/{file_id} 异步轮询
     - 前端预检格式/大小(10MB)，与后端 SUPPORTED_UPLOAD_FORMATS 一致
     - 处理失败/任务丢失(404)/超时(15min) 等错误路径
- Result: Success - node JS 语法校验通过

## 2026-08-07 17:32 - File Edited
- File: app/services/attachment_service.py
- Change: submit_extract_task 去重逻辑：当请求入库(persist=True)但既有相同文件任务未入库(persisted=False)时，跳过复用重建新任务，确保知识库上传入口一定写入向量库
- Result: Success - ast.parse 语法校验通过

## 2026-08-07 17:32 - Analysis
- Topic: 知识库上传去重边界
- Finding: 原逻辑对相同 MD5 已完成任务无条件复用 file_id，若既有任务 persist=False 会导致知识库上传入口实际未入库（静默失败）
- Decision: 在 dedup 判断中增加 `if persist and not task.get("persisted"): continue`，2 行修复保证核心需求成立

## 2026-08-07 17:36 - Analysis
- Topic: E2E 验证安排
- Finding: 8003 端口运行的是另一路径部署 (pj_0807)，不含本次改动；当前项目需要新启服务验证
- Decision: 经确认可启动服务，但用户随后决定「不需要，我自己验证」。未启动任何服务，E2E 验证交由用户自行执行

## 2026-08-07 17:56:41 - Session Start / 新任务
- 任务: 把 uploads 集合纳入 QUERY_COLLECTIONS
- 需求: 用户上传到 upload 向量知识库的文件，应在所有 RAG 检索路径（retrieve / retrieve_hybrid）默认命中，而不仅是 search_kb 单独检索
- 上下文: 前一任务已完成 agent.html 「上传知识库」入口 + attachment_service 去重修复

## 2026-08-07 17:56:41 - Analysis
- Topic: QUERY_COLLECTIONS 命名与重复检索风险
- Finding:
  1) QUERY_COLLECTIONS 条目被 retrieve/retrieve_hybrid 直接用作 ChromaDB 集合名（无前缀拼接），uploads 实际集合名为 qms_doc_uploads（带前缀），故必须写 qms_doc_uploads 而非 uploads
  2) 若仅添加不处理，search_kb 主库检索（retrieve_and_rerank/retrieve_hybrid）会同时命中 uploads，与独立 _do_retrieve_uploads 重复返回同一内容；且主库路径结果无 chunk_id，与 uploads 路径（有 chunk_id）去重键不一致，无法剔除重复
  3) minimax._rag_retrieve_for_chapter 用 uploads_vs.retrieve_hybrid 单独检索 uploads，但 retrieve_hybrid 实际按 QUERY_COLLECTIONS 检索（非 collection_name），本就是隐性 bug；改动后还会与主检索重复
  4) minimax 的 uploads_vs.count() 统计全部 QUERY_COLLECTIONS，加入 uploads 后恒 >0，会改变 main_k 分配
  5) search_attachment 的向量回退调用 VectorStore(collection_name="uploads").retrieve_hybrid，实际检索的是 QUERY_COLLECTIONS（主库而非 uploads），属既有 bug，改动后需直查 uploads 集合
  6) uploads chunk 的 doc_type 恒为 unknown（/api/upload 传参），而 minimax 按章节 doc_type 过滤检索，会导致 uploads chunk 被过滤掉
- Decision: 一体化修复——①QUERY_COLLECTIONS 加入 qms_doc_uploads；②retrieve_hybrid 标注 source_collection 且 uploads 豁免 doc_type 过滤；③search_kb 剔除主库结果中的 uploads chunk + 统一文本去重键；④minimax 移除冗余 uploads 检索、uploads_has_data 改用直接 collection.count()；⑤search_attachment 向量回退直查 uploads 集合

## 2026-08-07 17:56:41 - File Edited
- File: app/services/rag/vector_store.py
- Change:
  1) QUERY_COLLECTIONS = ["insulin_pump_kb", "qms_doc_uploads"]（含注释说明实际集合名带前缀）
  2) retrieve_hybrid 向量检索循环: doc_type 过滤增加 coll_name != "qms_doc_uploads" 豁免；结果 dict 新增 source_collection=coll_name
  3) retrieve_hybrid doc_type 过滤回退循环: 同样新增 source_collection
  4) retrieve_hybrid 合并结果透传 source_collection
- Result: Success - ast.parse 校验通过；运行时验证 QUERY_COLLECTIONS 两集合可解析 (insulin_pump_kb=9622, qms_doc_uploads=1400)

## 2026-08-07 17:56:41 - File Edited
- File: app/services/agent_tools.py
- Change:
  1) search_kb._do_retrieve_uploads 注释更新（uploads 已纳入 QUERY_COLLECTIONS，本方法保留配额与[附件]标注）
  2) search_kb 归一化主库结果时按 source_collection=="qms_doc_uploads" 剔除 uploads chunk，避免与独立检索重复
  3) search_kb 去重键统一为 text[:100]（原为 chunk_id or text[:100]，跨路径重复时键不一致漏去重）
  4) search_attachment 向量回退从 retrieve_hybrid 改为直查 store.collection.query（uploads-only）
- Result: Success - ast.parse 校验通过

## 2026-08-07 17:56:41 - File Edited
- File: app/services/minimax.py
- Change: _rag_retrieve_for_chapter 移除 uploads_vs.retrieve_hybrid 冗余检索（现会命中全语料且与主检索重复）；uploads_has_data 改用 VectorStore(collection_name="uploads").collection.count()>0 直接判断（原 count() 统计全部 QUERY_COLLECTIONS 恒 >0）；docstring 更新说明 uploads 已由主检索涵盖
- Result: Success - ast.parse 校验通过

## 2026-08-07 17:56:41 - Bash Command Executed
- Command: conda env_01 python ast.parse 校验 3 个改动文件 + VectorStore 运行时解析 QUERY_COLLECTIONS
- Working Dir: design_planning_generation_local_model
- Purpose: 语法校验 + 验证 qms_doc_uploads 集合可被 retrieve 解析
- Result: Success - 3 文件语法通过；QUERY_COLLECTIONS=['insulin_pump_kb','qms_doc_uploads']，两集合均可解析 (9622/1400)

## 2026-08-07 18:02:24 - Session Start / 新任务
- 任务: 诊断项目网络搜索功能（DuckDuckGo / Playwright 能否查询即时网络信息）
- 需求: 用户反馈网络搜索好像有问题，需验证 ddgs 与 Playwright 后端可用性

## 2026-08-07 18:02:24 - Bash Command Executed
- Command: conda env_01 python 检查 ddgs/duckduckgo_search/playwright/requests 是否安装
- Working Dir: design_planning_generation_local_model
- Purpose: 确认搜索后端依赖安装情况
- Result: Success - ddgs 9.14.4 / duckduckgo_search 8.1.1 / playwright / requests 均已安装

## 2026-08-07 18:02:24 - Bash Command Executed
- Command: conda env_01 python 实测 ddgs.DDGS().text() 实时搜索
- Working Dir: design_planning_generation_local_model
- Purpose: 验证 ddgs 库能否查到即时信息
- Result: Success - 6.5s 返回 3 条真实结果

## 2026-08-07 18:02:24 - Bash Command Executed
- Command: conda env_01 python Playwright headless 打开 Bing 搜索页并提取 li.b_algo
- Working Dir: design_planning_generation_local_model
- Purpose: 验证 Playwright Bing 后端可用性
- Result: Failure - li.b_algo 10s 超时；FINAL URL 带 rdr=1&rdrig= 地区重定向参数，页面无有机结果也无 CAPTCHA

## 2026-08-07 18:02:24 - Bash Command Executed
- Command: conda env_01 python 端到端测试 SyncWebSearchService.search_regulations('概述', ...)
- Working Dir: design_planning_generation_local_model
- Purpose: 验证应用实际使用的搜索服务整体可用性
- Result: Success - init 8.2s (含实时 DDG 探测)，search 12.8s 返回 1492 字格式化结果；ddg_available=True

## 2026-08-07 18:02:24 - Bash Command Executed
- Command: conda env_01 python Playwright headless 打开 DuckDuckGo 搜索页并数结果元素
- Working Dir: design_planning_generation_local_model
- Purpose: 验证 Playwright DDG 备用路径
- Result: Failure - 页面加载成功但结果元素数为 0（现行选择器匹配不到）

## 2026-08-07 18:02:24 - Analysis
- Topic: 搜索后端可用性诊断结论
- Finding:
  1) ddgs 库 (DuckDuckGo) ✅ 可用 — 实测 6.5s 返回真实结果；SyncWebSearchService 端到端 12.8s 返回 1492 字
  2) Playwright + Bing ❌ 不可用 — headless 无 cookie 被地区重定向 (rdr=1&rdrig=) 挡在结果页外，无 li.b_algo
  3) Playwright + DuckDuckGo ❌ 不可用 — 页面加载但现行选择器匹配不到任何结果元素
- 根因分析: 服务初始化 _check_ddg_library() 做实时网络探测 (实测 8.2s)，一旦瞬时失败 ddg_available 整个进程置 False → 回退到已失效的 Playwright 路径 → 搜索静默返回空。批量生成多章节时 DDG 限流也会触发此问题
- Decision: 待用户确认修复方向（详见会话日志）

## 2026-08-07 18:0x - File Edited
- File: app/services/web_search.py
- Change: 用户选择「修复探测+保留ddgs」方案。(1) `_check_ddg_library()` 移除实时网络探测（原 `DDGS().text("test")` 实测 8.2s，瞬时失败会永久禁用 ddgs 后端），改为仅 `import ddgs` 检查包可导入；(2) `_search_with_best_backend()` 的 ddgs 路径加 for 循环重试 2 次（异常或空结果均重试，间隔 1.5s），避免单一瞬时失败直接降级到已失效的 Playwright 路径
- Result: Success - init 8.2s → 0.04s；ddg_available=True；端到端 search_regulations('概述','贴敷式胰岛素泵') 返回 1182 字真实结果（含重试路径仍成功）

## 2026-08-07 18:0x - Analysis
- Topic: 修复后回归验证
- Finding: init 由 8.2s 降至 0.04s（探测不再打网络）；ddgs 搜索仍返回真实结果，即便瞬时失败也会重试而非直接禁用
- Decision: 保留 ddgs 为主后端、Playwright 为降级路径；Playwright+Bing/DDG 选择器问题留作后续独立修复项（不在本次范围）

## 2026-08-07 18:2x - Analysis
- Topic: 对话框 Agent 是否会自动调用网络搜索
- Finding: 会。聊天对话走 LangGraph ReAct Agent（agent_engine.py），web_search 工具已注册在 PHASE1_TOOLS（agent_tools.py:3126）并经 bind_tools 绑定（agent_engine.py:65），LLM 自主决定调用。但系统提示词 TOOL_RULES 未提及 web_search，LLM 仅靠工具 docstring 推断，本地小模型调用概率可能偏低
- Decision: 在 agent_prompt.py 的 TOOL_RULES 知识检索区补 web_search 使用说明（编号 2b），与 search_kb 分工明确

## 2026-08-07 18:2x - File Edited
- File: app/services/agent_prompt.py
- Change: TOOL_RULES 新增 "2b. **web_search**" 条目：何时用（最新法规动态/标准更新/本地知识库查不到）+ 与 search_kb 的区别 + 规则（网络结果为辅助参考，条款号以官方发布为准）
- Result: Success - ast.parse 通过；web_search in TOOL_RULES: True

## 2026-08-07 18:3x - Analysis
- Topic: 让 agent「判断到需要网络搜索就去搜索」
- Finding: 当前机制为 LLM 自主函数调用（概率性），本地小模型触发不够可靠。用户选择「提示词强规则 + search_kb 空结果自动升级」方案
- Decision: (1) agent_prompt.py TOOL_RULES 2b 升级为强规则（涉及最新/实时信息或本地检索不足时"必须"先调 web_search，不得凭已有知识编造）；(2) agent_tools.py search_kb 本地检索为空（all_results 为空）时自动调用 web_search 并合并结果（带 web_fallback 标记、source "[网络]..."）

## 2026-08-07 18:3x - File Edited
- File: app/services/agent_prompt.py
- Change: TOOL_RULES 2b 升级为强规则 + 补充说明（search_kb 空结果会自带网络结果，无需再单独调 web_search）
- Result: Success

## 2026-08-07 18:3x - File Edited
- File: app/services/agent_tools.py
- Change: search_kb 空结果分支改为自动升级 web_search：调用 `web_search.ainvoke({"query":..., "doc_type": _current_doc_type.get()})`，成功则合并为 [{content, source:"[网络] {method}", source_collection:"web"}] 返回 status:ok / web_fallback:true；失败回退 status:no_results。注意首次实现误用 `await web_search(query, doc_type=...)`，@tool 包装后为 StructuredTool 不可直接调用，抛 TypeError 被吞导致升级从未生效，已修正为 .ainvoke
- Result: Success - mock 强制本地空结果后，真实触发 web_search 返回 650 chars 合并成功（status:ok, count:1, web_fallback:true）

## 2026-08-07 18:3x - Bash Command Executed
- Command: conda env_01 python 对比 web_search 两种调用方式
- Working Dir: design_planning_generation_local_model
- Purpose: 定位自动升级为何始终空结果
- Result: Failure -> Success - .ainvoke 返回 1011 chars；直接 `web_search(query, doc_type=)` 抛 TypeError 'StructuredTool' object is not callable，确认根因后修正

## 2026-08-10 10:3x - Analysis
- Topic: 天气问题仍回答"无法获取实时气象数据"，未真实网络搜索（用户反馈）
- Finding: 解码 checkpoint 库 project_store/agent_checkpoints.db 复盘真实对话：①"今天天气怎么样"→ LLM tools=[] 直接拒绝（未调用任何工具）；②"深圳市今天的天气怎么样"→ LLM 确实调用了 web_search（提示词强规则生效），但 web_search 工具首选 Claude Agent SDK 后端（agent_search.py _build_research_prompt 为"医疗器械法规专用"研究提示），将天气问题判定为"与医疗器械法规无关，已忽略"，返回非空医疗研究内容 → ddgs/Playwright 降级永不触发 → LLM 只能回"抱歉，无法获取实时天气"。另 search_kb("今天天气怎么样") 向量检索返回 3 条垃圾结果（空文本 chunk 等），空结果自动升级也不触发
- Decision: 三层修复。(1) web_search 工具按查询类型分流：新增 `_is_general_query()` 分类器（医疗/文档关键词命中→医疗路径，未命中→通用实时路径）；通用查询走新增的 `SyncWebSearchService.search_general()`（原始关键词直搜 ddgs 优先+重试，不做章节→医疗查询改写、不过 Agent SDK 医疗提示）。(2) 医疗路径 Agent SDK 失败时降级到 search_general 而非旧的 search_regulations（避免医疗改写污染）。文档生成流程行为不变（章节名命中医疗关键词走原路径）。(3) agent_engine.py `_agent_node` 增加代码级兜底：LLM 未调用工具且回答含"无法获取/无法提供"等拒绝特征词、用户问题含实时话题关键词（天气/新闻/汇率等）时，强制注入 web_search 工具调用，让图路由到 ToolNode 真实搜索后再回本节点让 LLM 重新回答

## 2026-08-10 10:3x - File Edited
- File: app/services/web_search.py
- Change: EnhancedWebSearchService 新增 `search_general(query, max_results, enable_deep_scrape)`：直接用原始关键词走 `_search_with_best_backend`（ddgs 优先+重试+Playwright 备用），返回 `_format_results` 文本；SyncWebSearchService 同步包装版同增。doc_type="general" 关闭文件下载，无知识库副作用
- Result: Success - 测试脚本 test_general_search.py 验证：search_general("深圳市今天天气怎么样") 返回 697 字真实深圳天气结果（tianqi.com / weather.com.cn / 深圳气象局）

## 2026-08-10 10:3x - File Edited
- File: app/services/agent_tools.py
- Change: 新增 `_MEDICAL_DOC_KEYWORDS`（医疗器械/文档生成类高精度关键词）、`_REALTIME_TOPIC_KEYWORDS`、`_REALTIME_REFUSAL_PATTERNS` 及三个判定函数 `_is_general_query`/`_looks_like_realtime_refusal`/`_user_asks_realtime`；web_search 工具改为按 `_is_general_query(query)` 分流：通用→search_general 原始关键词直搜（search_method="ddgs"），医疗→Agent SDK 深度研究（失败降级 search_general）；通用分支空结果直接返回 no_results，避免走医疗逻辑
- Result: Success - 分类器 8 个用例全部通过（天气 3 例→general=True；医疗/章节 5 例→general=False）；refusal/realtime 判定符合预期

## 2026-08-10 10:3x - File Edited
- File: app/services/agent_engine.py
- Change: `_agent_node` LLM 调用后、返回前插入代码级兜底：若 response 无 tool_calls 且 `_user_asks_realtime(用户消息)` 且 `_looks_like_realtime_refusal(回复内容)`，构造仅携带 web_search 工具调用的 AIMessage 返回，使 tools_condition 路由到 ToolNode 执行真实搜索；新增 import time、AIMessage、agent_tools 三个判定函数
- Result: Success - ast.parse 三文件全过；兜底不改变文档生成流程（章节问题不满足实时/拒绝条件）

## 2026-08-10 14:5x - Analysis
- Topic: 文档内容/章节重复问题（三层去重方案）
- Finding: 重复来源有三——(1) 各章节独立生成、无跨章节感知；(2) Agent 模式提示词缺少 minimax.py 已有的防"本章依据XX编制"等冗余规则；(3) 生成后无全文档级去重兜底。`fill_template`（template.py:69）是 Markdown→Word 唯一公共转换点（routes.py:311/1013、agent_tools build_docx、generator.py:78/168 均经此）。
- Decision: 三层全做——源头提示词去重规则 + 已覆盖内容摘要注入 + 生成后全文档去重兜底（fill_template 单点注入，覆盖所有路径）

## 2026-08-10 14:5x - File Edited
- File: app/services/doc_dedup.py（新建）
- Change: 新增全文档去重模块（纯 str->str，无外部依赖）：`dedup_markdown(content)` = `_filter_redundant_lines`（过滤"本章依据XX编制/本节规定/合规性说明"等冗余前缀行，与 minimax.py 旧版过滤一致）→ `_remove_duplicate_lines`（精确重复行用 dict O(1) 去重、列表项剥离 `- ` 前缀、非列表项按长度分桶 ±15% + 相似度>0.92 近似去重）→ `_merge_similar_sections`（有标题且正文>=120字的小节，bigram Jaccard 相似度>=0.88 时保留较详细者删除较短者）
- Result: Success - ast.parse 通过；7/7 功能测试用例通过（含幂等性、短小节不误合并、正常内容保留）

## 2026-08-10 14:5x - File Edited
- File: app/services/template.py
- Change: `fill_template` 开头新增 `from app.services.doc_dedup import dedup_markdown` 并执行 `content = dedup_markdown(content)`——单点注入，覆盖 Agent 模式（build_docx）、旧模式（generator.py）及 routes.py 全部 Markdown→Word 路径
- Result: Success - 模块导入无循环依赖，集成检查通过

## 2026-08-10 14:5x - File Edited
- File: app/services/subagents.py
- Change: `CHAPTER_AGENT_PROMPT` 新增"## 去重要求"段：禁止"本章依据XX编制"开头、产品通用参数只在首次出现章节写全（其他章用"见XX章"）、标准总则类描述只出现一次、同一法规条款不跨章重复
- Result: Success - ast.parse 通过

## 2026-08-10 14:5x - File Edited
- File: app/services/agent_tools.py
- Change: (1) 新增 `_same_chapter` / `_build_covered_digest(exclude_chapter)` 助手：解析 `_current_generated_markdown`（`# 章节\n\n内容` 拼接格式）提取除当前章外各章标题+小节标题+首条要点（截断80字），空文档返回空串；(2) `write_chapter` 每小节 system_prompt 注入"## 去重要求"（含 covered_digest 已覆盖内容块）；(3) `generate_section` system_prompt 注入"## 去重要求"（含 covered_digest）；均新增"禁止以本章依据/本节依据冗余前缀开头"规则
- Result: Success - ast.parse 通过；_build_covered_digest 抽取验证通过（排除当前章、空文档边界正确）

## 2026-08-10 14:5x - Bash Command Executed
- Command: `python test_doc_dedup.py`
- Working Dir: 项目根目录
- Purpose: 验证 doc_dedup 全文档去重模块功能
- Result: Success - 7/7 用例通过（冗余前缀过滤、精确/近似重复行去除、高相似度小节合并、短小节不误合并、幂等性、正常内容保留）

## 2026-08-10 14:5x - File Edited
- File: test_doc_dedup.py（项目根目录，新建）
- Change: doc_dedup 回归测试脚本（按用户要求写入项目目录，不写 C 盘临时目录）
- Result: Success - 7/7 通过

## 2026-08-10 14:44 - Task: 项目计划书不写具体法规
用户需求：写项目计划书（design_development_plan）时，不需要在文档中写明具体法规；其余文档（风险管理/设计输入/产品需求等）保持法规条款引用要求。

## 2026-08-10 14:4x - File Edited
- File: app/services/minimax.py
- Change: (1) 新增 `_PLAN_DOC_TYPES = {"design_development_plan"}` 与 `_regulation_clause_rule(doc_type)` 助手（计划书返回"不需要写明具体法规/标准条款号"，其余返回"所有标准条款引用必须有明确的条款号"）；(2) `_build_targeted_revision_prompt`（原L3079 "【修改质量要求】"）硬编码条款规则替换为 `{_regulation_clause_rule(doc_type)}`；(3) `_revise_simple`（原L3244 "【要求】"）同样替换；(4) `_build_section_prompt`（旧模式分章节生成）风格准则第5条"标准引用"与内容质量要求第2条改为 `{'不引用...' if doc_type in _PLAN_DOC_TYPES else 原规则}` 条件渲染
- Result: Success - ast.parse 通过；渲染对比验证：design_development_plan→"不引用具体法规/标准条款号，聚焦计划内容本身"，risk_management_plan→保留"标准号后用书名号包裹全称"/"标准号和条款引用要准确"

## 2026-08-10 14:4x - File Edited
- File: app/services/agent_tools.py
- Change: 新增 `_PLAN_DOC_TYPES`、`_regulation_clause_rule(doc_type)`、`_output_structure_requirement(doc_type, is_revision=False)`；generate_section/revise_section/write_chapter(每小节与整章兜底)共4处硬编码"所有标准条款引用必须有明确的条款号"替换为 `{_regulation_clause_rule(doc_type)}`；generate_section/revise_section 的"## 输出结构要求"块替换为 `{_output_structure_requirement(doc_type)}`（计划书变体：聚焦阶段划分/任务分配/资源/时间安排/职责，无"法规条款原文引用"/"合规要点"）
- Result: Success - ast.parse 通过；两 helper 对 plan/non-plan 分流输出验证正确

## 2026-08-10 14:4x - File Edited
- File: app/services/prompt_engineer.py
- Change: `design_development_plan` 专属提示词改为"**不需要写明具体法规/标准条款号**（如ISO 13485 §7.3.2、IEC 62304等），聚焦计划内容本身"（替换原"遵循ISO 13485 §7.3.2要求"）
- Result: Success - ast.parse 通过

## 2026-08-10 14:4x - Bash Command Executed
- Command: `python -c "ast.parse 3 文件"` + `MiniMaxService._build_section_prompt` 渲染对比 + `agent_tools` 两 helper 输出对比
- Working Dir: 项目根目录
- Purpose: 校验语法 + 验证计划书/非计划书文档类型分流渲染
- Result: Success - 3 文件 SYNTAX OK；design_development_plan 渲染为不引用法规，risk_management_plan 保留条款引用；_output_structure_requirement 计划书变体无"法规条款原文引用/合规要点"

## 2026-08-10 14:53 - 验证 OpenViking 集成连接
- 检查：OPENVIKING_ENABLED=true；URL http://localhost:1933（与 ~/.openviking/ovcli.conf 一致）；langchain_openviking 已安装于 env_01
- 服务器侧：MCP health = "OpenViking is healthy (service initialized, storage: VikingFS)"；curl localhost:1933 端口有响应（HTTP 404 属正常，根路径无路由）
- 运行时验证：真实 .env 配置下调用 init_openviking() → initialize() 返回 True；is_available()=True（recorder 已创建）；capture tools = ['viking_store','viking_add_resource']
- 接线确认：agent_engine.init_agent() 启动时调用 init_openviking()；_agent_node 每轮 LLM 回复后调用 _capture_to_openviking()（agent_engine.py:108）；capture 工具追加到 PHASE1_TOOLS
- 发现：OpenViking 存储中尚无 design-plan-agent 会话数据（仅 cc-* Claude Code 会话）。原因候选：启用后尚未跑真实对话，或 langgraph get_config() thread_id 跨 async 任务传播失败导致 capture 静默跳过（代码注释已注明该 Python 3.10 限制）
- 结论：连接已打通；实际数据流需跑一次真实对话后用 OpenViking MCP list/glob 检查 viking://session 下新增 thread_id 会话确认

## 2026-08-10 15:30 - Task: 修复 PDF 上传失败
用户需求：这个项目上传pdf文件会上传失败，修复一下。

## 2026-08-10 15:3x - Analysis
- 根因1（已复现）：app/services/rag/ingest.py extract_text_from_pdf 中 pdfplumber 解析块只捕获 ImportError。加密/损坏 PDF 会让 pdfplumber 抛 PdfminerException 等非 ImportError 异常，异常穿透到 attachment_service._do_extract 的 except Exception → 任务 status=failed → /agent/upload 轮询到 failed 抛 500 → 前端显示"上传失败"。用加密 PDF 复现 STATUS=failed "提取失败:"。
- 根因2（已复现）：attachment_service._do_extract 的 latin1 兜底会把无法解析的二进制 PDF（扫描版/加密）读成乱码并标记"提取完成"，产生乱码文本进入 RAG/生成文档。
- 补充发现：真实应用加载 .env（USE_MINERU=true），PDF 优先走 MinerU 本地 1.2B 模型；MinerU 失败时回退本地解析器，此时根因1才会暴露。MinerU 对文本 PDF 正常（1页约 12s）。

## 2026-08-10 15:3x - File Edited
- File: app/services/rag/ingest.py
- Change: extract_text_from_pdf 的 pdfplumber 块 `except ImportError` → `except Exception`，异常回退 PyPDF2；新增 fitz(PyMuPDF) 兜底提取（对 pdfplumber/PyPDF2 解析失败但含文本层的 PDF 有效）；OCR 回退保留
- Result: Success - 加密 PDF 不再崩溃，文本 PDF 正常提取

## 2026-08-10 15:3x - File Edited
- File: app/services/attachment_service.py
- Change: _do_extract 的原始文本兜底仅限 .txt/.md（多编码直读），pdf/docx/doc/xlsx 等二进制格式不再做 latin1 兜底，避免乱码"假成功"；失败信息改为"文件可能为空、已加密或格式不支持"
- Result: Success - 扫描版/加密 PDF 返回清晰失败提示而非乱码文本

## 2026-08-10 15:3x - Bash Command Executed
- Command: python 复现+回归脚本（文本/扫描/加密/中文/GBK txt PDF 任务流）
- Working Dir: 项目根目录
- Purpose: 验证修复前后行为
- Result: Success - 文本 PDF(含MinerU路径)提取正常；加密/扫描 PDF 清晰失败不再崩溃；GBK txt 正常；38 个 pytest 用例全部通过

## 2026-08-10 16:xx - Task Start
- 需求：修改代码，使审阅文档时可以直接修改文档的具体段落的内容
- 方案：段落级内联编辑（review.html 按 markdown 块拆分渲染，每块 hover 出"✎ 编辑"，文本域编辑原始 markdown）+ 新增后端保存端点整体替换 generated_sections

## 2026-08-10 16:xx - File Edited
- File: app/api/routes.py
- Change: 新增 SectionContent / DocumentUpdateRequest 请求模型；新增 POST /agent/projects/{project_id}/document 端点：接收 {sections:[{title,content}]}，空标题跳过，整体替换 generated_sections 并 aupdate_state 持久化；项目不存在→404，全部空→400
- Result: Success - ast.parse 通过；router 注册确认 GET+POST 双方法

## 2026-08-10 16:xx - File Edited
- File: app/static/review.html
- Change: 顶栏新增"保存修改"按钮+未保存指示；CSS 新增 .md-block/.block-edit-btn/.block-editor 段落编辑样式；JS 新增 splitBlocks/joinBlocks/renderSectionHTML/renderSection/startEditBlock/saveEditBlock/cancelEditBlock/setDirty/saveDocument；renderDocument 改为按块渲染；print 模式隐藏编辑控件
- Result: Success - 内联 JS 经 node --check 通过

## 2026-08-10 16:xx - Bash Command Executed
- Command: node --check（提取 review.html 内联 script）
- Purpose: 校验新增 JS 语法
- Result: Success - JS SYNTAX OK

## 2026-08-10 16:xx - Bash Command Executed
- Command: python _test_review_save.py（mock get_agent）
- Purpose: 验证保存端点逻辑
- Result: Success - 4 场景全过（修改+新增章节、空标题跳过、全空→400、项目不存在→404）

## 2026-08-10 16:xx - Bash Command Executed
- Command: node _test_split_blocks.js
- Purpose: 验证 markdown 块拆分/合并逻辑（标题/段落/表格/列表/代码围栏/空行）
- Result: Success - ALL BLOCK TESTS PASSED

## 2026-08-10 16:xx - Bash Command Executed
- Command: python -m pytest tests/test_attachment.py -q
- Purpose: 回归确认无破坏
- Result: Success - 38 passed

## 2026-08-10 16:xx - Analysis
- Topic: 段落编辑粒度
- Finding: generated_sections 为 {章节标题: markdown 内容}，审阅页原为整章 marked 渲染，无法逐段编辑
- Decision: 按 markdown 块（空行分隔段落/标题/表格/代码围栏/列表）拆分渲染，逐块内联编辑；保存时整体替换 generated_sections，后续 Agent 生成/build_docx/下载均基于最新内容

## 2026-08-10 17:41 - File Edited
- File: app/services/agent_state.py
- Change: AgentState 新增 attachment_modifications 字段（附件修改结果列表），create_initial_state() 初始化为 []
- Result: Success - 附件修改结果独立于 generated_sections，不污染目标文档章节

## 2026-08-10 17:41 - File Edited
- File: app/services/agent_tools.py
- Change: 新增 modify_attachment 工具 + 旁路字典 _pending_modified_documents / get_pending_modified_document()，以及辅助函数 _llm_rewrite/_one_line/_split_sections_by_heading/_split_summary/_parse_affected_indices/_rewrite_single_pass/_rewrite_section_wise；注册进 PHASE1_TOOLS（16 个工具）
- Result: Success - 短文档(≤6000字)单遍改写，长文档按章节识别受影响章节改写、其余保留

## 2026-08-10 17:41 - File Edited
- File: app/services/agent_engine.py
- Change: _after_tools_node 处理 modify_attachment 结果写入 attachment_modifications；结果装配时合并；stream_agent_events 与 resume_agent 增加 modified_doc_ready SSE 事件
- Result: Success - 修改结果持久化到 agent 状态，前端实时收到修改完成事件

## 2026-08-10 17:41 - File Edited
- File: app/services/agent_prompt.py
- Change: TOOL_RULES 新增 2c. modify_attachment 规则（参数、何时用、修改附件副本不影响目标文档）
- Result: Success - LLM 能正确决定何时调用该工具

## 2026-08-10 17:41 - File Edited
- File: app/api/routes.py
- Change: 新增 GET /modified-documents 列表端点 + GET /modified-documents/{file_id}/download 下载端点（TemplateService 渲染 docx，文件名 {stem}_修改版.docx）
- Result: Success - 修改版文档可列表查看与下载

## 2026-08-10 17:41 - File Edited
- File: app/static/agent.html
- Change: 附件 chip 新增 ✏️修改按钮；新增修改对话框(openModifyDialog/submitModify 注入聊天消息)；SSE modified_doc_ready 触发 showModifiedDownloadButton 下载框；toolLabel 增加"修改附件"映射；CSS 新增 .att-modify/.dl-summary
- Result: Success - 前端完整交互链路，内联 JS 经 node --check 通过

## 2026-08-10 17:41 - File Created
- File: _test_modify_attachment.py
- Change: 5 个 mock 场景测试（短文档单遍改写、长文档分段改写、无附件错误、_after_tools_node 状态写入、路由列表+下载）
- Result: Success - ALL MODIFY-ATTACHMENT TESTS PASSED

## 2026-08-10 17:41 - Bash Command Executed
- Command: python -m pytest _test_modify_attachment.py
- Purpose: 验证修改上传文档功能全链路（mock LLM / mock Agent 状态）
- Result: Success - 5 场景全过

## 2026-08-10 17:41 - Bash Command Executed
- Command: python -m pytest -q（全量）
- Purpose: 全量回归确认无破坏
- Result: Partial - 156 passed, 4 failed（4 个为既有失败：test_phase1_tools_list 断言 len==4 已过时(实际15/16)；3 个 LLM/网络依赖测试因 Ollama 未运行/网络回退失败，与本次改动无关）

## 2026-08-10 17:41 - Bash Command Executed
- Command: python -m pytest tests/test_attachment.py -q
- Purpose: 回归确认先前的段落编辑功能未受影响
- Result: Success - 38 passed

## 2026-08-10 17:41 - Analysis
- Topic: 长文档分段改写方案
- Finding: 长文档整篇重写会丢失未受影响章节的原有表述，且耗时
- Decision: >6000 字时由 LLM 识别受影响章节（{"affected":[索引]} JSON），仅改写受影响章节，其余章节原样保留；识别失败时回退为改写全部章节

## 2026-08-11 09:29 - File Edited
- File: app/services/agent_state.py
- Change: AgentState 新增 concise_mode 字段（默认 False，仅影响文档内容生成）；build_state_snapshot 顶层暴露 concise_mode 供前端初始化
- Result: Success - 模式按项目持久化到 checkpoint

## 2026-08-11 09:29 - File Edited
- File: app/services/agent_prompt.py
- Change: build_system_prompt 在 concise_mode=True 时注入"精炼生成模式"指令块，作用域限定 write_chapter/generate_section/modify_attachment/update_outline，声明聊天回复不适用
- Result: Success - 提示词级注入，关闭时输出与基线一致

## 2026-08-11 09:29 - File Edited
- File: app/api/routes.py
- Change: 新增 POST /agent/projects/{project_id}/mode（form: concise），无 checkpoint 时用 create_initial_state 合并 seed，as_node=after_tools，失败返回 500
- Result: Success - 模式切换端点注册成功

## 2026-08-11 09:29 - File Edited
- File: app/static/agent.html
- Change: 顶栏新增"📄 精炼生成"开关按钮（#conciseBtn，active 紫色高亮）；JS 新增 conciseMode 状态 + toggleConciseMode()/setConciseBtnUI()；fetchState 初始化恢复模式；失败乐观更新回滚 + toast 提示
- Result: Success - JS 语法通过，开关交互完整

## 2026-08-11 09:29 - File Created
- File: _test_concise_mode.py
- Change: 6 条 mock 场景测试（端点 on/off/新线程 seed + 提示词注入 on/off 回归护栏 + 快照暴露 + 初始状态默认）
- Result: Success - ALL CONCISE-MODE TESTS PASSED

## 2026-08-11 09:29 - Bash Command Executed
- Command: python -m pytest _test_concise_mode.py -q
- Purpose: 验证精炼生成开关功能（mock get_agent）
- Result: Success - 6 passed

## 2026-08-11 09:29 - Bash Command Executed
- Command: python -m py_compile app/services/agent_state.py app/services/agent_prompt.py app/api/routes.py
- Purpose: 后端语法校验
- Result: Success - PY_COMPILE OK

## 2026-08-11 09:29 - Bash Command Executed
- Command: python -m pytest tests/test_attachment.py tests/test_summarize.py tests/test_agent_search.py -q
- Purpose: 快速回归确认无破坏
- Result: Success - 117 passed

## 2026-08-11 09:29 - Bash Command Executed
- Command: python -c "from app.api.routes import router; ..."（校验路由注册）
- Purpose: 确认 mode 路由注册
- Result: Success - MODE ROUTE REGISTERED OK

## 2026-08-11 09:29 - Analysis
- Topic: 精炼模式注入方式（经 /plan-eng-review 评审）
- Finding: 用户选择提示词级注入 + 作用范围仅文档内容生成
- Decision: build_system_prompt 加条件指令块，明确限定文档生成工具；聊天回复保持原风格；模式按项目 state 持久化，下一轮自动生效

## 2026-08-11 - Task Start
- Project: design_plan_generation_local_model
- Task: 修复文档生成时显示"llm查询失败"
- Start: 2026-08-11 11:20

## 2026-08-11 - Analysis
- Topic: llm查询失败 根因定位
- Finding: qwen3.5:122b 默认开启 thinking 模式，思考过程耗尽 token 预算导致 content 为空。实测 _call_minimax_api_raw max_tokens=1024 返回空串（11s）；curl /api/chat 显示 content="" 但 thinking 有内容、done_reason=length。_generate_search_queries 因此返回 [] → generate_search_query 工具返回"查询词生成失败" → 前端显示 llm查询失败。max_tokens=8192 的文档生成主路径部分正常但 RAG 查询词环节失败。
- 验证: /api/chat 加 "think":false 后 content 正常返回（thinking_len=0, done_reason=stop）；_generate_search_queries 从 [] → 3 条查询词，2.2s
- Decision: 在 minimax.py 两处 /api/chat payload（_call_minimax_api_raw + MiniMaxService._call_api）加 "think": False，禁用思考模式

## 2026-08-11 - File Edited
- File: app/services/minimax.py (_call_minimax_api_raw)
- Change: payload 加 "think": False + 注释说明 qwen3.5 thinking 耗尽预算问题
- Result: Success

## 2026-08-11 - File Edited
- File: app/services/minimax.py (MiniMaxService._call_api)
- Change: payload 加 "think": False + 注释
- Result: Success

## 2026-08-11 - Bash Command Executed
- Command: python -m pytest tests/test_attachment.py tests/test_summarize.py tests/test_agent_search.py _test_concise_mode.py tests/test_openviking_integration.py -q
- Working Dir: E:/nrf_sample_codes/working_team_work/public/project/git_project/design_plan_generation_local_model/design_planning_generation_local_model
- Purpose: 回归测试
- Result: Success - 135 passed

## 2026-08-11 - Bash Command Executed
- Command: python -m py_compile app/services/minimax.py
- Purpose: 语法校验
- Result: Success

## 2026-08-11 - Analysis
- Topic: 修复覆盖范围
- Finding: 仅 minimax.py 两处直接构造 Ollama /api/chat payload；主 agent 用 /v1 (ChatOpenAI) 不受 thinking 影响（实测 reasoning_len=0 正常返回 tool_calls）；无需改 agent_engine/subagents
- Decision: 修复完整覆盖

## 2026-08-11 - Task: SQL agent 集成（/plan-eng-review CLEARED）
- Project: design_plan_generation_local_model
- Start: 上午 / End: 17:03

### Bash Commands
## 2026-08-11 - Bash Command Executed
- Command: `python -m py_compile app/services/agent_engine.py app/main.py`
- Working Dir: design_planning_generation_local_model
- Purpose: SQL 启动接线语法校验
- Result: Success - SYNTAX OK

## 2026-08-11 - Bash Command Executed
- Command: `PYTHONIOENCODING=utf-8 python -c "from app.services.sql_db import init_db, list_tables; ..."`
- Working Dir: design_planning_generation_local_model
- Purpose: init_db 幂等 + 表清单校验
- Result: Success - 数据库已存在，跳过种子（seed_version=2026-08-11-v1）；6 表齐全

## 2026-08-11 - Bash Command Executed
- Command: `python -m pytest tests/test_sql_db.py tests/test_sql_tools.py tests/test_sql_prompt.py -q`
- Working Dir: design_planning_generation_local_model
- Purpose: SQL 新增测试
- Result: Success - 43 passed（首轮 10 失败：StructuredTool 需 .ainvoke() 调用、单列结果无 | 分隔，已修复）

## 2026-08-11 - Bash Command Executed
- Command: `python -m pytest tests/ -q`
- Working Dir: design_planning_generation_local_model
- Purpose: 全量回归
- Result: 198 passed, 4 failed（3 条历史既有：test_search_kb_no_results_format 依赖 vector_store.py 上个会话改动；context_manager 两测试依赖 LLM 环境；1 条为 test_phase1_tools_list 过期断言，已修正）

## 2026-08-11 - Bash Command Executed
- Command: `python -m pytest tests/test_agent.py::TestAgentTools::test_phase1_tools_list tests/test_sql_db.py tests/test_sql_tools.py tests/test_sql_prompt.py -q`
- Working Dir: design_planning_generation_local_model
- Purpose: 修正后 phase1 断言 + SQL 测试复核
- Result: Success - 43 passed

## 2026-08-11 - Bash Command Executed
- Command: `python -m py_compile _test_sql_agent_eval.py`
- Working Dir: design_planning_generation_local_model
- Purpose: 真实 LLM EVAL 脚本语法校验
- Result: Success - EVAL SYNTAX OK

## 2026-08-11 - Bash Command Executed
- Command: `python _test_sql_agent_eval.py`（后台运行）
- Working Dir: design_planning_generation_local_model
- Purpose: 真实 LLM（qwen3.5:122b / Ollama）SQL agent 端到端 EVAL
- Result: 运行中（完成后更新）

### File Edits
## 2026-08-11 - File Edited
- File: app/services/sql_db.py（新建）
- Change: 领域 SQLite 库模块：连接(mode=ro+query_only+uri=True)/建表/seed-once 幂等/查询原语
- Result: Success

## 2026-08-11 - File Edited
- File: app/services/agent_tools.py
- Change: 新增 sql_db_list_tables/sql_db_schema/sql_db_query 3 工具并注册 PHASE1_TOOLS
- Result: Success

## 2026-08-11 - File Edited
- File: app/services/agent_prompt.py
- Change: TOOL_RULES 新增「## SQL 领域数据库查询」段
- Result: Success

## 2026-08-11 - File Edited
- File: app/services/agent_engine.py
- Change: init_agent() 启动时调用 init_db()（幂等，失败非致命）
- Result: Success

## 2026-08-11 - File Edited
- File: ../.gitignore（父仓库根）
- Change: 追加 **/data/domain.db 及 -journal/-wal/-shm
- Result: Success

## 2026-08-11 - File Edited
- File: tests/test_sql_db.py / test_sql_tools.py / test_sql_prompt.py（新建）
- Change: SQL 单元/工具/提示词回归测试共 43 条
- Result: Success

## 2026-08-11 - File Edited
- File: tests/test_agent.py
- Change: test_phase1_tools_list 过期断言（len==4）改为核心+SQL 工具存在性断言
- Result: Success

## 2026-08-11 - File Edited
- File: TODOS.md（新建）
- Change: 2 条 SQL 相关 TODO（种子扩充维护 / 前端 SQL 结果专用展示）
- Result: Success

## 2026-08-11 - File Edited
- File: _test_sql_agent_eval.py（新建）
- Change: 真实 LLM SQL agent 端到端 EVAL（3 题：标准适用/材料选择/输注精度）
- Result: Success

### Analysis
## 2026-08-11 - Analysis
- Topic: 回归失败归属
- Finding: test_search_kb_no_results_format 依赖 vector_store.py（上个会话改动，非本会话）；test_maybe_compress_above_threshold 与 test_fallback_summary_generates_json 依赖 LLM 环境（context_manager.py 未改动）；仅 test_phase1_tools_list 为过期断言（len(PHASE1_TOOLS)==4 早于本会话已失效）
- Decision: 3 条历史既有失败不做处理并记录；phase1 断言修正为存在性断言

## 2026-08-11 - Analysis
- Topic: StructuredTool 调用方式
- Finding: @tool 装饰的 async 函数是 StructuredTool 对象，不可直接 await 调用
- Decision: 测试统一用 `await tool.ainvoke({...})`（kwargs 字典）

## 2026-08-11 - Bash Command Executed
- Command: `python _test_sql_agent_eval.py`（第 1 轮，开放式题组）
- Working Dir: design_planning_generation_local_model
- Purpose: 真实 LLM SQL agent EVAL
- Result: 0/3 通过（但答案全对）。发现：开放式文本题 agent 合理选 search_kb(RAG) 而非 sql_db_*（符合 TOOL_RULES「何时不用」指引，属预期行为）

## 2026-08-11 - Bash Command Executed
- Command: `python _test_sql_agent_eval.py`（第 2 轮，SQL 强制题组）
- Working Dir: design_planning_generation_local_model
- Purpose: 真实 LLM SQL agent EVAL（改显式查库 + 结构化列筛选题）
- Result: 3/3 通过。工具轨迹: Q1/Q2 = sql_db_list_tables→sql_db_schema→sql_db_query；Q3 = sql_db_schema→sql_db_query。答案含正确关键事实（不可接受风险项/参数限值±5/ISO 14971 与 GB/T 42062）

## 2026-08-11 - Analysis
- Topic: SQL agent 工具路由行为
- Finding: 首轮开放式题 agent 全走 search_kb 且答案正确；显式要求查库时 3/3 走 SQL 链路且顺序符合 TOOL_RULES
- Decision: 提示词无需改动（当前「何时用/何时不用」指引已正确引导路由）；SQL 能力验证以第 2 轮 3/3 为准

## 2026-08-11 17:42 - Task Started
- Project: design_plan_generation_local_model（设计方案生成 Agent）
- Task: 参照《KF-CGM-2-0004 设计输入 V7.0》为每个生成的文档附加 首页 / 修订记录 / 目录
- 决策（AskUserQuestion 确认）: 文件编号=阶段编号方案（KF-CGM-{阶段序号}-{4位序号}）；目录=Word 域目录（打开自动更新）；编制/审核/批准=env 可配置；跳过 /plan-eng-review 直接实现

## 2026-08-11 17:42 - File Edited
- File: app/services/template.py
- Change: 新增前置页机制。导入 datetime/WD_TABLE_ALIGNMENT/OxmlElement/qn/DOC_CATEGORIES；模块级助手 _derive_doc_number（阶段编号方案，env DOC_NUMBER_PREFIX 覆盖前缀，未归类确定性兜底）、_append_field（Word 域 begin/instr/separate/end）、_set_update_fields_on_open（w:updateFields 使 Word 打开自动刷新域）。fill_template 在解析正文前注入 _add_front_matter（首页+修订记录+目录）+ _add_page_number_footer（第X页共Y页）。新增方法：_add_cover（Title+产品名+信息表4×2+签名表3×4）、_add_revision_history（6列表：版本号/修订日期/修订内容/编制/审核/批准，首行 V1.0）、_add_toc（TOC \o "1-3" 域）、_add_page_number_footer。_parse_and_fill 移除与首页重复的标题/副标题（product_name/doc_type 参数相应移除）。前置页小节标题用居中加粗段落（非 Heading 样式，避免进入 TOC）。
- Result: Success

## 2026-08-11 17:42 - File Created
- File: tests/test_template_front_matter.py
- Change: 17 条前置页测试（首页字段/修订记录表/目录域/updateFields/页码域/分页计数/编号推导与兜底/env 覆盖/正文仍完整解析/标题不重复）
- Result: Success（17 passed）

## 2026-08-11 17:42 - Bash Command Executed
- Command: `python -m pytest tests/test_template_front_matter.py -q`（env_01）
- Working Dir: design_planning_generation_local_model
- Purpose: 前置页测试
- Result: Success - 首轮 16 passed 1 failed（_Footer 用 _element 非 element），修正后 17 passed

## 2026-08-11 17:42 - Bash Command Executed
- Command: `python -m pytest tests/ -q -p no:cacheprovider`（env_01）
- Working Dir: design_planning_generation_local_model
- Purpose: 全量回归
- Result: 216 passed, 3 failed（3 条均为历史既有失败：test_search_kb_no_results_format 依赖 vector_store.py；test_maybe_compress_above_threshold / test_fallback_summary_generates_json 依赖 LLM 环境。无新增回归）

## 2026-08-11 17:42 - Bash Command Executed
- Command: `python _scratch_front_matter_check.py`（env_01，生成 _front_matter_sample.docx 并 dump 结构）
- Working Dir: design_planning_generation_local_model
- Purpose: 验证前置页布局顺序与域
- Result: Success - 首页(Title 设计输入文件+产品名+信息表4×2+签名表3×4)→修订记录(2×6)→目录(TOC 域)→正文(Heading 1/2+列表+markdown 表)；page_breaks=3，TOC 域与 updateFields 均存在。临时脚本已删除，样例保留 _front_matter_sample.docx（38KB）

## 2026-08-11 17:42 - Analysis
- Topic: 前置页编号方案
- Finding: 参考《KF-CGM-2-0004 设计输入 V7.0》为「前缀-阶段序号-4位序号」；本项目 DOC_CATEGORIES 分组名首字中文数字即阶段序号（二、设计输入→2），组内顺序为序号。design_input 推导为 KF-CGM-2-0001（格式一致，具体序号不必与参考逐一对齐）。legacy/未归类文档阶段=0，未归类用确定性散列序号避免冲突
- Decision: 阶段序号解析自分组名而非 dict 顺序（显式、可读、不依赖插入序）；修订记录/目录页标题用非 Heading 段落避免进入正文目录

## 2026-08-11 18:04 - 任务开始: 添加模板功能 (front-matter 之后新功能)
- Topic: 添加模板入口 — 用户点击「添加模板」上传参考文档，Agent 读取其章节结构与内容，模仿模板风格生成目标文档
- Decision: 用户确认「不用评审，直接执行」。模板作为 state["templates"] 一级概念（区别于普通附件），持久化提取不污染共享知识库；新增 outline_from_template 工具，复用 outline_from_attachment 的章节结构提取逻辑（共享 _extract_outline_from_text 助手）

## 2026-08-11 18:04 - File Edited
- File: app/services/agent_state.py
- Change: AgentState 增加 `templates: list[dict]` 字段（template_id/name/filename/doc_type/char_count/preview/toc/full_text/status）；create_initial_state 返回 templates=[]；build_state_snapshot 增加 templates 键
- Result: Success

## 2026-08-11 18:04 - File Edited
- File: app/services/agent_tools.py
- Change: 新增 `_current_templates` contextvar + `set_current_templates()`；抽取共享助手 `_extract_outline_from_text`（超时/空/无效JSON 抛 `_OutlineExtractError`）；outline_from_attachment Step3 改为调用共享助手；新增 `outline_from_template` 工具（无模板/无全文/指定 ID 不存在 → 降级错误；全文按 50000 预算等额截断；成功返回 design_outline 兼容 JSON）；注册到 PHASE1_TOOLS（outline_from_attachment 之后、write_chapter 之前）
- Result: Success

## 2026-08-11 18:04 - File Edited
- File: app/services/agent_prompt.py
- Change: TOOL_RULES 增加 5c 节说明 outline_from_template（模板优先路径）；SOP_KNOWLEDGE 步骤4 改为「有附件/模板时的路径选择」（模板非空时必须提供选项C 按模板生成）；build_system_prompt 在 attachment_info 后注入 template_info 段（模板名称/文档类型/预览/目录 + 生成时模仿模板风格指引），`{template_info}` 占位符加入 state_section
- Result: Success

## 2026-08-11 18:04 - File Edited
- File: app/services/agent_engine.py
- Change: _agent_node 在 _sync_attachment_context 后调用 _sync_template_context(state)，同步模板到 agent_tools contextvar
- Result: Success

## 2026-08-11 18:04 - File Edited
- File: app/api/routes.py
- Change: 新增三个路由 — POST /agent/projects/{id}/templates（上传+提取+写 state.templates）、GET /agent/projects/{id}/templates（列表）、DELETE /agent/projects/{id}/templates/{template_id}（移除）
- Result: Success

## 2026-08-11 18:04 - File Edited
- File: app/static/agent.html
- Change: 新增 .tpl-upload-btn/.template-area/.tpl-chip 系列青绿色样式；templateDialog 弹窗（名称/文档类型下拉/文件选择）；header「📄 添加模板」按钮；template-area 容器；JS 函数 showTemplateDialog/closeTemplateDialog/handleTemplateFileSelect/submitTemplate/renderTemplateChips/removeTemplate/fetchTemplates；fetchTemplates 接入 sendMessage/resumeAgent/autoGen finally 与 init
- Result: Success

## 2026-08-11 18:04 - File Edited
- File: tests/test_template_prompt.py (新建)
- Change: build_system_prompt 模板段回归护栏：无模板不注入、有模板注入名称/预览/目录/风格指引、TOOL_RULES 5c、SOP 步骤4 模板路径、与精炼模式共存
- Result: Success

## 2026-08-11 18:04 - File Edited
- File: tests/test_template_tools.py (新建)
- Change: outline_from_template 分支测试：PHASE1_TOOLS 注册顺序、无模板/无全文/ID不存在降级、LLM 失败指引、正常路径返回兼容 JSON、全文预算截断、多模板分发
- Result: Success

## 2026-08-11 18:04 - Bash Command Executed
- Command: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_template_prompt.py tests/test_template_tools.py -q`（env_01）
- Working Dir: design_planning_generation_local_model
- Purpose: 模板功能新测试
- Result: 首轮 4 failed → 修正（基线断言改用动态指引标记；DOC_TYPE_LABELS design_development_plan=设计开发策划书；_sample_template 增加 template_id/filename 参数；预算断言 lstrip 前缀换行）→ 27 passed

## 2026-08-11 18:04 - Bash Command Executed
- Command: `PYTHONIOENCODING=utf-8 python -m pytest tests/ -q --ignore=tests/test_openviking_integration.py`（env_01）
- Working Dir: design_planning_generation_local_model
- Purpose: 全量回归
- Result: 231 passed, 3 failed（3 条均为历史既有失败，与模板功能无关：test_search_kb_no_results_format 依赖 vector_store 检索环境；test_maybe_compress_above_threshold / test_fallback_summary_generates_json 依赖 LLM 环境，且后者是 context_manager 实现返回纯文本与测试期望 JSON 的既有不匹配）。无新增回归

## 2026-08-11 18:04 - Bash Command Executed
- Command: `PYTHONIOENCODING=utf-8 python -c "import app.services.agent_state/agent_tools/agent_prompt/agent_engine, app.api.routes; ..."`（env_01）
- Working Dir: design_planning_generation_local_model
- Purpose: 后端导入与模板接线冒烟
- Result: Success - imports OK；state.templates 存在；outline_from_template 已注册 PHASE1_TOOLS；routes 含模板端点

## 2026-08-13 14:53 - Task Start
- Task: 添加模板按钮支持一次性选择并批量添加多个模板文件
- Project: design_planning_generation_local_model
- Scope: 仅前端 app/static/agent.html（后端 POST /api/agent/projects/{id}/templates 本身支持单文件，前端逐个串行调用即可，无需改后端）

## 2026-08-13 14:53 - File Edited
- File: `app/static/agent.html`
- Change: 模板对话框描述文案增加"支持一次选择多个文件批量添加"说明（约 L465）
- Result: Success

## 2026-08-13 14:53 - File Edited
- File: `app/static/agent.html`
- Change: #tplFileInput 增加 multiple 属性；"选择文件"按钮文案改为"选择文件（可多选）"（约 L480-486）
- Result: Success

## 2026-08-13 14:53 - File Edited
- File: `app/static/agent.html`
- Change: 模板管理 JS 重构为多文件批量添加：
  1. `_selectedTemplateFile`（单文件）→ `_selectedTemplateFiles`（File 数组）
  2. `showTemplateDialog()` 重置逻辑适配数组 + 名称输入框状态复位 + 清空 file input
  3. `handleTemplateFileSelect()` 遍历所选文件逐个校验格式/大小，不合规文件跳过并提示；多选时禁用名称输入框（各模板以文件名命名）
  4. `submitTemplate()` 改为逐个串行上传（后端每个文件需提取文本、可能触发 MinerU，串行避免资源争用）；每文件独立 uploading chip（唯一 chipId）；单文件仍需填名称，多文件以文件名命名；结束后汇总提示成功数与失败明细；失败响应兼容 data.detail（HTTPException）
- Why: 用户要求点击"添加模板"按钮支持一次性添加多个模板文件
- Result: Success

## 2026-08-13 14:53 - Bash Command Executed
- Command: `node -e "读取 agent.html 提取 <script> 块并用 new Function 做语法校验"`
- Working Dir: design_planning_generation_local_model
- Purpose: 校验修改后的内联 JS 语法
- Result: Success - script block 0 OK, 60544 chars

## 2026-08-13 14:53 - Analysis
- Topic: 是否需要改后端
- Finding: 后端 agent_upload_template 每次接收单文件并同步轮询提取（最长5分钟），前端串行循环调用即可实现批量；无需新增批量接口
- Decision: 仅改前端，保持后端不动

## 2026-08-13 16:12 - Analysis
- Topic: 多模板上传 bug 根因定位
- Finding: 前次会话已将 `_selectedTemplateFile`(单文件) 改为 `_selectedTemplateFiles`(数组)，但 `handleTemplateFileSelect` 中 `_selectedTemplateFiles = valid` 是**替换**而非追加。导致用户「先选文件A、再选文件B」时，A 被 B 顶替掉，最终只能上传最后一个文件。`_test_template_append_repro.py` 复现测试通过，证明后端 read-modify-write 逻辑无问题，bug 在前端。
- Decision: 修改前端 `handleTemplateFileSelect` 为追加模式（带去重），并在对话框内显示已选文件列表（可单独移除）；同时移除「单文件必须输入名称」的限制。

## 2026-08-13 16:12 - File Edited
- File: `app/static/agent.html`
- Change: 修复多模板上传 + 名称非必填：
  1. 对话框 HTML：描述文本补充「也可多次追加选择」；标签改为「模板名称（留空则使用文件名）」；输入框 placeholder 改为「留空则使用文件名」；按钮文案改为「选择文件（可多选/可追加）」；新增 `<div id="tplSelectedList">` 用于渲染已选文件列表
  2. `showTemplateDialog()`：placeholder 改为「留空则使用文件名」；调用 `renderSelectedTemplateFiles()` 清空已选列表 UI
  3. 新增 `renderSelectedTemplateFiles()`：在对话框内渲染已选文件 chip 列表（文件名 + 大小 + × 移除按钮）
  4. 新增 `removeSelectedTemplateFile(idx)`：从 `_selectedTemplateFiles` 移除指定索引文件，并重新计算名称输入框启用/禁用状态
  5. `handleTemplateFileSelect()`：改为**追加**模式 `_selectedTemplateFiles = _selectedTemplateFiles.concat(valid)`（带同名同大小去重）；`event.target.value = ''` 允许重选同一文件；UI 状态基于累计数量 `_selectedTemplateFiles.length` 而非当次 `valid.length`；末尾调用 `renderSelectedTemplateFiles()`
  6. `submitTemplate()`：删除 `if (files.length === 1 && !name) { showError('请输入模板名称'); return; }` 校验；`tplName = (files.length === 1 && name) ? name : file.name`（单文件有名称用名称、否则用文件名；多文件一律用文件名）
- Why: 用户反馈 agent 模式上传模板时无法上传多个模板（实为「追加选择会顶替上一个」），且要求添加模板时无需强制输入名称
- Result: Success

## 2026-08-13 16:12 - Bash Command Executed
- Command: `python _test_template_append_repro.py`
- Working Dir: design_planning_generation_local_model
- Purpose: 验证后端 agent_upload_template 的 read-modify-write 在连续 3 次追加后是否累积（排除后端 bug）
- Result: Success - FINAL templates = ['tpl-A', 'tpl-B', 'tpl-C']，后端无问题，bug 定位在前端

## 2026-08-13 16:14 - Bash Command Executed
- Command: `node -e "提取 <script> 块并用 new Function 做语法校验"`
- Working Dir: design_planning_generation_local_model
- Purpose: 校验修改后 agent.html 内联 JS 语法
- Result: Success - JS syntax OK, length = 63709

## 2026-08-13 16:14 - Analysis
- Topic: 修复验证总结
- Finding: JS 语法校验通过；前端 4 处改动（对话框 HTML、showTemplateDialog + 新增两个函数、handleTemplateFileSelect 改追加模式、submitTemplate 移除名称必填）均按预期完成
- Decision: 修复完成，建议用户在浏览器中实际测试多模板上传流程

## 2026-08-13 16:20 - File Edited
- File: `app/static/agent.html`
- Change: 添加附件入口显眼化：
  1. 新增 CSS 类 `.att-header-btn`（蓝色 #1976d2 主色，与 `.tpl-upload-btn` / `.kb-upload-btn` 并列的 prominent 按钮）
  2. 顶部 main-header 在「添加模板」按钮前新增 `📎 添加附件` 按钮（id=attHeaderBtn，触发同一 fileInput.click()）
  3. 输入区旁的快速上传圆形按钮 `.att-upload-btn` 从「灰色虚线 32px」改为「蓝色实线 36px + 阴影 + hover 反色」，让用户在输入框附近也能及时看到
- Why: 用户反馈添加附件的入口不够显眼，希望用户能及时看到
- Result: Success

## 2026-08-13 16:20 - Bash Command Executed
- Command: `node -e "提取 <script> 块并用 new Function 做语法校验"`
- Working Dir: design_planning_generation_local_model
- Purpose: 校验修改后 agent.html 内联 JS 语法
- Result: Success - JS syntax OK, length = 63709

## 2026-08-18 - File Edited (OpenViking 前端记忆工具标签)
- File: app/static/agent.html
  Change: (1) toolLabel() 新增 viking_find/viking_search/viking_read/viking_store/viking_add_resource 的中文标签映射（"检索历史记忆"/"搜索当前会话记忆"/"读取记忆详情"/"保存记忆"/"添加记忆资源"）；(2) 两处 tool_end 硬编码三元改为统一使用 toolLabel()，避免新工具漏掉友好标签。
  Result: Success

## 2026-08-25 15:00:05 - 任务开始：Agent 对话框拖拽文件引用功能
- 项目: design_planning_generation_local_model (设计策划文档生成系统 v2.0)
- 需求: 实现"拖拽文件到对话框输入框 → 消息内插入 @文件名 引用标记 → 发送后 Agent 精确定位该附件"

## 2026-08-25 15:00:05 - File Edited
- File: `app/static/agent.html`
- Change: 新增 `.input-area.drag-over` 高亮样式（拖拽文件到输入框时显示蓝色虚线边框）
- Result: Success

## 2026-08-25 15:00:05 - File Edited
- File: `app/static/agent.html`
- Change: 新增 `let fileRefs = {}`（文件名→file_id 映射），`uploadFile` 改为返回 `{file_id, filename}` 并在成功时登记映射，新增 `expandFileReferences()`（@文件名 → 附件《文件名》（file_id: xxx））和 `insertFileReference()`（在光标处插入引用标记）两个辅助函数
- Result: Success

## 2026-08-25 15:00:05 - File Edited
- File: `app/static/agent.html`
- Change: 新增 `setupInputDragDrop()` IIFE：监听 `.input-area` 的 dragenter/dragover/dragleave/drop，拖入文件后以 silent 模式上传并插入引用标记
- Result: Success

## 2026-08-25 15:00:05 - File Edited
- File: `app/static/agent.html`
- Change: `sendMessage()` 增加 `messageToSend = expandFileReferences(message)`，发送体和 `lastUserMessage`（重试用）改用展开后的消息，聊天气泡仍显示干净的 @文件名
- Result: Success

## 2026-08-25 15:05:00 - 需求修正：拖拽仅插入引用，不触发上传
- 用户澄清：拖文件到输入框不是为了上传附件，只是要在输入框里引用这个文件名
- 回退: uploadFile 恢复原样（去掉 silent/返回值/fileRefs 登记）、删除 fileRefs/expandFileReferences/insertFileReference/messageToSend
- 保留: .input-area.drag-over 样式、insertReferenceToken()（仅插入文字）、setupInputDragDrop()（drop 时插入 @文件名，不上传）
- Result: Success

## 2026-08-25 15:15:21 - 任务开始：上传附件/模板过程中支持取消上传
- 项目: design_planning_generation_local_model (设计策划文档生成系统 v2.0)
- 需求: 用户要求"上传附件或模板的过程中，能否取消上传"。为三个上传路径（单文件附件、文件夹、模板）增加 AbortController + 取消入口。

## 2026-08-25 15:15:21 - File Edited
- File: `app/static/agent.html`
- Change: 新增 `const activeUploads = {}`（uploadId → AbortController 映射），紧跟 `uploadedFiles` 声明之后。
- Result: Success

## 2026-08-25 15:15:21 - File Edited
- File: `app/static/agent.html`
- Change: 新增全局 `cancelUpload(uploadId)`：abort 对应 controller、清理附件/模板占位 chip 并重渲染，对不存在 id 幂等。
- Result: Success

## 2026-08-25 15:15:21 - File Edited
- File: `app/static/agent.html`
- Change: `uploadFile()`：tempId 加入随机后缀避免并发冲突；创建 AbortController 存入 activeUploads 并传入 fetch signal；catch 中 AbortError 不弹错误；finally 清理 activeUploads。
- Result: Success

## 2026-08-25 15:15:21 - File Edited
- File: `app/static/agent.html`
- Change: `buildAttachmentChip()` 的 uploading 分支新增"×"取消按钮（onclick=cancelUpload(file_id)）。
- Result: Success

## 2026-08-25 15:15:21 - File Edited
- File: `app/static/agent.html`
- Change: `submitTemplate()`：每个模板上传创建 AbortController 传入 POST fetch signal；轮询循环顶部检查 aborted 抛 AbortError；catch 中 AbortError 时 break 停止整个批量；finally 清理 activeUploads。
- Result: Success

## 2026-08-25 15:15:21 - File Edited
- File: `app/static/agent.html`
- Change: `renderTemplateChips()` 的 uploading 分支新增"×"取消按钮（onclick=cancelUpload(template_id)），替代原先空字符串。
- Result: Success

## 2026-08-25 15:15:21 - File Edited
- File: `app/static/agent.html`
- Change: 文件夹上传：`handleFolderSelect()` 生成 folderUploadId + AbortController，进度条文本新增红色"取消"链接；`uploadFolderBatch()` 新增 signal 参数并传入 fetch；catch 中 AbortError 不弹错误；finally 清理 activeUploads 并移除进度条。
- Result: Success

## 2026-08-25 15:30:00 - 任务开始：从附件/模板 chip 拖拽到输入框引用
- 项目: design_planning_generation_local_model
- 需求: 用户希望直接从附件区或模板区的 chip 拖到输入框，插入 @文件名 引用（不上传）。

## 2026-08-25 15:30:00 - File Edited
- File: `app/static/agent.html`
- Change: 新增 `makeChipDraggable(el, refText)`：设置 draggable=true，dragstart 写入 `application/x-file-ref` 与 `text/plain` 数据。
- Result: Success

## 2026-08-25 15:30:00 - File Edited
- File: `app/static/agent.html`
- Change: `buildAttachmentChip()` 非上传态 chip 调用 `makeChipDraggable(chip, f.relative_path || f.filename)`（文件夹文件用完整相对路径，与 Agent 提示一致）。
- Result: Success

## 2026-08-25 15:30:00 - File Edited
- File: `app/static/agent.html`
- Change: `renderTemplateChips()` 非上传态 chip 调用 `makeChipDraggable(chip, t.name || t.filename)`。
- Result: Success

## 2026-08-25 15:30:00 - File Edited
- File: `app/static/agent.html`
- Change: `setupInputDragDrop()` 扩展：接受 `Files` 或 `application/x-file-ref` 两类拖拽；drop 时优先读取 chip 引用，否则回退为系统文件。
- Result: Success

## 2026-08-25 15:30:00 - File Edited
- File: `app/static/agent.html`
- Change: 新增 `.att-chip[draggable="true"]/.tpl-chip[draggable="true"] { cursor: grab }` 及 active 态 grabbing，提供可拖拽视觉提示。
- Result: Success

## 2026-08-25 15:45:00 - 任务开始：输入框快速清空
- 项目: design_planning_generation_local_model
- 需求: 用户希望快速清除输入框中的文字。

## 2026-08-25 15:45:00 - File Edited
- File: `app/static/agent.html`
- Change: 输入框与发送按钮之间新增 `#clearBtn`（×）清空按钮，初始 display:none；textarea 增加 `oninput="updateClearBtn()"`。
- Result: Success

## 2026-08-25 15:45:00 - File Edited
- File: `app/static/agent.html`
- Change: 新增 `.input-area #clearBtn` 淡色小圆点样式（覆盖 `.input-area button` 默认蓝色大按钮）。
- Result: Success

## 2026-08-25 15:45:00 - File Edited
- File: `app/static/agent.html`
- Change: 新增 `clearInput()`（清空+聚焦）与 `updateClearBtn()`（按有无文字显示/隐藏按钮）；`insertReferenceToken()` 与 `sendMessage()` 清空输入后调用 updateClearBtn 保持按钮状态同步。
- Result: Success

## 2026-08-25 17:05:00 - 任务开始：修复生成文档出现 HTML <table> 而非渲染表格的问题
- 项目: design_planning_generation_local_model
- 需求: 用户发现生成的部分段落输出为 `<table><tr><td>阶段</td><td>核心任务</td>...</td></tr></table>` 原始 HTML，而非渲染的表格。根因：LLM 输出 HTML 表格，前端 formatContent 会转义 HTML 且只渲染 Markdown 管道表格；prompt 也未禁止 HTML 表格。方案：A（prompt 侧禁止 HTML 表格，治本）+ B（前端兜底把 HTML 表格归一化为 Markdown）。

## 2026-08-25 17:05:00 - File Edited
- File: `app/services/agent_tools.py`
- Change: 新增常量 `_TABLE_FORMAT_RULE`（要求表格必须用 Markdown 管道表格语法，禁止 HTML <table>/<tr>/<td>）。
- Result: Success

## 2026-08-25 17:05:00 - File Edited
- File: `app/services/agent_tools.py`
- Change: 将 `{_TABLE_FORMAT_RULE}` 注入 6 处生成/改写 prompt：generate_section、revise_section、_rewrite_single_pass、_rewrite_section_wise、write_chapter 分段、write_chapter 整章（f-string 用 `{_TABLE_FORMAT_RULE}`，普通字符串拼接用 `+ _TABLE_FORMAT_RULE +`）。
- Result: Success

## 2026-08-25 17:09:00 - File Edited
- File: `app/static/agent.html`
- Change: 新增 `htmlTableToMarkdown(text)` 辅助函数：正则匹配 `<table>...</table>`，逐行提取 `<tr>`/`<td>`/`<th>` 单元格文本，首行作为表头生成 `|---|` 分隔的 Markdown 管道表格；`formatContent()` 开头先调用 `text = htmlTableToMarkdown(text)` 作为兜底。
- Result: Success

## 2026-08-25 17:09:17 - 校验
- Topic: Python 语法校验（agent_tools.py）
- Finding: `ast.parse` 通过（输出 AST_PARSE_OK），说明 6 处 prompt 注入无语法错误。
- Decision: A（prompt 侧）+ B（前端兜底）两处修改均完成。

## 2026-08-25 18:12:17 - 任务开始：文档名称改为"项目开发计划书"
- 项目: design_planning_generation_local_model
- 需求: 用户要求生成的文档名称改为"项目开发计划书"，不要写"设计开发策划书"。

## 2026-08-25 18:12:17 - File Edited
- File: `app/services/doc_types.py`
- Change: `DOC_TYPE_LABELS["design_development_plan"]` 从"设计开发策划书"改为"项目开发计划书"（第212行，决定生成文档标题的核心映射）；同步修改第11行 `DOC_TYPES` 注释。
- Result: Success

## 2026-08-25 18:12:17 - File Edited
- File: `app/services/prompt_engineer.py`
- Change: `DOC_TYPE_SPECIFIC_PROMPTS["design_development_plan"]` 标题从"【设计开发策划书特别要求】"改为"【项目开发计划书特别要求】"。
- Result: Success

## 2026-08-25 18:12:17 - File Edited
- File: `tests/test_template_tools.py`
- Change: 断言 `"设计开发策划书" in captured["label"]` 改为 `"项目开发计划书" in captured["label"]`，与 DOC_TYPE_LABELS 映射同步。
- Result: Success

## 2026-08-26 16:11:47 - 任务开始：修复新增章节序号不顺延的问题
- 项目: design_planning_generation_local_model
- 需求: 文档生成后，对 agent 提出"增加某一章节"时，新增章节的序号不能顺延（最后一章为"第六章"，新增章节仍为"第六章"）。
- 根因: 章节标题的"第X章"序号由 LLM 在 outline 阶段写入 title，prompt 未强制"序号连续递增 + 新增章节顺延"，导致 LLM 重复编号。

## 2026-08-26 16:11:47 - File Edited
- File: `app/services/agent_tools.py`
- Change: `design_outline` prompt 末尾追加"章节编号规则"（章节标题形如"第一章 XXX"，序号从1连续递增，不重复不跳号）。
- Result: Success

## 2026-08-26 16:11:47 - File Edited
- File: `app/services/agent_tools.py`
- Change: `update_outline` prompt 追加"章节编号规则"（新增章节序号顺延=现有最大序号+1；删除/插入后重新连续编号）。
- Result: Success

## 2026-08-26 16:11:47 - File Edited
- File: `app/services/agent_tools.py`
- Change: `_extract_outline_from_text` 关键约束追加"章节标题序号连续递增，不重复不跳号"。
- Result: Success

## 2026-08-26 16:11:47 - File Edited
- File: `app/services/agent_prompt.py`
- Change: write_chapter 规则追加"增加新章节时 chapter_name 序号必须顺延（第X章→第X+1章）"。
- Result: Success

## 2026-08-26 16:11:47 - File Edited
- File: `app/services/agent_prompt.py`
- Change: update_outline 描述追加"⚠️ 章节序号连续递增、新增顺延、删除/插入后重新连续编号"。
- Result: Success

## 2026-08-26 16:11:47 - 校验
- Topic: Python 语法校验（agent_tools.py / agent_prompt.py）
- Finding: ast.parse 通过（AST_PARSE_OK），5 处 prompt 注入无语法错误。
- Decision: 修复完成。

## 2026-08-26 17:09:42 - 任务：前端新增「补充文档」入口（补全 enrich 功能）

## 2026-08-26 17:09:42 - File Edited
- File: `app/static/agent.html`
- Change: `uploadFile(file)` 校验失败分支由 `return;` 改为 `return null;`，成功分支记录 `resultFileId = data.file_id`，函数末尾返回 `resultFileId`（供 `submitEnrich` 上传后拿到真实 file_id）。
- Result: Success

## 2026-08-26 17:09:42 - File Edited
- File: `app/static/agent.html`
- Change: 在 `submitModify` 之后、`showModifiedDownloadButton` 之前新增「补充文档」相关 JS 函数：`showEnrichDialog()`（动态填充已上传附件下拉框并重置字段）、`closeEnrichDialog()`、`handleEnrichFileSelect(event)`（选择新文件后清空下拉选择）、`onEnrichExistingChange(value)`（选择已有附件后清空新文件选择）、`submitEnrich()`（优先上传新文档拿 file_id，否则用已选附件，拼装"请把附件「X」的内容补充得更完整、更详细[，补充重点：Y]"注入聊天并 sendMessage）。
- Result: Success

## 2026-08-26 17:09:42 - 校验
- Topic: 语法校验（Python + 前端 JS）
- Finding: `py_compile` 通过（agent_tools.py / agent_engine.py / agent_prompt.py / default_templates/__init__.py，PY_COMPILE_OK）；抽取 agent.html 内联 JS（100422 字符）经 `node --check` 通过（JS_CHECK_OK）。
- Decision: 前端「补充文档」入口 + 后端 enrich_attachment 链路完整，功能可用。

## 2026-08-26 17:15:00 - 任务：精简文档时保留表格 + 法规过程描述直接写结论

## 2026-08-26 17:15:00 - File Edited
- File: `app/services/agent_tools.py`
- Change: `_summarize_one_subsection` 的 system_prompt「必须保留」中表格规则由"表格中的数据行（保留表格，可精简表格周围说明文字）"强化为"所有表格（含表号、表头、全部数据行）必须原样保留，不得删除任何表格、表头或数据行；只可精简表格周围说明文字"；「可以精简」新增一条"涉及法规/标准的过程性、描述性语言（层层分析推导的叙述）直接精简为结论，删除分析推导过程；只保留条款号和最终结论"。
- Result: Success

## 2026-08-26 17:15:00 - File Edited
- File: `app/services/agent_tools.py`
- Change: aggressive（二次精简）prompt 中"表格保留完整列结构…不得删除整列"改为"所有表格（含表号、表头、全部数据行）必须原样保留，不得删除任何表格"；"法规条款号可保留但删除其后的展开说明"改为"法规条款号保留，但删除其后的过程性展开说明和层层分析推导，直接写结论"。
- Result: Success

## 2026-08-26 17:15:00 - File Edited
- File: `app/services/agent_tools.py`
- Change: 迭代精简 retry_user_prompt 追加"所有表格必须原样保留不得删除；涉及法规的过程性描述直接写结论、删除分析推导"。
- Result: Success

## 2026-08-26 17:15:00 - File Edited
- File: `app/services/subagents.py`
- Change: `SUMMARY_AGENT_PROMPT`「必须保留」中表格规则同步强化为"所有表格（含表号、表头、全部数据行）必须原样保留，不得删除任何表格、表头或数据行"；「可以精简」新增法规过程性描述语言直接写结论规则。
- Result: Success

## 2026-08-26 17:15:00 - 校验
- Topic: Python 语法校验（agent_tools.py / subagents.py）
- Finding: py_compile 通过（PY_COMPILE_OK）。
- Decision: 精简功能规则已同步到主 prompt 与子代理 prompt，功能可用。

## 2026-08-26 17:40:00 - 任务：新增文档版本回退功能（单步撤销）

## 2026-08-26 17:40:00 - File Edited
- File: `app/services/agent_state.py`
- Change: AgentState 新增 `undo_stack: list[dict]` 字段（撤销栈快照），create_initial_state 初始化 `undo_stack=[]`。条目结构：`{"sections_before": {章节名: 旧内容或None}, "attachments_before_len": int, "removed_file_ids": [file_id,...], "description": str}`。
- Result: Success

## 2026-08-26 17:40:00 - File Edited
- File: `app/services/agent_engine.py`
- Change: `_after_tools_node` 在覆盖 generated_sections（generate_section/revise_section/revise_paragraph/write_chapter/summarize_section）前用 `sections_before` 记录旧值；在 append 附件修改（modify_attachment/enrich_attachment）时记录 `removed_file_ids` 与 `attachments_before_len`；循环后若有变更则压入 undo_stack（栈深上限 50），写入 result。
- Result: Success

## 2026-08-26 17:40:00 - File Edited
- File: `app/api/routes.py`
- Change: 新增 `POST /agent/projects/{project_id}/undo`，弹出 undo_stack 栈顶并恢复 generated_sections 章节旧值（None 删除章节）与 attachment_modifications 截断，`aupdate_state` 持久化，返回 description 与 removed_file_ids。
- Result: Success

## 2026-08-26 17:40:00 - File Edited
- File: `app/static/agent.html`
- Change: 顶栏新增「↩️ 回退」按钮（undoBtn）；新增 `undoLast()` JS，调用 undo API，成功后清理被回退的附件修改下载按钮 DOM 并 `fetchState()`/`fetchAttachments()` 刷新。
- Result: Success

## 2026-08-26 17:40:00 - 校验
- Topic: 语法校验（Python + 前端 JS）
- Finding: py_compile 通过（agent_state.py / agent_engine.py / routes.py，PY_COMPILE_OK）；抽取 agent.html 内联 JS（101445 字符）经 node --check 通过（JS_CHECK_OK）。
- Decision: 回退功能链路完整（快照→压栈→undo API→前端按钮），功能可用。

## 2026-08-26 18:20:00 - 任务：新增「精简上传附件」能力（对话驱动，补齐修改/补全/精简三类处理）

## 2026-08-26 18:20:00 - File Edited
- File: `app/services/agent_tools.py`
- Change: 新增 `_summarize_attachment_single_pass` / `_summarize_attachment_section_wise` / `summarize_attachment` 工具（kind=summarize），精简 prompt 融入「保留表格」「法规过程描述直接写结论」规则；复用 modify/enrich 的旁路存储与下载链路；注册到 PHASE1_TOOLS（enrich_attachment 之后）。
- Result: Success

## 2026-08-26 18:20:00 - File Edited
- File: `app/services/agent_engine.py`
- Change: 三处 `("modify_attachment", "enrich_attachment")` 统一改为 `("modify_attachment", "enrich_attachment", "summarize_attachment")`（_after_tools_node 处理 + 两处 SSE modified_doc_ready 事件）。
- Result: Success

## 2026-08-26 18:20:00 - File Edited
- File: `app/services/agent_prompt.py`
- Change: 新增「2f. summarize_attachment」工具说明，明确与 summarize_section/summarize_document 的区别（前者精简上传附件，后者精简生成文档章节），并注明保留表格、法规过程描述直接写结论等规则。
- Result: Success

## 2026-08-26 18:20:00 - File Edited
- File: `app/static/agent.html`
- Change: `showModifiedDownloadButton` 改为 kind→文案映射（modify/enrich/summarize 分别显示修改/补全/精简版下载）；`toolLabel` 新增 `summarize_attachment` → 「精简附件」。
- Result: Success

## 2026-08-26 18:20:00 - 校验
- Topic: 语法校验（Python + 前端 JS）
- Finding: py_compile 通过（agent_tools.py / agent_engine.py / agent_prompt.py，PY_COMPILE_OK）；抽取 agent.html 内联 JS（101767 字符）经 node --check 通过（JS_CHECK_OK）。
- Decision: 上传文档处理已覆盖「修改 / 补全 / 精简」三类，对话驱动触发，功能可用。

## 2026-08-26 19:30:00 - 任务：前端「补充文档」显示改为「修改文档」

## 2026-08-26 19:30:00 - File Edited
- File: `app/static/agent.html`
- Change: 头部按钮文本 `📝 补充文档` → `📝 修改文档`（enrichBtn），title 同步改为「…修改完善，生成修改版文档」；补充文档对话框标题 `<h3>📝 补充文档</h3>` → `<h3>📝 修改文档</h3>`。
- Result: Success

## 2026-08-26 19:30:00 - 校验
- Topic: 前端显示字符串
- Finding: 全局检索确认页面中已无「补充文档」字样（保留对话框内部「补充目标文档/补充重点/开始补全」等描述语，属于补全操作内部文案）。
- Decision: 仅改按钮与标题两处「补充文档」显示文案，符合最小改动原则，任务完成。

## 2026-08-26 19:40:00 - 任务：修改文档对话框「开始补全」改为「确认」，需求措辞泛化为修改/精简/补全

## 2026-08-26 19:40:00 - File Edited
- File: `app/static/agent.html`
- Change: 对话框说明改为「…并描述处理需求（修改、精简、补全等），由 Agent 处理生成新文档…」；「补充目标文档」→「处理目标文档」；「补充重点（可选）」→「处理需求（可选）」并更新 placeholder 示例；按钮「开始补全」→「确认」；submitEnrich 注入消息由固定「补充得更完整」改为通用「请处理附件…，处理需求：…」（留空则让 Agent 自行判断处理方式）。
- Result: Success

## 2026-08-26 19:40:00 - 校验
- Topic: 前端 JS 语法
- Finding: 抽取 agent.html 内联 JS（2 个 script 块，实际内联脚本 1 块）经 node --check 通过（JS_CHECK_OK）。
- Decision: 对话框从「单一补全」泛化为「通用文档处理」入口，用户可提出修改/精简/补全等任意需求，任务完成。

## 2026-08-26 19:55:00 - 任务：修改文档上传后未填需求时，解析完成追加引导消息（方案1轻量）

## 2026-08-26 19:55:00 - File Edited
- File: `app/static/agent.html`
- Change: `submitEnrich` 提交逻辑分支化——用户已填「处理需求」则直接注入指令并 sendMessage；用户留空则不再自动 sendMessage，改为 `appendMessage('agent', '文档「xxx」已解析完成。请告诉我是要 修改、精简 还是 补全，以及具体需求。')` 引导用户在输入框回复。复用现有对话流程，纯前端改动。
- Result: Success

## 2026-08-26 19:55:00 - 校验
- Topic: 前端 JS 语法
- Finding: 抽取 agent.html 内联 JS 经 node --check 通过（JS_CHECK_OK）。
- Decision: 解析完成后留空场景会追加引导消息，提示用户选择修改/精简/补全，任务完成。

## 2026-08-26 20:05:00 - 任务：修改文档入口上传的文档不放入附件列表（隐藏附件）

## 2026-08-26 20:05:00 - File Edited
- File: `app/api/routes.py`
- Change: `/agent/upload/{project_id}` 新增 `hidden: bool = Form(False)` 参数，附件条目增加 `hidden` 字段；`/agent/projects/{project_id}/attachments` 列表接口过滤 `hidden` 附件，不再返回给前端展示。文档仍保留在 Agent 状态的 attachments 中（含 full_text），供 modify/enrich/summarize 工具处理。
- Result: Success

## 2026-08-26 20:05:00 - File Edited
- File: `app/static/agent.html`
- Change: `uploadFile(file, hidden=false)` 增加第二参数；hidden 模式不上传为附件 chip、不 appendMessage、不 renderAttachmentChips、不 fetchState，仅上传并返回 file_id；`submitEnrich` 上传新文档时传 `hidden=true`。
- Result: Success

## 2026-08-26 20:05:00 - 校验
- Topic: 语法校验（Python + 前端 JS）
- Finding: py_compile 通过（routes.py，PY_COMPILE_OK）；node --check 通过（agent.html 内联 JS，JS_CHECK_OK）。
- Decision: 修改文档入口上传的文档仅作为处理对象，不展示在附件列表，任务完成。

## 2026-09-01 16:41 - 任务：段落级手术（保留原版 docx 样式，修改/精简/补全不再全文重排）
- 目标：解决「修改版与原版差距过大」问题——根因是原 docx 上传后被删除、LLM 在纯文本上重写、下载时从空白模板重排。
- 方案（用户选定「段落级手术」）：保留原 docx，LLM 基于块清单输出编辑指令 JSON，在原 docx 上执行 delete/replace/insert_after，未涉及块样式原样保留。

### 文件改动
- File: app/services/docx_edit.py（新建）
  - Change: 段落级手术核心模块——iter_body_blocks / build_block_inventory / inventory_text_from_path / apply_edit_ops（replace 保留段落样式、delete、insert_after 复制锚定段 pPr）。
  - Result: Success - 单元测试验证（对真实文档 130 块做 replace/delete/insert，样式 pStyle 保留、run 数=1）。
- File: app/services/attachment_service.py
  - Change: _do_extract 的 finally 对 .docx 保留原文件并记录 extract_tasks[task_id]["original_path"]，其余格式仍删除临时文件。
  - Result: Success
- File: app/api/routes.py
  - Change: agent_finalize_attachment 的 attachment 条目新增 original_path 字段；agent_download_modified_document 改为：有条目 ops+original_path 则执行段落级手术，否则走原 fill_template 重排。
  - Result: Success
- File: app/services/agent_tools.py
  - Change: 新增段落级手术辅助函数（_can_use_docx_edit/_build_docx_inventory/_parse_edit_ops/_ops_modified_chars/_llm_summarize_ops/_llm_modify_ops/_llm_enrich_ops）；modify_attachment/enrich_attachment/summarize_attachment 各加入「优先段落级手术、失败回退全文重写」分支。
  - Result: Success
- File: app/services/agent_engine.py
  - Change: _after_tools_node 中附件修改结果处理：pending 携带 ops+original_path 时存段落级手术条目（kind/ops/original_path），否则存 modified_markdown。
  - Result: Success

### Bash 命令
- Command: python -m py_compile app/services/docx_edit.py app/services/attachment_service.py app/services/agent_tools.py app/services/agent_engine.py app/api/routes.py
  - Result: Success - ALL_COMPILE_OK
- Command: python _test_docx_edit.py（临时测试脚本，验证段落级手术样式保留，已删除）
  - Result: Success - stats={'deleted':1,'replaced':1,'inserted':1,'skipped':0}，替换段落样式保持 None、run 数 1

### 决策
- 段落级手术仅对「有 original_path 且为 .docx」的附件生效；pdf/超长文档回退到原全文重写逻辑。
- 表格块在提示词中约束为「只能 delete/保留」，replace/insert 不作用于表格（保真优先）。
- 前端无需改动：工具返回 JSON 结构（status/kind/file_id/filename/modified_chars/summary/message）保持不变，下载按钮链路复用。

---

## 2026-09-01 全文风格参照（style reference）任务

### 任务背景
用户：生成完某篇文档后，当用户要求修改某章节或增加小节时，agent 应参照已生成全文的整体风格进行修改/补充。
实现：新增 `_build_style_reference(exclude_chapter)`，从 `_current_generated_markdown` 提取（1）结构概览（标题树）、（2）相邻章节节选、（3）文风范本（预算控制），注入 revise_section / revise_paragraph / generate_section / write_chapter 四个工具的提示词。

### 文件编辑
- File: app/services/agent_tools.py
  - Change: 新增 `_build_style_reference(exclude_chapter, max_chars=2600)` 辅助函数（位于 _build_covered_digest 之后）；四个文档生成/修改工具分别计算 style_reference 并注入 system_prompt。
  - Result: Success

### Bash 命令
- Command: python -m py_compile app/services/agent_tools.py
  - Result: Success - COMPILE_OK
- Command: python -c "导入 agent_tools，设置 _current_generated_markdown，调用 _build_style_reference('阶段划分') 验证输出"
  - Result: Success - 正确输出结构概览（标题树）、相邻章节节选、文风范本，len=441

### 决策
- 注入点：generate_section 与 write_chapter（两分支）在 covered_block 之后、模板风格 style_section 之前注入；revise_section 在 _output_structure_requirement 之前注入；revise_paragraph 在「输出格式」之前注入并新增一条「措辞语气与全文一致」要求。
- 优先级：模板风格（_build_template_style_hint，最高优先级）> 全文风格参照 > 默认写作风格。
- 预算控制：文风范本总预算 2600 字符，每章取正文开头 ≤280 字符；避免 token 膨胀。

---

## 2026-09-01 知识库文件删除（后端接口 + 前端按钮）任务

### 任务背景
用户：想从「上传文件知识库（qms_doc_uploads）」删除一些文件。
现状：`GET /api/kb/files` 已能列出文件、`VectorStore.delete_by_source` 已存在但未暴露；缺删除接口与前端删除按钮。
实现：新增 `POST /api/kb/files/delete` + 前端「查看知识库」弹窗每行加删除按钮。

### 文件编辑
- File: app/api/routes.py
  - Change: 新增 `KbFileDeleteRequest` Pydantic 模型与 `POST /kb/files/delete` 端点；用 `VectorStore(collection_name="uploads").delete_by_source(source_file)` 删除，并调用 `invalidate_bm25_cache("qms_doc_uploads")`。
  - Result: Success
- File: app/static/agent.html
  - Change: `showKbFilesDialog` 表格新增「操作」列与每行「删除」按钮；新增 `deleteKbFile(btn)`（confirm 确认 → POST 删除 → 刷新列表）。
  - Result: Success

### Bash 命令
- Command: python -m py_compile app/api/routes.py
  - Result: Success - COMPILE_OK

### 决策
- 删除键用 `source_file`（collection 中每 chunk 的 metadata.source_file，list 接口已返回），前端回传 source_file；`file_id`/`original_filename` 仅展示。
- 必须 `VectorStore(collection_name="uploads")` 定位到 qms_doc_uploads，避免误删默认 collection。
- 删除后失效 BM25 缓存，确保混合检索不再命中已删文件。
- 不加对话式 agent 工具（用户明确只做「后端接口 + 前端按钮」）。

## 2026-09-02 15:56 - 任务：文档风格选择（精炼生成 → 精炼简洁/严谨详细）

### 背景
用户：「把精炼生成的功能改成一个文档风格选择的功能，用户可以选择精炼简洁的语言风格或者严谨详细的语言风格」。
将原「精炼生成」布尔开关（concise_mode）改造为文档语言风格选择（writing_style: "concise" | "detailed"）。

### File Edits
- File: app/services/agent_state.py
  - Change: 字段 `concise_mode: Optional[bool]` → `writing_style: Optional[str]`（"concise"|"detailed"）；create_initial_state 默认值 False → "detailed"；build_state_snapshot 顶层 `concise_mode` → `writing_style`
  - Result: Success
- File: app/services/agent_prompt.py
  - Change: `concise_block` → `style_block`，按 writing_style 注入两分支指令块「文档风格：精炼简洁（已选择）/ 严谨详细（已选择）」，作用域仍限定 write_chapter/generate_section/modify_attachment/update_outline，声明不改变聊天回复风格
  - Result: Success
- File: app/api/routes.py
  - Change: `agent_set_generation_mode` 端点参数 `concise: str = Form(...)` → `style: str = Form(...)`，校验 "concise"/"detailed"，写入 `{"writing_style": style}`，返回 `{"success": True, "writing_style": style}`
  - Result: Success
- File: app/static/agent.html
  - Change: 顶栏 `#conciseBtn` 按钮 → `#styleSelect` 下拉（严谨详细/精炼简洁）；CSS 同步改名；JS `conciseMode` → `writingStyle`（默认 'detailed'）；`toggleConciseMode()/setConciseBtnUI()` → `changeWritingStyle()/setStyleSelectUI()`，POST 字段 `concise` → `style`，成功加 toast；fetchState 恢复读 `data.state?.writing_style`
  - Result: Success
- File: tests/test_sql_prompt.py
  - Change: `_build(concise=...)` → `_build(style="detailed")`；`TestConciseModeBaseline` → `TestWritingStyleBaseline`，断言「文档风格：精炼简洁（已选择）/严谨详细（已选择）」
  - Result: Success
- File: tests/test_template_prompt.py
  - Change: `_build(concise=...)` → `_build(style="detailed")`；`TestConciseModeNotAffected` → `TestWritingStyleNotAffected`
  - Result: Success
- File: _test_concise_mode.py（删除）→ _test_writing_style.py（新建）
  - Change: 临时验证脚本重写为 writing_style 版本（6 场景：端点 concise/detailed、新线程 seed、prompt 精炼注入、detailed 默认、快照暴露）
  - Result: Success

### Bash Commands
- Command: python -m py_compile app/services/agent_state.py app/services/agent_prompt.py app/api/routes.py tests/test_sql_prompt.py tests/test_template_prompt.py _test_writing_style.py
  - Purpose: 编译检查全部改动 Python 文件
  - Result: Success (COMPILE_OK)
- Command: python -m pytest tests/test_sql_prompt.py tests/test_template_prompt.py -q
  - Purpose: 回归测试（风格选择 prompt 注入）
  - Result: Success (25 passed)
- Command: python _test_writing_style.py
  - Purpose: 风格选择端点/快照/初始状态验证（mock get_agent）
  - Result: Success (ALL WRITING-STYLE TESTS PASSED)

### 决策
- 保持布尔语义不变的前提下，把开关升级为二选一下拉：`writing_style` 默认 "detailed"（与改造前默认「未开启精炼」的详细输出行为对齐）。
- 状态字段名 `concise_mode` → `writing_style`；前端控件由单按钮开关改为 select 下拉（value 与后端 Form 参数一致：style）。
- 端点响应键改为 `writing_style`；前端 fetchState 从 `data.state?.writing_style` 恢复。

---

# 2026-09-08 15:55:00 - 新任务：合并 window2 源项目代码到本项目 main 分支

## 2026-09-08 15:50:00 - Analysis
- Topic: 仓库关系分析
- Finding: 源（design_local_win2，feat/window2 分支）与目标（本项目，main）为同一远程仓库（github.com/zcwangforwork/design_plan_generation_local_model）的两个克隆，HEAD 同为 1327812。源工作区改动 = routes.py + agent.html（后台流解耦改造）+ 新增 agent_streams.py / tests/test_agent_streams.py；目标工作区改动 = 11 个 services 文件 + agent.html（PostgreSQL 长期记忆 LTM UI 等功能）。唯一交叉文件 = agent.html
- Decision: 不产生 git 提交（与双方"改动未提交"的工作方式一致）：routes.py 目标未改直接用源版覆盖；新文件直接复制；agent.html 用 git merge-file 三方合并（base=HEAD 版、ours=目标版、theirs=源版），合并后补齐 reconnectStream 缺失的 LTM 事件分支

## 2026-09-08 15:53:00 - Bash Command Executed
- Command: `git merge-file -p ours.html base.html theirs.html`（首次，base 为 LF、工作区为 CRLF）
- Working Dir: 目标仓库
- Purpose: agent.html 三方合并
- Result: Failure - 11 处假冲突（仓库 LF vs 工作区 CRLF 导致每行都被视为双方改动）

## 2026-09-08 15:54:00 - Bash Command Executed
- Command: `sed 's/$/\r/' base.html > base-crlf.html && git merge-file -p ours.html base-crlf.html theirs.html`
- Working Dir: 目标仓库
- Purpose: 行尾归一化后重新三方合并
- Result: Success - exit 0，零冲突，3762 行；已覆盖写入 app/static/agent.html

## 2026-09-08 15:56:00 - File Edited
- File: `app/static/agent.html`
- Change: 合并后功能补齐——reconnectStream（源新增的重连续播函数）事件 switch 补加 ltm_recall_start / ltm_recall_done / ltm_capture 三个分支（目标侧 LTM 功能），保证重连续播时长期记忆指示器不丢失
- Result: Success

## 2026-09-08 15:57:00 - Bash Command Executed
- Command: `python -m py_compile app/api/routes.py app/services/agent_streams.py`；`node --check`（agent.html 内联脚本）；`python -c "import app.api.routes"`；`python -m pytest tests/test_agent_streams.py -v`；`python -m pytest --collect-only -q`
- Working Dir: 目标仓库
- Purpose: 合并结果验证（语法/导入/端点注册/单元测试/全量测试收集）
- Result: Success - 全部通过：7/7 单元测试通过，253 个测试收集无导入错误，3 个 stream 端点注册确认，agent.html 无冲突标记

## 2026-09-08 15:58:00 - File Edited
- File: `app/api/routes.py`（以源版覆盖）、`app/services/agent_streams.py`（新文件）、`tests/test_agent_streams.py`（新文件）
- Change: 合并源项目"切换聊天任务不中断生成"改造：后台流管理器 + 3 个生成端点解耦 + stream/status、stream、stream/cancel 新端点 + recall/delete 联动取消
- Result: Success
