# 医疗器械体系文件审核 Agent v2.0 项目介绍

## 1. 项目概述

**医疗器械体系文件审核 Agent** 是一个面向医疗器械企业的 AI 驱动体系文件智能审核系统。系统基于大语言模型（LLM），结合 RAG（检索增强生成）、多代理协作（Multi-Agent）和本地化部署，能够对用户上传的体系文件（Word/PDF）进行分章节智能审核，输出缺失内容清单、修改建议和法规条款依据，并支持对话式交互审核、重审和报告导出。

系统覆盖 ISO 13485、ISO 14971、IEC 62304、EU MDR、FDA 21 CFR Part 820、NMPA GMP 等国际/国内法规标准，适用于质量手册、程序文件（SOP）、设计开发文件（DHF）、风险管理文档、软件生命周期文档等各类体系文件的合规性审核。

### 1.1 核心价值

- **智能审核**：基于 RAG + LLM 的分章节深度审核，自动识别缺失内容和合规性问题
- **法规关联**：自动关联适用法规条款，附条款引用校验防止 LLM 编造条款号
- **多代理并行**：章节级并行审核（Send API fan-out），大幅缩短长文档审核时间
- **对话式交互**：支持对话模式，用户可在审核各阶段介入确认、反馈、重审
- **本地化部署**：支持本地 Ollama LLM + 本地 MinerU 视觉解析，数据不出企业
- **报告导出**：一键导出 Word 格式审核报告

### 1.2 审核范围

| 文件类型 | 说明 |
|----------|------|
| 质量手册 | 质量管理体系总纲文件 |
| 程序文件（SOP） | 标准操作规程 |
| 设计开发文件（DHF） | 设计历史文件 |
| 风险管理文档 | ISO 14971 风险管理文件 |
| 软件生命周期文档 | IEC 62304 软件开发文件 |
| 采购/供应商管理文件 | 供应商管理相关文件 |
| 生产/检验文件 | 生产与检验规程 |
| 不良事件/CAPA/召回文件 | 上市后监管文件 |

**参考法规标准**：
- ISO 13485:2016 医疗器械质量管理体系
- ISO 14971:2019 医疗器械风险管理
- IEC 62304 医疗器械软件生命周期过程
- EU MDR 2017/745 欧盟医疗器械法规
- FDA 21 CFR Part 820 质量体系法规
- NMPA 医疗器械生产质量管理规范

---

## 2. 项目目录结构

```
project_0428_beta/
├── backend/                                # 后端主目录
│   ├── main.py                             # FastAPI 主程序（120KB，含全部 API 端点）
│   ├── agent_graph.py                      # ★ 单 Agent StateGraph（95KB，图拓扑+节点+路由+HITL）
│   ├── agent_state.py                      # ★ AuditState 状态定义（LangGraph TypedDict）
│   ├── agent_tools.py                      # ★ Agent 工具集（5 个 @tool）
│   ├── multi_agent/                        # ★ 多 Agent 协作模块
│   │   ├── __init__.py                     # 公共导出
│   │   ├── state.py                        # MultiAgentState 状态定义
│   │   ├── agents.py                       # 3 个子 Agent（结构分析/章节审核/综合报告）
│   │   └── supervisor_graph.py             # Supervisor StateGraph（Send API fan-out + HITL）
│   ├── rag_retriever.py                    # RAG 检索引擎（114KB，向量检索+LLM重排序）
│   ├── vector_store.py                     # ChromaDB 向量存储封装
│   ├── doc_processor.py                    # 文档处理（54KB，Word/PDF解析+结构提取+MinerU）
│   ├── clause_citation_validator.py        # ★ 法规条款引用校验器（防编造）
│   ├── chat_rag.py                         # 对话 RAG 辅助
│   ├── mineru_service.py                   # ★ MinerU 本地视觉解析服务
│   ├── mineru_local.py                     # MinerU 本地模型调用
│   ├── mineru_runner.py                    # MinerU 子进程隔离执行
│   ├── build_knowledge_base.py             # 知识库构建脚本
│   ├── ingest_all.py                       # 全量文档摄入脚本
│   ├── build_all_medical.py               # 医疗标准全量构建
│   ├── rebuild_medical_standards.py       # 医疗标准重建
│   ├── requirements.txt                    # Python 依赖
│   ├── .env                                # 环境变量配置
│   ├── data/                               # 数据目录
│   ├── docs/                               # 后端文档
│   ├── logs/                               # 日志目录
│   ├── tests/                              # 测试目录
│   ├── test_*.py                           # 测试脚本（集成/多Agent/向量库/JSON修复）
│   └── check_*.py / compare_dir.py        # 诊断与对比工具
├── frontend/                               # 前端目录
│   ├── index.html                          # 旧版审核界面（79KB）
│   └── agent.html                          # ★ 新版 Agent 对话审核界面（45KB）
├── checkpoints/                            # ★ 状态持久化
│   ├── conversation.db                     # 对话状态（46MB SQLite）
│   └── multi_agent.db                      # 多 Agent 状态（4.5MB SQLite）
├── docs/                                   # 项目文档
├── develop_documents/                      # 知识库源文件（医疗器械体系模板）
├── SPEC.md                                 # 规格文档
├── TODOS.md                                # 待办事项
├── README.md                               # 项目介绍（本文件）
├── run_build_kb.py                         # 知识库构建启动脚本
├── test_analyze.py                         # 分析测试
├── 企业级agent.docx                        # 企业级 Agent 设计文档
└── 胰岛素泵-DHF清单.xlsx                   # DHF 清单参考
```

> **图例**：`★` 标记为 v2.0 新增模块。

---

## 3. 技术架构

### 3.1 技术栈总览

| 层级 | 技术选型 | 用途 |
|------|----------|------|
| Web 前端 | HTML + JavaScript + TailwindCSS | 旧版审核界面 + 新版 Agent 对话界面 |
| 后端框架 | FastAPI + uvicorn + httpx | RESTful API + SSE 流式输出 |
| **Agent 框架** | **LangGraph + LangChain** | **StateGraph 图拓扑，HITL interrupt，检查点持久化** |
| **LLM 模型** | **Ollama (qwen3.5:122b)** | **本地化大语言模型，OpenAI 兼容接口** |
| LangChain 集成 | langchain-openai | ChatOpenAI 兼容 Ollama |
| 状态持久化 | langgraph-checkpoint-sqlite + aiosqlite | SQLite 检查点，支持中断恢复 |
| 向量数据库 | ChromaDB | 法规知识库向量存储 + 语义检索 |
| **RAG 重排序** | **LLM Listwise Rerank** | **检索结果 LLM 二次排序** |
| 嵌入模型 | MiniMax embed-multilingual-v2 | 文本向量化 |
| **文档解析** | **MinerU2.5-Pro（本地视觉模型）** | **opt-in，PDF/Office/图片视觉解析** |
| 文档处理 | python-docx + pdfplumber + PyMuPDF | Word/PDF 文本提取与结构解析 |
| **条款校验** | **clause_citation_validator.py** | **正则提取+比对，防 LLM 编造法规条款号** |
| 报告导出 | python-docx | 审核报告 Word 导出 |
| 异步处理 | asyncio + Semaphore | 章节级/小节级并发控制 |
| 测试 | pytest | 集成测试 |

### 3.2 系统架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Web Browser                                   │
│   ┌──────────────────┐   ┌──────────────────────────────────────┐    │
│   │ /  旧版审核界面   │   │ /agent  Agent 对话审核界面            │    │
│   │ index.html       │   │ agent.html                           │    │
│   └────────┬─────────┘   └──────────────────┬───────────────────┘    │
└────────────┼────────────────────────────────┼────────────────────────┘
             │                                │ SSE 流式
             ▼                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (port 8000)                          │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  旧版 API          单 Agent API          多 Agent API           │  │
│  │  /api/chat         /api/agent/analyze    /api/multi-agent/...   │  │
│  │  /api/upload       /api/agent/conv/*     /api/multi-agent/conv/*│  │
│  │  /api/analyze      (SSE 流式)            (SSE 流式)             │  │
│  │  /api/segment-*    /api/export-review                           │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                              │                                        │
│         ┌────────────────────┼─────────────────────┐                 │
│         ▼                    ▼                      ▼                 │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │ 单 Agent 图   │  │ ★ 多 Agent 图    │  │  RAG 引擎            │   │
│  │ agent_graph   │  │ supervisor_graph │  │  rag_retriever       │   │
│  │               │  │                  │  │  (向量+LLM重排序)    │   │
│  │ analyze_outline│ │ analyze_structure│  └──────────────────────┘   │
│  │ plan_strategy │  │ audit_chapter ×N │                             │
│  │ audit_section │  │ synthesize_report│  ┌──────────────────────┐   │
│  │ cross_validate│  │ + HITL 检查点    │  │ ★ 条款引用校验器     │   │
│  │ generate_report│ │ + 对话循环       │  │ clause_citation_val  │   │
│  └──────┬────────┘  └────────┬─────────┘  └──────────────────────┘   │
│         │                    │                                        │
│         ▼                    ▼                                        │
│  ┌──────────────────────────────────────┐  ┌──────────────────────┐  │
│  │ ★ Ollama LLM (qwen3.5:122b)          │  │ ★ MinerU 视觉解析    │  │
│  │ ChatOpenAI 兼容接口                   │  │ (opt-in 子进程隔离)  │  │
│  └──────────────────────────────────────┘  └──────────────────────┘  │
│                                                                       │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │ doc_processor│  │ vector_store     │  │ checkpoints/         │   │
│  │ Word/PDF解析 │  │ ChromaDB         │  │ conversation.db      │   │
│  └──────────────┘  └──────────────────┘  │ multi_agent.db       │   │
│                                          └──────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. 核心模块详解

### 4.1 ★ 单 Agent 审核图（agent_graph.py，95KB）

基于 LangGraph StateGraph 构建的文档审核流水线，支持两种拓扑模式：

**并行模式（默认）**：
```
analyze_outline -> plan_strategy -> batch_audit_all_sections
                                     -> cross_validate -> generate_report -> END
```

**顺序模式（向后兼容）**：
```
analyze_outline -> plan_strategy -> audit_section -> evaluate_result
                                     -> update_context -> [next_section | done]
                                     -> cross_validate -> generate_report -> END
```

**节点说明**：
| 节点 | 功能 |
|------|------|
| `analyze_outline` | 文档结构分析，识别章节/小节层级 |
| `plan_strategy` | 审核策略规划，为每小节分配审核深度（quick/standard/deep）+ 预检索知识库上下文 |
| `batch_audit_all_sections` | 并行审核所有小节（asyncio.gather + Semaphore 并发） |
| `audit_section` | 顺序审核单个小节 |
| `evaluate_result` | 解析审核结果（JSON metadata + 评分） |
| `update_context` | 更新跨章节上下文 |
| `cross_validate` | 跨章节交叉验证，发现矛盾 |
| `generate_report` | 生成最终审核报告 |

**HITL 检查点**：通过 `interrupt()` 暂停，等待用户确认/反馈/重审。

### 4.2 ★ 多 Agent 协作图（multi_agent/supervisor_graph.py，27KB）

基于 LangGraph Subagents + Send API 模式的多代理协作架构：

```
START
  │
  ▼
analyze_structure        (结构分析 Agent - 一次)
  │
  │  Send API fan-out（每个章节一个 Send packet）
  ▼
audit_chapter ×N         (章节审核 Agent - 章节级并行)
  │
  │  reducer 自动汇集 chapter_results
  ▼
synthesize_report        (综合报告 Agent - 一次)
  │
  ▼
END
```

**三个子 Agent**（`multi_agent/agents.py`）：
| 子 Agent | 职责 |
|----------|------|
| `analyze_structure_agent` | 结构分析：将 outline + sections 整理成章节级结构 |
| `audit_chapter_agent` | 章节审核：内部循环每个小节（Semaphore 小节级并发） |
| `synthesize_report_agent` | 综合报告：汇总章节结果，发现矛盾，生成最终报告 |

**对话模式扩展**（HITL 检查点 + 对话循环）：
| 检查点 | 说明 |
|--------|------|
| `checkpoint_structure` | 分章确认：结构分析后暂停，用户确认章节划分 |
| `checkpoint_post_audit` | 审核结果确认：章节审核完成后暂停，用户反馈 |
| `checkpoint_post_completion` | 报告完成确认：报告生成后暂停，用户可重审或结束 |

**对话循环能力**：
- **重审（re-audit）**：用户指定章节重新审核（上限 3 次循环）
- **跳过（skip）**：用户跳过指定章节
- **对话（chat）**：自由对话，`summarize_conversation` 压缩长对话历史
- **修订请求**：用户提交修订请求队列

### 4.3 ★ AuditState 状态定义（agent_state.py）

LangGraph TypedDict，含丰富的审核状态字段：

- **文档信息**：`document_text` / `document_type` / `outline` / `sections`
- **结构概览**：`outline_summary`（章节数、小节数、章节树）
- **审核策略**：`audit_plan`（每小节审核深度 + 关注标准）/ `knowledge_context`（预检索法规原文）
- **审核进度**：`current_section_idx` / `round_count` / `total_agent_steps`
- **审核结果**：`audit_results`（每小节的 findings/score/confidence）
- **跨章节上下文**：`global_context`（`operator.add` 追加）
- **对话交互**：`current_stage` / `user_feedback` / `revision_requests` / `re_audit_sections` / `skip_sections`
- **长程记忆**：`summary`（对话摘要，防 token 膨胀）
- **最终输出**：`contradictions` / `final_report`

### 4.4 ★ Agent 工具集（agent_tools.py，5 个工具）

| 工具 | 功能 |
|------|------|
| `parse_document` | 解析文档结构，返回树状大纲和审核单元列表 |
| `rag_search` | RAG 知识库语义检索 |
| `check_regulation` | 法规条款核查 |
| `assess_completeness` | 章节完整性评估 |
| `audit_section` | 章节审核（含 RAG 上下文 + 审核深度 + 文档类型） |

### 4.5 RAG 检索引擎（rag_retriever.py，114KB）

- **向量检索**：ChromaDB 语义检索
- **★ LLM Listwise Rerank**：检索结果 LLM 二次排序（`_llm_rerank_listwise_sync`）
- **小节级检索**：`_retrieve_for_section` 按小节内容精准检索
- **文档分析**：`analyze_document` 全文档 RAG 分析（含 fallback）
- **分段审核**：`audit_segment` 分段审核模式
- **上下文构建**：`build_context` 含对比模式（`use_contrast_mode`）
- **领域专项 Prompt**：`SECTION_PROMPTS` 按文档类型加载专属审核检查清单

### 4.6 ★ 法规条款引用校验器（clause_citation_validator.py）

防止 LLM 编造未在检索片段中出现的法规条款号：

1. 从 LLM 输出中正则提取所有"标准号+条款号"组合（ISO/IEC/GB/T/YY/T/NMPA/MDR/FDA）
2. 从检索片段（section_knowledge）中提取合法条款号集合
3. 比对：LLM 引用的条款号不在合法集合中 -> 标注"⚠ 引用待核实"
4. 知识库片段中条款号 < 2 个时跳过校验（避免误报）
5. 不阻断主流程：任何异常仅 log warning

### 4.7 ★ MinerU 文档解析（mineru_*.py）

opt-in 的本地视觉文档解析服务：
- **模型**：MinerU2.5-Pro-2605-1.2B（本地部署）
- **启用方式**：环境变量 `USE_MINERU=true`
- **支持格式**：PDF / DOCX / DOC / PPTX / XLSX / 图片
- **子进程隔离**：`mineru_runner.py` 独立子进程执行，避免 torch/transformers 冲突
- **回退机制**：未启用时回退到 python-docx / pdfplumber

### 4.8 文档处理（doc_processor.py，54KB）

- Word/PDF 文本提取（python-docx / pdfplumber / PyMuPDF）
- 文档结构解析：outline（树状大纲）+ sections（平铺小节列表）
- MinerU 视觉解析集成

---

## 5. API 接口

### 5.1 旧版 API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 旧版审核前端页面 |
| GET | `/health` | 健康检查（含向量库状态） |
| GET | `/info` | 服务信息 |
| POST | `/api/chat` | 通用聊天 |
| POST | `/api/upload` | 上传文档 |
| POST | `/api/analyze` | RAG 智能审核 |
| POST | `/api/clear` | 清除会话 |
| GET | `/api/history/{session_id}` | 获取会话历史 |
| GET | `/api/vectorstore/status` | 向量库状态 |

### 5.2 ★ 单 Agent API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/agent` | Agent 对话前端页面 |
| POST | `/api/agent/analyze` | Agent 审核（SSE 流式） |
| POST | `/api/agent/conversation/start` | 启动对话审核 |
| GET | `/api/agent/conversation/stream/{session_id}` | 对话流（SSE） |
| POST | `/api/agent/conversation/message` | 发送对话消息 |
| POST | `/api/agent/conversation/reaudit` | 请求重审 |
| GET | `/api/agent/conversation/state/{session_id}` | 获取审核状态 |
| GET | `/api/agent/conversation/report/{session_id}` | 获取审核报告 |

### 5.3 ★ 多 Agent API

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/multi-agent/analyze` | 多 Agent 审核（SSE 流式） |
| POST | `/api/multi-agent/conversation/start` | 启动多 Agent 对话审核 |
| POST | `/api/multi-agent/conversation/message` | 发送对话消息 |
| GET | `/api/multi-agent/conversation/stream/{session_id}` | 对话流（SSE） |
| GET | `/api/multi-agent/conversation/state/{session_id}` | 获取审核状态 |
| GET | `/api/multi-agent/conversation/report/{session_id}` | 获取审核报告 |

### 5.4 分段审核 API

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/analyze-segment` | 分段分析 |
| GET | `/api/segment-status/{session_id}` | 分段状态 |
| POST | `/api/segment-synthesize` | 分段综合 |
| POST | `/api/segment-reset` | 重置分段 |

### 5.5 报告导出 API

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/export-review` | 导出 Word 格式审核报告 |

---

## 6. 知识库

### 6.1 知识库源文件（develop_documents/）

预处理的医疗器械体系模板文件，覆盖：
- 质量管理体系模板
- 风险管理模板
- 软件资料模板
- 产品技术要求模板
- 使用说明书模板
- 作业指导书模板
- 设计开发表格
- 验证/有效期/可用性模板

### 6.2 向量存储

- **数据库**：ChromaDB 本地持久化
- **嵌入模型**：MiniMax embed-multilingual-v2
- **构建脚本**：`build_knowledge_base.py` / `ingest_all.py` / `build_all_medical.py`

### 6.3 状态持久化

| 数据库 | 用途 |
|--------|------|
| `checkpoints/conversation.db` | 单 Agent 对话状态（46MB SQLite） |
| `checkpoints/multi_agent.db` | 多 Agent 协作状态（4.5MB SQLite） |

---

## 7. 启动与运行

### 7.1 环境要求

- Python 3.10+
- Conda 环境（env_01）
- **Ollama**（本地 LLM 服务，qwen3.5:122b）
- ChromaDB
- **MinerU**（可选，`USE_MINERU=true` 启用本地视觉解析）

### 7.2 安装依赖

```bash
conda activate env_01
cd backend
pip install -r requirements.txt
```

### 7.3 预处理知识库

```bash
cd backend
python build_knowledge_base.py --docs-dir ../develop_documents
# 或全量摄入
python ingest_all.py
```

### 7.4 启动服务

```bash
conda activate env_01
cd backend
python main.py
```

服务启动后访问：
- **旧版审核界面**：http://localhost:8000/
- **★ Agent 对话审核**：http://localhost:8000/agent

### 7.5 环境变量（.env）

```bash
# MinerU 文档解析（可选）
USE_MINERU=false                         # 启用本地视觉解析
MINERU_LOCAL_MODEL_PATH=E:\model\MinerU2.5-Pro-2605-1.2B
MINERU_TIMEOUT=1200                      # 单文件解析超时（秒）
```

LLM 通过 Ollama 本地服务（默认 `http://localhost:11435/v1`），在 `main.py` / `rag_retriever.py` 中配置。

---

## 8. 测试

| 文件 | 功能 |
|------|------|
| `test_main_integration.py` | 主程序集成测试 |
| `test_multi_agent.py` | 多 Agent 协作测试 |
| `test_vector_store_batching.py` | 向量库批量操作测试 |
| `test_repair_json.py` | JSON 修复测试 |
| `test_embedding.py` | 嵌入模型测试 |
| `test_analyze.py` | 分析功能测试 |

---

## 9. 项目演进历程

1. **MVP 阶段（v1）**：基础 RAG 审核，FastAPI + MiniMax API + ChromaDB，单次分析
2. **文档处理增强阶段**：python-docx/pdfplumber 文本提取，文档结构解析
3. **分段审核阶段**：`/api/analyze-segment` 分段分析 + 综合
4. **★ 单 Agent 图阶段（v2）**：LangGraph StateGraph 审核流水线（并行/顺序模式），HITL 检查点，对话模式
5. **★ 多 Agent 协作阶段（v2）**：Supervisor Graph + Send API 章节级并行，3 个子 Agent，对话循环（重审/跳过/对话）
6. **★ 本地化阶段**：Ollama qwen3.5:122b 替代 MiniMax API，MinerU 本地视觉解析
7. **★ 质量增强阶段**：LLM Listwise Rerank 重排序，法规条款引用校验器，领域专项审核 Prompt

---

## 10. 注意事项

1. **本地 LLM**：需先启动 Ollama 服务并拉取 qwen3.5:122b 模型
2. **知识库构建**：首次使用需运行 `build_knowledge_base.py` 预处理文档
3. **MinerU**：opt-in 功能，需设置 `USE_MINERU=true` 并下载本地模型
4. **审核结果**：本系统输出仅供参考，请结合法规专家意见使用
5. **状态持久化**：`checkpoints/` 目录下的 SQLite 数据库支持中断恢复
