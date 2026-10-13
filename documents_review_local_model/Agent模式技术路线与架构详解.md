# 医疗器械体系文件审核 Agent 模式技术路线与架构详解

> 本文档详细阐述 `documents_review_local_model/project_0428_beta` 项目 Agent 模式的技术选型、分层架构、LangGraph 图拓扑、多代理协作、HITL 人机交互、状态持久化、对话循环、RAG 检索、条款引用校验、SSE 流式输出与上下文管理等核心技术路线。

---

## 目录

1. [技术概览](#1-技术概览)
2. [技术选型与理由](#2-技术选型与理由)
3. [分层架构](#3-分层架构)
4. [单 Agent 审核图（agent_graph.py）](#4-单-agent-审核图agent_graphpy)
5. [多 Agent 协作图（multi_agent/supervisor_graph.py）](#5-多-agent-协作图multi_agentsupervisor_graphpy)
6. [HITL 人机交互机制](#6-hitl-人机交互机制)
7. [对话循环与重审机制](#7-对话循环与重审机制)
8. [状态持久化与中断恢复](#8-状态持久化与中断恢复)
9. [AuditState 与 MultiAgentState 设计](#9-auditstate-与-multiagentstate-设计)
10. [工具系统（agent_tools.py）](#10-工具系统agent_toolspy)
11. [RAG 检索架构](#11-rag-检索架构)
12. [法规条款引用校验](#12-法规条款引用校验)
13. [SSE 流式输出](#13-sse-流式输出)
14. [上下文管理与长程记忆](#14-上下文管理与长程记忆)
15. [System Prompt 工程](#15-system-prompt-工程)
16. [技术风险与缓解措施](#16-技术风险与缓解措施)
17. [架构总结](#17-架构总结)

---

## 1. 技术概览

本项目是一个面向医疗器械体系文件的 AI 智能审核系统，Agent 模式是其核心能力层。系统提供 **两套并行的 Agent 图实现**，覆盖从一次性自动审核到多轮对话式审核的全场景：

| 图实现 | 文件 | 核心特征 |
|--------|------|---------|
| **单 Agent 图** | `backend/agent_graph.py` (95KB) | 一个 StateGraph 串行/并行执行所有审核节点，含 3 种拓扑 |
| **多 Agent 图** | `backend/multi_agent/supervisor_graph.py` (27KB) | Supervisor + Send API 章节级并行，3 个子 Agent 分工 |

**核心能力矩阵**：

| 能力 | 实现方式 |
|------|---------|
| 文档结构分析 | 正则 + LLM 兜底，识别章节/小节层级 |
| 审核策略规划 | 按小节分配 quick/standard/deep 深度 + 预检索知识库 |
| 并行审核 | 单图 asyncio.gather + 多图 Send API fan-out |
| HITL 人机交互 | `interrupt()` + `Command(resume=...)`，3 个检查点 |
| 对话循环 | re-audit (上限 3 次) / skip / chat / summarize |
| RAG 检索 | ChromaDB 向量检索 + LLM Listwise Rerank |
| 反幻觉校验 | 法规条款引用校验器（正则提取 + 比对） |
| 状态持久化 | SQLite checkpointer，支持中断恢复 |
| 流式输出 | SSE + `astream(stream_mode=["messages","updates"])` |
| 长程记忆 | 对话摘要压缩 (触发阈值 16 条，保留近 6 条) |

---

## 2. 技术选型与理由

### 2.1 Agent 框架：LangGraph + LangChain

**选型**：LangGraph StateGraph + LangChain ChatOpenAI

**理由**：

| 候选方案 | 优点 | 劣势 | 本项目选择理由 |
|----------|------|------|---------------|
| **LangGraph** | 原生 StateGraph、interrupt、Send API、checkpointer、条件边 | 学习曲线陡 | ✅ interrupt + checkpointer 是 HITL 对话审核的刚需 |
| LangChain Agent Executor | 成熟、文档全 | 无原生状态机、HITL 需手搓 | ❌ 无法优雅表达"分章确认→审核→重审"循环 |
| AutoGen | 多 Agent 对话原生 | 偏对话场景，无持久化 | ❌ 审核是流水线而非自由对话 |
| CrewAI | 角色分工清晰 | 无 Send API 级并行 | ❌ 章节级 fan-out 并行能力弱 |

**关键 LangGraph 特性使用**：
- `StateGraph(TypedDict)` — 类型化状态图
- `interrupt(value)` — HITL 暂停
- `Command(resume=...)` — 恢复执行
- `Send(node, input)` — 条件边 fan-out 并行调度
- `Annotated[List, operator.add]` — reducer 自动合并并行结果
- `AsyncSqliteSaver` — 异步 SQLite 检查点持久化
- `add_messages` reducer — 消息历史自动追加

### 2.2 LLM：Ollama 本地化

**选型**：Ollama qwen3.5:122b，通过 OpenAI 兼容接口（ChatOpenAI）接入

```python
# agent_graph.py:123
def create_llm(temperature=0.3, max_tokens=4096, **kwargs) -> ChatOpenAI:
    params = dict(
        model=os.getenv("OPENAI_MODEL", "qwen3.5:122b"),
        base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11435/v1"),
        api_key=_DEFAULT_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=3,
        streaming=True,        # 流式输出
        request_timeout=600,   # 10 分钟超时
    )
```

**理由**：
- **数据合规**：医疗器械体系文件含企业敏感信息，数据不出企业
- **OpenAI 兼容**：通过 `langchain-openai` 的 `ChatOpenAI` 直接接入，无需改代码
- **streaming=True**：配合 LangGraph `stream_mode="messages"` 实现 token 级实时渲染
- **128K 上下文**：可容纳长文档 + RAG 上下文 + 对话历史

### 2.3 双图模式设计

**设计**：单 Agent 图 + 多 Agent 图并存

**理由**：
- **单 Agent 图**：适合中小文档、一次性审核、向后兼容
- **多 Agent 图**：适合长文档、章节级并行、对话式审核
- **API 层统一**：两套图通过独立的 API 端点暴露（`/api/agent/*` vs `/api/multi-agent/*`），前端可按场景选择
- **代码复用**：多 Agent 的子 Agent 函数复用单 Agent 的 `_build_audit_system_prompt` / `_extract_json` / `generate_report_node` 等核心逻辑

### 2.4 状态持久化：SQLite Checkpointer

**选型**：`langgraph-checkpoint-sqlite` + `aiosqlite`

**理由**：
- **中断恢复**：对话审核可能跨多个会话，SQLite 持久化检查点
- **thread_id 隔离**：每个审核会话用唯一 `thread_id`，状态互不干扰
- **轻量**：无需额外数据库服务，单文件 SQLite
- **异步友好**：`AsyncSqliteSaver` 配合 FastAPI 异步栈

实际持久化文件：
- `checkpoints/conversation.db` (46MB) — 单 Agent 对话状态
- `checkpoints/multi_agent.db` (4.5MB) — 多 Agent 协作状态

---

## 3. 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  API 层 (main.py)                                                │
│  - 旧版 API (/api/chat, /api/analyze)                            │
│  - 单 Agent API (/api/agent/conv/*)                              │
│  - 多 Agent API (/api/multi-agent/conv/*)                        │
│  - SSE 流式端点 + 会话管理 (_conversation_sessions)               │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  Graph 层 (LangGraph StateGraph)                                 │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐  │
│  │ 单 Agent 图          │  │ 多 Agent Supervisor 图           │  │
│  │ - build_audit_graph  │  │ - build_supervisor_graph         │  │
│  │ - build_conversation │  │ - 3 个子 Agent                  │  │
│  │   _graph             │  │ - Send API fan-out              │  │
│  │ - 3 种拓扑模式       │  │ - 3 个 HITL 检查点              │  │
│  └──────────┬──────────┘  └──────────────┬───────────────────┘  │
└─────────────┼─────────────────────────────┼─────────────────────┘
              │                             │
┌─────────────▼─────────────────────────────▼─────────────────────┐
│  节点/工具层                                                      │
│  - agent_tools.py (5 个 @tool)                                   │
│  - agent_graph.py 节点函数 (analyze_outline/plan_strategy/       │
│    batch_audit/cross_validate/generate_report/checkpoint)        │
│  - multi_agent/agents.py (3 个子 Agent 函数)                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  能力层                                                           │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │ RAG 检索     │ │ 文档解析     │ │ 条款引用校验              │ │
│  │ rag_retriever│ │ doc_processor│ │ clause_citation_validator │ │
│  │ - 向量检索   │ │ - Word/PDF   │ │ - 正则提取                │ │
│  │ - LLM Rerank │ │ - MinerU     │ │ - 比对合法条款集          │ │
│  │ - 领域 Prompt│ │ - 结构提取   │ │ - 标注"引用待核实"        │ │
│  └──────┬───────┘ └──────┬───────┘ └──────────────────────────┘ │
└─────────┼────────────────┼──────────────────────────────────────┘
          │                │
┌─────────▼────────────────▼──────────────────────────────────────┐
│  基础设施层                                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │ Ollama LLM   │ │ ChromaDB     │ │ SQLite Checkpoints       │ │
│  │ qwen3.5:122b │ │ 向量库       │ │ conversation.db          │ │
│  │ :11435/v1    │ │              │ │ multi_agent.db           │ │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 单 Agent 审核图（agent_graph.py）

单 Agent 图基于 `StateGraph(AuditState)` 构建，支持 **三种拓扑模式**，覆盖一次性审核与对话式审核。

### 4.1 三种拓扑模式

#### 模式一：并行审核图（`build_audit_graph`，默认）

```
analyze_outline -> plan_strategy -> batch_audit_all_sections
                                     -> cross_validate -> generate_report -> END
```

由 `PARALLEL_AUDIT_ENABLED=true`（默认）启用，`batch_audit_all_sections_node` 内部使用 `asyncio.gather + Semaphore(AUDIT_CONCURRENCY=5)` 并发审核所有小节。

#### 模式二：顺序审核图（`build_audit_graph`，向后兼容）

```
analyze_outline -> plan_strategy -> audit_section -> evaluate_result
                                     -> [reaudit | pass]
                                     -> update_context -> [next | done]
                                     -> cross_validate -> generate_report -> END
```

由 `PARALLEL_AUDIT_ENABLED=false` 启用，逐小节顺序审核，支持 `reaudit` 循环（上限 2 次）。

#### 模式三：对话审核图（`build_conversation_graph`）

```
analyze_outline -> plan_strategy -> checkpoint_strategy (interrupt)
    -> batched_audit -> cross_validate -> checkpoint_post_audit (interrupt)
    -> [re_audit_sections -> cross_validate (循环) | generate_report]
    -> checkpoint_post_completion (interrupt)
    -> [summarize_conversation -> chat_response (循环) | END]
```

启用 HITL 检查点 + re-audit 循环 + 自由对话环，是 `/api/agent/conversation/*` 端点的后端图。

### 4.2 核心节点详解

| 节点 | 函数 | 输入字段 | 输出字段 | 职责 |
|------|------|---------|---------|------|
| `analyze_outline` | `analyze_outline_node` | document_text, outline, sections | outline_summary | 文档结构分析，识别章节/小节层级，生成章节树；sections 为空时 LLM 兜底解析 |
| `plan_strategy` | `plan_strategy_node` | sections, outline_summary | audit_plan, knowledge_context | 为每小节分配审核深度 (quick/standard/deep) + 预检索知识库上下文 |
| `batch_audit` | `batch_audit_all_sections_node` | sections, audit_plan, knowledge_context | audit_results, global_context | 并行审核所有小节，每小节独立 RAG 检索 + LLM 审核 + 条款校验 |
| `audit_section` | `audit_section_node` | current_section_idx, sections, audit_plan | current_section_result_content | 顺序审核单个小节 |
| `evaluate_result` | `evaluate_result_node` | current_section_result_content | audit_results (追加) | 解析 JSON metadata + 条款校验结果 |
| `update_context` | `update_context_node` | audit_results | global_context (追加), current_section_idx | 更新跨章节上下文 |
| `cross_validate` | `cross_validate_node` | audit_results | contradictions | 跨章节矛盾检测 |
| `generate_report` | `generate_report_node` | audit_results, contradictions, outline_summary | final_report, finished | 生成最终审核报告 |

### 4.3 并行审核节点核心逻辑

`batch_audit_all_sections_node` 是并行模式的核心（agent_graph.py:571）：

```python
async def batch_audit_all_sections_node(state, llm, retriever):
    sections = state.get("sections", [])
    semaphore = asyncio.Semaphore(AUDIT_CONCURRENCY)  # 默认 5

    async def audit_one_section(idx):
        async with semaphore:
            section = sections[idx]
            depth = audit_plan.get(idx, {}).get("depth", "standard")
            # 1. 逐小节检索专用法规条款
            section_knowledge = _retrieve_section_knowledge(section, doc_type, retriever)
            # 2. 构建审核 System Prompt（注入领域专项 Prompt + RAG 上下文）
            system_prompt = _build_audit_system_prompt(...)
            # 3. LLM 审核
            response = await section_llm.ainvoke([SystemMessage(...), HumanMessage(...)])
            # 4. 法规条款引用校验（防编造）
            citation_validation = validate_citations(result_content, section_knowledge)
            if citation_validation["unverified"] > 0:
                result_content = annotate_unverified(result_content, citation_validation)
            return {section_idx, title, findings, confidence, result_content, citation_validation}

    all_results = await asyncio.gather(*[audit_one_section(i) for i in range(len(sections))])
    # Fallback: 并发失败则逐个重试
    ...
```

**设计要点**：
- **Semaphore 限流**：避免本地 Ollama 过载（122B 模型显存敏感）
- **独立 LLM 实例**：每个并发任务 `create_llm()` 新建实例，避免共享状态
- **逐小节检索**：`_retrieve_section_knowledge` 按小节内容精准检索，而非共享全局上下文
- **Fallback 降级**：`asyncio.gather` 异常时退化为逐个顺序重试，保证部分成功

### 4.4 路由函数

| 路由 | 函数 | 判断逻辑 |
|------|------|---------|
| `route_after_eval` | 顺序模式 evaluate_result 后 | confidence < 3 且 round_count < 2 → reaudit；否则 → pass |
| `route_next_section` | 顺序模式 update_context 后 | current_section_idx < len(sections) → next；否则 → done |
| `_route_after_post_audit` | 对话模式 post_audit 后 | re_audit_sections 非空且 cycle < 3 → re_audit；否则 → generate_report |
| `_route_after_completion` | 对话模式 post_completion 后 | feedback 含结束关键词 → end；否则 → chat |
| `_route_before_chat` | chat 前 | len(messages) >= 16 → summarize；否则 → chat |

---

## 5. 多 Agent 协作图（multi_agent/supervisor_graph.py）

多 Agent 图采用 **LangGraph Subagents + Send API** 模式，实现章节级并行审核。

### 5.1 图拓扑

#### 一次性审核拓扑（`conversation_mode=False`）

```
START -> analyze_structure -> [dispatch: Send(audit_chapter) ×N]
    -> reducer 汇集 chapter_results -> synthesize_report -> END
```

#### 对话循环拓扑（`conversation_mode=True`）

```
START -> analyze_structure -> checkpoint_structure (interrupt)
    -> [dispatch: Send(audit_chapter) ×N] -> dedupe_chapters
    -> checkpoint_post_audit (interrupt)
    -> [re_audit_clear -> dispatch (重审) | synthesize_report]
    -> checkpoint_post_completion (interrupt)
    -> [summarize_conversation -> chat_response (循环) | END]
```

### 5.2 Send API Fan-out 机制

核心在 `_dispatch_chapters` 条件边（supervisor_graph.py:101）：

```python
def _dispatch_chapters(state: MultiAgentState):
    chapter_structure = state.get("chapter_structure", [])
    sections = state.get("sections", [])
    document_type = state.get("document_type", "")

    sends = []
    for chap in chapter_structure:
        chapter_idx = chap["chapter_idx"]
        sub_indices = chap["subsection_indices"]
        # 截取该章节下属 subsection
        subsections = [sections[i] for i in sub_indices if 0 <= i < len(sections)]
        if not subsections:
            continue
        sends.append(Send("audit_chapter", {
            "chapter_idx": chapter_idx,
            "chapter_title": chap["chapter_title"],
            "subsections": subsections,
            "subsection_indices": sub_indices,
            "doc_type": document_type,
        }))
    return sends  # LangGraph 并行调度这些 Send packets
```

**关键设计**：
- 每个 `Send("audit_chapter", packet)` 携带该章节的完整输入（不是全量 MultiAgentState）
- `audit_chapter` 节点返回 `{"chapter_results": [single_result]}`，LangGraph 通过 `Annotated[List[dict], operator.add]` reducer 自动合并
- 无可审章节时返回 `Send("synthesize_report", {"_skip": True})` 跳过

### 5.3 三个子 Agent（multi_agent/agents.py）

#### 子 Agent 1：`analyze_structure_agent` — 结构分析

```python
def analyze_structure_agent(document_text, outline, sections, llm=None):
    # 复用 agent_graph.analyze_outline_node 逻辑
    delta = analyze_outline_node(pseudo_state, llm=llm)
    outline_summary = delta.get("outline_summary", {})
    # 转换为 chapter_structure
    chapter_structure = [{
        "chapter_idx": c_idx,
        "chapter_title": chap["title"],
        "subsection_indices": chap["subsection_indices"],
        "section_count": len(sub_indices),
    } for c_idx, chap in enumerate(outline_summary["chapters"])]
    return {"chapter_structure": ..., "outline_summary": ..., "total_chapters": ..., "total_sections": ...}
```

**特点**：复用单 Agent 的结构分析逻辑，保证两套图产出一致。

#### 子 Agent 2：`audit_chapter_agent` — 章节审核

```python
async def audit_chapter_agent(chapter_idx, chapter_title, subsections,
                               subsection_indices, doc_type, retriever, llm,
                               knowledge_context="", inner_concurrency=3):
    semaphore = asyncio.Semaphore(inner_concurrency)  # 小节级并发

    async def _bounded_audit(idx, section):
        async with semaphore:
            # 1. 小节级 RAG 检索
            section_knowledge = _retrieve_section_knowledge(section, doc_type, retriever)
            # 2. 复用单 Agent 的 _build_audit_system_prompt
            system_prompt = _build_audit_system_prompt(...)
            # 3. LLM 审核
            response = await llm.ainvoke([SystemMessage(...), HumanMessage(...)])
            # 4. 条款引用校验
            citation_validation = validate_citations(result_content, section_knowledge)
            return {title, breadcrumb, findings, confidence, result_content, citation_validation}

    results = await asyncio.gather(*[_bounded_audit(i, s) for i, s in enumerate(subsections)])
    # 章节级摘要
    chapter_summary = _build_chapter_summary(chapter_title, results)
    return {chapter_idx, chapter_title, subsection_results: results, chapter_summary, agent_steps}
```

**两级并发**：
- **章节级并行**：Supervisor Send API 同时调度多个 `audit_chapter` 节点
- **小节级并发**：每个 `audit_chapter` 内部 `Semaphore(INNER_CONCURRENCY=3)` 控制小节并发

#### 子 Agent 3：`synthesize_report_agent` — 综合报告

```python
def synthesize_report_agent(chapter_results, outline_summary, contradictions, document_type, llm):
    # 1. 展平为单 Agent 兼容的 audit_results 形式
    audit_results = [sub for ch in chapter_results for sub in ch["subsection_results"]]
    # 2. 复用 generate_report_node
    delta = generate_report_node(pseudo_state, llm=llm)
    final_report = delta["final_report"]
    # 3. 追加章节级摘要（多 Agent 独有）
    final_report += "\n## 6. 章节级审核摘要（多 Agent 协作）\n" + "\n".join(...)
    return {"final_report": ..., "subsection_results": audit_results}
```

**特点**：复用单 Agent 的报告生成逻辑，额外追加章节级摘要块。

### 5.4 去重节点（dedupe_chapters）

re-audit 场景下，新的 `chapter_results` 会通过 `operator.add` 追加到旧结果，`_dedupe_chapters_node` 按 `chapter_idx` 去重，保留最新：

```python
async def _dedupe_chapters_node(state):
    chapters = state.get("chapter_results", [])
    seen = {}
    for ch in chapters:
        idx = ch.get("chapter_idx")
        if idx is not None:
            seen[idx] = ch  # 后写入覆盖先写入
    return {"chapter_results": sorted(seen.values(), key=lambda c: c["chapter_idx"])}
```

### 5.5 环境变量配置

| 变量 | 默认值 | 作用 |
|------|--------|------|
| `MULTI_AGENT_INNER_CONCURRENCY` | 3 | 章节内小节级并发上限 |
| `MULTI_AGENT_CROSS_VALIDATION` | 1 | 是否启用章节间交叉验证 |
| `MAX_RE_AUDIT_CYCLES` | 3 | 重审循环上限 |
| `PARALLEL_AUDIT_ENABLED` | true | 单 Agent 图并行/顺序模式 |
| `AUDIT_CONCURRENCY` | 5 | 单 Agent 图并行并发数 |
| `AUDIT_BATCH_SIZE` | 5 | 对话模式批量审核批大小 |

---

## 6. HITL 人机交互机制

HITL（Human-in-the-Loop）是本系统对话审核的核心能力，通过 LangGraph `interrupt()` + `Command(resume=...)` 实现。

### 6.1 interrupt 机制

检查点节点调用 `interrupt(value)` 暂停图执行，`value` 作为中断信息推送给前端：

```python
# supervisor_graph.py:269
def _make_checkpoint_node(checkpoint_name, stage_name):
    async def checkpoint_node(state, *, config):
        # 构建中断信息
        summary = f"文档解析完成，supervisor 分章 {len(chapter_structure)} 章"
        structured = {"strategy": {"chapter_count": ..., "chapters": [...]}}

        _token = var_child_runnable_config.set(config)
        try:
            feedback = interrupt({
                "type": "checkpoint",
                "checkpoint": checkpoint_name,
                "stage": stage_name,
                "summary": summary,
                "structured": structured,
                "timestamp": _time.time(),
            })
        finally:
            var_child_runnable_config.reset(_token)

        return {
            "user_feedback": str(feedback) if feedback else "",
            "pending_checkpoint": checkpoint_name,
            "current_stage": stage_name,
        }
    return checkpoint_node
```

**关键点**：
- `var_child_runnable_config.set(config)` — 确保 interrupt 在正确的子配置上下文中执行
- `interrupt()` 返回值 = `Command(resume=...)` 传入的值 = 用户反馈
- 中断时 LangGraph 自动保存检查点到 SQLite，支持跨会话恢复

### 6.2 三个检查点

| 检查点 | 阶段 | 位置 | 用户可执行操作 |
|--------|------|------|---------------|
| `checkpoint_structure` | 分章确认 | analyze_structure 后 | 确认章节划分 / 修改 / 重审 |
| `checkpoint_post_audit` | 审核结果确认 | audit_chapter + dedupe 后 | 确认 / 重审指定章节 / 跳过 / 对话 |
| `checkpoint_post_completion` | 报告完成确认 | synthesize_report 后 | 确认完成 / 对话 / 重审 / 导出 |

### 6.3 恢复机制

用户反馈通过 API 传入，后端调用 `Command(resume=feedback)` 恢复图执行：

```python
# main.py conversation_message 端点
# 1. 分类用户意图
classification = await _classify_intent_async(message, intent_llm)
intent = classification["intent"]  # approve/adjust/supplement/skip/question/regenerate

# 2. 根据意图构造 resume payload
if intent == "adjust":
    state_update = {
        "re_audit_sections": classification["re_audit_sections"],
        "conversation_context": classification["supplement_text"],
    }
    # 3. 用 Command(resume=...) 恢复
    await graph.ainvoke(Command(resume=message, update=state_update), session.config)
elif intent == "approve":
    await graph.ainvoke(Command(resume=message), session.config)
```

### 6.4 意图分类（6 类）

`_classify_user_intent` 用 LLM 将用户反馈分类为 6 种意图：

| 意图 | 说明 | 处理方式 |
|------|------|---------|
| `approve` | 确认继续 | resume + 不更新状态 |
| `adjust` | 重审指定章节 | resume + update re_audit_sections |
| `supplement` | 补充上下文 | resume + update conversation_context |
| `skip` | 跳过章节 | resume + update skip_sections |
| `question` | 提问 | 路由到 chat_response |
| `regenerate` | 重新生成报告 | resume + update regenerate_instruction |

---

## 7. 对话循环与重审机制

### 7.1 Re-audit 循环

用户在 `checkpoint_post_audit` 或 `checkpoint_post_completion` 可请求重审指定章节：

```
checkpoint_post_audit -> [re_audit] -> re_audit_clear -> dispatch (重审)
    -> audit_chapter ×M -> dedupe_chapters -> checkpoint_post_audit (循环)
```

**控制逻辑**：

```python
# supervisor_graph.py:431
def _route_after_post_audit(state):
    feedback = state.get("user_feedback", "").strip().lower()
    re_audit_chapters = state.get("re_audit_chapters", [])
    re_audit_cycle_count = int(state.get("re_audit_cycle_count", 0))

    re_audit_keywords = ["重审", "重新审核", "re-audit", "reaudit", "再审", "重新审"]
    if re_audit_chapters and re_audit_cycle_count < MAX_RE_AUDIT_CYCLES:
        return "re_audit"
    if any(kw in feedback for kw in re_audit_keywords) and re_audit_cycle_count < MAX_RE_AUDIT_CYCLES:
        return "re_audit"
    return "synthesize"
```

**re_audit_clear 节点**：

```python
async def _re_audit_clear_node(state):
    return {
        "re_audit_chapters": [],                    # 清空重审列表
        "re_audit_cycle_count": state.get("re_audit_cycle_count", 0) + 1,  # 计数器+1
        "current_stage": "re_audit_dispatched",
    }
```

**重审后的去重**：`_dedupe_chapters_node` 按 `chapter_idx` 保留最新结果，旧结果被覆盖。

### 7.2 Skip 跳过

用户可跳过指定章节，`skip_chapters` / `skip_sections` 字段记录，后续审核跳过这些章节。

### 7.3 Chat 自由对话环

报告生成后进入"完成后自由对话"循环：

```
checkpoint_post_completion -> [chat | summarize -> chat | END]
    chat_response -> checkpoint_post_completion (循环)
```

**chat_response 节点**（supervisor_graph.py:471）：

```python
async def _node(state):
    question = state.get("user_feedback", "")
    final_report = state.get("final_report", "")
    history = state.get("messages", [])
    summary = state.get("summary", "")

    system_prompt = f"你是医疗器械文档审核专家。审核已完成...{final_report[:2000]}..."
    if summary:
        system_prompt += f"## 此前对话摘要\n{summary[:1500]}"

    response = await llm.ainvoke([
        HumanMessage(content=system_prompt),
        *history[-6:],              # 最近 6 条消息
        HumanMessage(content=question),
    ])
    return {"messages": [HumanMessage(question), AIMessage(answer)]}
```

**退出关键词**：`_END_KEYWORDS = ("结束", "退出", "完成", "exit", "quit", "done", "bye", "再见")`

---

## 8. 状态持久化与中断恢复

### 8.1 SQLite Checkpointer

```python
# agent_graph.py:1225
def get_sqlite_checkpointer(db_path="checkpoints/audit.db"):
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)
```

**持久化文件**：
- `checkpoints/conversation.db` (46MB) — 单 Agent 对话状态
- `checkpoints/multi_agent.db` (4.5MB) — 多 Agent 协作状态

### 8.2 thread_id 隔离

每个审核会话用唯一 `thread_id`（通常为 `session_id`）隔离状态：

```python
# main.py
session.config = {"configurable": {"thread_id": session_id}}
# 后续所有 graph.ainvoke / graph.astream 都使用该 config
```

LangGraph checkpointer 按 `thread_id` 分区存储，不同会话状态互不干扰。

### 8.3 中断恢复流程

```
1. 用户启动审核 -> graph.astream(initial_input, config)
2. 图执行到 checkpoint -> interrupt() -> 自动保存到 SQLite
3. SSE 推送 checkpoint 事件给前端
4. 用户离开 / 浏览器关闭
5. 用户重新连接 -> GET /conversation/stream/{session_id}
6. 后端 graph.aget_state(config) 读取 SQLite -> 恢复中断点
7. 用户发送反馈 -> POST /conversation/message
8. 后端 graph.ainvoke(Command(resume=feedback), config) -> 从中断点恢复执行
```

### 8.4 会话管理

```python
# main.py
_conversation_sessions: Dict[str, ConversationSession] = {}

class ConversationSession:
    def __init__(self, session_id, config):
        self.session_id = session_id
        self.config = config
        self.queue: asyncio.Queue = asyncio.Queue()  # SSE 事件队列
        self.last_active = time.time()

    def touch(self):
        self.last_active = time.time()
```

**心跳保活**：SSE 端点 60 秒无事件时推送 `heartbeat`，同时 `session.touch()` 防止后台 session-sweeper 误清理。

---

## 9. AuditState 与 MultiAgentState 设计

### 9.1 AuditState（单 Agent 图状态）

```python
class AuditState(TypedDict):
    # 文档信息
    document_text: str
    document_type: str
    outline: List[dict]
    sections: List[dict]

    # 结构概览
    outline_summary: dict  # {chapter_count, section_count, tree_text, chapters}

    # 审核策略
    audit_plan: dict       # {section_idx: {depth, focus_standards}}
    knowledge_context: str # 预检索法规原文

    # 审核进度
    current_section_idx: int
    round_count: int
    total_agent_steps: int

    # 当前小节中间结果
    confidence: int
    key_findings: List[str]
    current_section_result_content: str
    current_section_citation_validation: dict

    # 跨章节上下文 (reducer: operator.add 追加)
    global_context: Annotated[List[str], operator.add]

    # 审核结果
    audit_results: List[dict]

    # 消息历史 (reducer: add_messages)
    messages: Annotated[list, add_messages]

    # 长程记忆
    summary: str

    # 最终输出
    contradictions: Optional[List[dict]]
    final_report: Optional[str]
    finished: bool

    # 对话交互层
    current_stage: str           # intake/strategy/audit/cross_validate/report/revision
    user_feedback: str
    pending_checkpoint: str
    stage_history: List[dict]
    revision_requests: List[dict]
    re_audit_sections: List[int]
    conversation_context: str
    skip_sections: List[int]
    re_audit_cycle_count: int
    conversation_mode: bool
```

### 9.2 MultiAgentState（多 Agent 图状态）

```python
class MultiAgentState(TypedDict):
    # 输入
    document_text: str
    document_type: str
    outline: List[dict]
    sections: List[dict]

    # 结构分析产出
    outline_summary: dict
    chapter_structure: List[dict]

    # 章节审核并行写入 (reducer: operator.add)
    chapter_results: Annotated[List[dict], operator.add]

    # 综合产出
    subsection_results: List[dict]
    contradictions: Optional[List[dict]]
    final_report: Optional[str]
    finished: bool

    # 进度
    total_chapters: int
    total_sections: int
    total_agent_steps: int

    # 消息 (reducer: add_messages)
    messages: Annotated[list, add_messages]

    # 对话模式
    conversation_mode: bool
    current_stage: str
    user_feedback: str
    pending_checkpoint: str
    conversation_context: str

    # 对话循环扩展
    re_audit_chapters: List[int]
    revision_requests: List[dict]
    skip_chapters: List[int]
    re_audit_cycle_count: int
    summary: str
    awaiting_input: bool
```

### 9.3 Reducer 设计要点

| 字段 | Reducer | 行为 |
|------|---------|------|
| `global_context` | `operator.add` | 跨小节上下文追加，不覆盖 |
| `chapter_results` | `operator.add` | Send API 并行结果自动合并 |
| `messages` | `add_messages` | 消息历史追加，支持 RemoveMessage 修剪 |
| 其他字段 | 默认（覆盖） | 后写覆盖前写 |

**关键设计**：
- `chapter_results` 用 `operator.add` 让多个并行 `audit_chapter` 节点的返回值自动合并成一个列表
- `messages` 用 `add_messages` 让 chat 环的消息自动追加，同时支持 `RemoveMessage` 修剪（摘要后移除旧消息）
- `global_context` 用 `operator.add` 让顺序模式的 `update_context` 节点追加而非覆盖

---

## 10. 工具系统（agent_tools.py）

### 10.1 五个工具

| 工具 | 装饰器 | 参数 | 返回 | 用途 |
|------|--------|------|------|------|
| `parse_document` | `@tool` | text | JSON (outline + sections) | 解析文档结构，返回树状大纲和审核单元列表 |
| `rag_search` | `@tool` | query, top_k=5 | 检索片段文本 | 从法规知识库语义检索 |
| `check_regulation` | `@tool` | standard, clause | 检索片段文本 | 精确查询指定标准的具体条款原文 |
| `assess_completeness` | `@tool` | section_text, doc_type | JSON (score, gaps, assessment) | 快速评估章节完整度 1-5 分 |
| `audit_section` | `@tool` | section_text, context, depth, doc_type | 审核结果文本 | 专项审核（含 RAG + 领域 Prompt） |

### 10.2 依赖注入模式

工具通过模块级全局变量注入外部依赖（`create_audit_tools` 工厂函数）：

```python
# agent_tools.py
_retriever = None
_llm_client = None
_DOC_TYPE_LABELS: Dict[str, str] = {}

def create_audit_tools(retriever_instance, llm_client):
    global _retriever, _llm_client, _DOC_TYPE_LABELS
    _retriever = retriever_instance
    _llm_client = llm_client
    if hasattr(retriever_instance, "_DOC_TYPE_LABELS"):
        _DOC_TYPE_LABELS = retriever_instance._DOC_TYPE_LABELS
    return [parse_document, rag_search, check_regulation, assess_completeness, audit_section]
```

**设计理由**：`@tool` 装饰器生成静态工具函数，无法通过参数传递实例依赖；用全局变量在运行时注入 `RAGRetriever` 和 `ChatOpenAI` 实例。

### 10.3 工具与图的集成

工具主要供 **Agent 模式的工具循环** 使用（如 ReAct 模式），但本项目的审核图主要用 **直接节点调用** 而非工具循环，工具更多作为：
- **Phase 1 备用能力**：`PHASE1_TOOLS` 列表供 ReAct Agent 模式使用
- **辅助查询**：`rag_search` / `check_regulation` 在对话模式 chat_response 中可按需调用

---

## 11. RAG 检索架构

### 11.1 RAG 检索流水线

```
审核输入 (section_text + doc_type)
    │
    ▼
[1] Embedder (MiniMax embed-multilingual-v2)
    │
    ▼
[2] ChromaDB 向量检索 (top_k=5, doc_type 过滤)
    │
    ▼
[3] LLM Listwise Rerank (_llm_rerank_listwise_sync)
    │  - 候选数 < RERANK_LLM_MIN_CANDIDATES 时跳过
    │  - 温度 0.0，超时回退原始顺序
    │  - 输出 <order> [1] > [3] > [2] </order>
    ▼
[4] build_context (含对比模式 use_contrast_mode)
    │
    ▼
[5] 领域专项 Prompt (SECTION_PROMPTS[doc_type])
    │  - ISO 14971 风险管理检查清单
    │  - IEC 62304 软件生命周期检查清单
    │  - ISO 13485 体系审核检查清单
    │  - ...
    ▼
[6] 审核 System Prompt 构建 (_build_audit_system_prompt)
    │  - 注入 knowledge_context (通用)
    │  - 注入 section_knowledge (小节专用)
    │  - 注入 global_context (跨章节)
    │  - 注入 conversation_context (用户补充)
    ▼
[7] LLM 审核 (Ollama qwen3.5:122b)
    │
    ▼
[8] 法规条款引用校验 (validate_citations)
    │
    ▼
审核结果 (findings + score + citation_validation)
```

### 11.2 LLM Listwise Rerank

`_llm_rerank_listwise_sync` (rag_retriever.py:1556) 用 LLM 对候选片段做 listwise 重排：

```python
def _llm_rerank_listwise_sync(self, query, candidates):
    if len(candidates) < RERANK_LLM_MIN_CANDIDATES:
        return candidates  # 候选太少不重排

    parts = [f"[{i}] (来源: {source}) {text[:300]}" for i, doc in enumerate(candidates, 1)]
    user_content = f"QUERY: {query[:800]}\n候选片段:\n{parts}\n请按相关性排序: <order> [1] > [3] > ... </order>"

    payload = {
        "model": self.model,
        "messages": [
            {"role": "system", "content": self.RERANK_LISTWISE_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }
    try:
        resp = httpx.Client(timeout=RERANK_TIMEOUT).post(self.api_url, headers, json=payload)
        order = self._parse_ranking_response(answer, n)
        return [candidates[i - 1] for i in order]
    except Exception:
        return candidates  # 任何异常回退原始顺序
```

**设计要点**：
- **Listwise 而非 pairwise**：一次调用排序所有候选，减少 LLM 调用次数
- **温度 0.0**：确保排序稳定可复现
- **安全降级**：超时/解析失败/格式错误均回退原始顺序，不阻断主流程
- **候选数阈值**：`RERANK_LLM_MIN_CANDIDATES` 以下不重排，节省 LLM 调用

### 11.3 小节级检索

`_retrieve_section_knowledge` (agent_graph.py:423) 按小节内容精准检索：

```python
def _retrieve_section_knowledge(section, doc_type, retriever, top_k=5):
    title = section.get("title", "")
    content = section.get("content", "")[:2000]
    breadcrumb = section.get("breadcrumb", "")
    # 用标题 + 面包屑 + 内容前 2000 字作为检索 query
    query = f"{breadcrumb} {title}\n{content}"
    docs = retriever.search_sync_with_rerank(query, top_k=top_k)
    # 格式化为 chunk 文本
    return _format_knowledge_chunks(docs)
```

### 11.4 领域专项 Prompt

`RAGRetriever.SECTION_PROMPTS` 按文档类型加载专属审核检查清单：

| doc_type | 检查清单来源 |
|----------|-------------|
| `risk_management` | ISO 14971 风险管理检查清单 |
| `design_dev` | ISO 13485 设计开发检查清单 |
| `software_compliance` | IEC 62304 软件生命周期检查清单 |
| `registration` | 注册申报检查清单 |
| `production_quality` | 生产质量管理检查清单 |
| `system_construction` | 体系构建检查清单 |

---

## 12. 法规条款引用校验

### 12.1 问题背景

LLM 在审核中可能编造未在检索片段中出现的法规条款号（如把 "ISO 14971 §5.4.1" 编为 "ISO 14971 §5.4.12"），这会导致审核报告不可信。

### 12.2 校验流程

`clause_citation_validator.py` 实现 4 步校验：

```
LLM 审核输出文本
    │
    ▼
[1] 正则提取所有"标准号+条款号"组合
    _CITATION_RE = (ISO|IEC|GB/T|YY/T|NMPA GMP|MDR|FDA) + (§或空格) + (数字.数字...)
    │
    ▼
[2] 从 section_knowledge 提取合法条款号集合
    extract_kb_clauses() -> Set[normalized_key]
    normalized_key = "ISO14971|5.4.1" (去空格/年份/统一大小写)
    │
    ▼
[3] 跳过条件判断
    if len(kb_clauses) < 2: 跳过校验 (chunk 无明确条款号)
    │
    ▼
[4] 比对
    LLM 引用条款 ∈ 合法集合 -> 通过
    LLM 引用条款 ∉ 合法集合 -> 标注 "⚠ 引用待核实"
    │
    ▼
[5] 标注 (annotate_unverified)
    在 result_content 末尾追加"引用核实提示"段
    最多列出 5 条未核实引用
```

### 12.3 正则模式

```python
_STD_PREFIXES = (
    r"ISO\s*\d{3,5}(?::\d{4})?",       # ISO 14971, ISO 14971:2019
    r"IEC\s*\d{4,5}(?::\d{4})?",       # IEC 62304, IEC 62304:2015
    r"GB/T\s*\d{4,5}(?:-\d{4})?",      # GB/T 42062-2022
    r"YY/T\s*\d{3,5}(?:-\d{4})?",      # YY/T 0316, YY/T 0664
    r"NMPA\s*GMP",                     # NMPA GMP
    r"MDR\s*\d{4}/\d+",                # MDR 2017/745
    r"FDA\s*21\s*CFR\s*Part\s*\d+",    # FDA 21 CFR Part 820
)

_CITATION_RE = re.compile(
    r"(" + "|".join(_STD_PREFIXES) + r")"
    r"(?:\s*§\s*|\s+)"  # 必须有 § 或至少一个空格分隔
    r"(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
```

**设计要点**：
- 分隔符必须是 `§` 或至少一个空格，避免把 `iso14971.md` 误识别为条款引用
- 标准化函数 `_normalize_std` 去空格/年份/统一大小写，让 "ISO 14971:2019" 和 "iso 14971" 匹配同一条款

### 12.4 安全机制

- **不阻断主流程**：任何异常仅 `log warning`，返回原文本或空校验结果
- **跳过阈值**：知识库片段条款号 < 2 时跳过校验，避免对全部引用误标"未核实"
- **不破坏原内容**：`annotate_unverified` 在末尾追加提示段，不修改 LLM 原文

### 12.5 校验结果结构

```python
{
    "enabled": True,           # 是否实际执行了校验
    "total": 8,                # 提取的去重后引用数
    "verified": 6,             # 在知识库中找到的引用数
    "unverified": 2,           # 未在知识库中找到的引用数
    "unverified_list": [       # 未核实引用详情
        {"std": "ISO 14971:2019", "clause": "5.4.12", "raw": "ISO 14971:2019 §5.4.12"},
        ...
    ],
}
```

---

## 13. SSE 流式输出

### 13.1 双 stream_mode

```python
# main.py:1118
async for mode, chunk in graph.astream(
    state_to_run, session.config,
    stream_mode=["messages", "updates"],
):
    if mode == "messages":
        message_chunk, metadata = chunk
        # LLM token 级流式
        token_text = getattr(message_chunk, "content", "")
        if token_text:
            await session.queue.put({
                "event": "token",
                "content": token_text,
                "node": metadata.get("langgraph_node", ""),
            })
        # Tool 调用事件
        tool_calls = getattr(message_chunk, "tool_calls", None) or []
        for tc in tool_calls:
            await session.queue.put({"event": "tool_call", ...})
        # ToolMessage 结果
        if type(message_chunk).__name__ == "ToolMessage":
            await session.queue.put({"event": "tool_result", ...})

    elif mode == "updates":
        for node_name, node_output in chunk.items():
            await session.queue.put({
                "event": "node_complete",
                "node": node_name,
                "current_stage": node_output.get("current_stage", ""),
            })
```

### 13.2 事件类型

| 事件 | 触发时机 | 数据 |
|------|---------|------|
| `token` | LLM 生成 token | content, node |
| `tool_call` | Agent 触发工具调用 | tool_name, tool_args, tool_id, node |
| `tool_result` | 工具返回结果 | tool_name, tool_id, result_preview (截断 500 字) |
| `node_complete` | 节点执行完成 | node, current_stage |
| `checkpoint` | 图中断等待用户 | checkpoint, stage, summary, structured |
| `complete` | 审核完成 | report |
| `error` | 执行错误 | message |
| `heartbeat` | 60 秒无事件心跳 | (空) |

### 13.3 SSE 端点

```python
@app.get("/api/agent/conversation/stream/{session_id}")
async def conversation_stream(session_id):
    session = _conversation_sessions[session_id]

    async def event_stream():
        while True:
            event = await asyncio.wait_for(session.queue.get(), timeout=60.0)
            session.touch()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("event") in ("complete", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
    })
```

### 13.4 心跳保活

本地 Ollama 推理较慢时，SSE 可能长时间无事件。心跳机制：
- 60 秒无事件 -> 推送 `heartbeat`
- 同时 `session.touch()` 刷新 `last_active`
- 防止后台 session-sweeper 误判过期清理

---

## 14. 上下文管理与长程记忆

### 14.1 三层上下文注入

审核 System Prompt `_build_audit_system_prompt` 注入三层上下文：

```python
def _build_audit_system_prompt(section, depth, focus_standards, doc_type,
                                knowledge_context, global_context,
                                conversation_context, section_knowledge):
    # 1. 跨章节上下文 (最近 5 条)
    context_block = "## Global Context (findings from previous sections)\n"
    for ctx in global_context[-5:]:
        context_block += f"- {ctx}\n"

    # 2. 用户补充上下文 (重审时注入)
    extra_context_block = f"## Additional Context from User\n{conversation_context[:2000]}\n"

    # 3. 预检索知识 (通用，截断 4000 字)
    knowledge_block = knowledge_context[:4000]

    # 4. 小节专用知识 (截断 4000 字)
    section_knowledge_block = "## Section-Specific Regulatory References\n" + section_knowledge[:4000]

    # 5. 领域专项 Prompt (优先)
    domain_prompt = _get_domain_prompt(doc_type)
    if domain_prompt:
        return f"## 审核上下文\n...\n{knowledge_block}\n{section_knowledge_block}\n---\n{domain_prompt}"

    # 6. 回退通用英文 Prompt
    return f"You are a medical device documentation audit expert...\n{knowledge_block}..."
```

### 14.2 global_context 追加机制

`global_context` 用 `Annotated[List[str], operator.add]` reducer，跨小节自动追加：

```python
# batch_audit_all_sections_node 产出
global_context = []
for r in all_results:
    for finding in r.get("findings", [])[:2]:
        global_context.append(f"[{r['section_idx']}: {r['title']}] {finding}")
return {"global_context": global_context, ...}  # reducer 自动追加到现有列表
```

### 14.3 对话摘要压缩

当 `messages` 超过阈值时，`_summarize_conversation_node` 压缩早期消息：

```python
_SUMMARIZE_TRIGGER_LEN = 16  # 触发阈值
_SUMMARIZE_KEEP_RECENT = 6   # 保留最近条数

async def _summarize_conversation_node(state, llm):
    history = state.get("messages", [])
    if len(history) < _SUMMARIZE_TRIGGER_LEN:
        return {}

    to_summarize = history[:-_SUMMARIZE_KEEP_RECENT]  # 压缩除最近 6 条外的所有
    prev_summary = state.get("summary", "")

    # 转 plain text
    transcript = "\n".join(f"{role}: {content[:400]}" for m in to_summarize)

    # LLM 摘要（含此前摘要更新）
    response = await llm.ainvoke([
        SystemMessage("你是对话摘要助手...浓缩为不超过 400 字..."),
        HumanMessage(f"## 此前摘要\n{prev_summary}\n## 待压缩对话\n{transcript}"),
    ])
    new_summary = response.content

    # RemoveMessage 修剪 messages
    remove_ops = [RemoveMessage(id=m.id) for m in to_summarize if m.id]
    return {"summary": new_summary, "messages": remove_ops}
```

**设计要点**：
- **增量摘要**：新摘要包含此前摘要，避免信息丢失
- **RemoveMessage**：用 LangGraph 的 `RemoveMessage` 从 `messages` reducer 中移除旧消息
- **保留近期原文**：最近 6 条消息保留原文，保证近期上下文精度
- **chat_response 消费 summary**：`chat_response` 节点在 system prompt 中注入 `summary[:1500]`

### 14.4 摘要触发路由

```
checkpoint_post_completion -> _route_post_completion
    -> [end | summarize -> chat | chat]
```

```python
def _route_before_chat(state):
    history = state.get("messages", [])
    if len(history) >= _SUMMARIZE_TRIGGER_LEN:  # >= 16
        return "summarize"
    return "chat"
```

---

## 15. System Prompt 工程

### 15.1 领域专项 Prompt 优先

`_get_domain_prompt(doc_type)` 从 `RAGRetriever.SECTION_PROMPTS` 取对应领域的检查清单 prompt，剔除尾部的评分/评级段（Agent 模式不再输出评分），追加 JSON metadata 要求。

```python
_DOMAIN_SCORE_TAIL_RE = re.compile(r"###\s*严重度评级.*?\Z", re.DOTALL)
_DOMAIN_CHECKLIST_SECTION_RE = re.compile(r"###\s*逐条检查结果.*?(?=###\s)", re.DOTALL)

def _get_domain_prompt(doc_type):
    prompt = RAGRetriever.SECTION_PROMPTS.get(doc_type)
    if not prompt:
        return None
    # 剔除评分段
    prompt = _DOMAIN_SCORE_TAIL_RE.sub("", prompt)
    # 剔除逐条检查结果段（Agent 模式不输出）
    prompt = _DOMAIN_CHECKLIST_SECTION_RE.sub("", prompt)
    return prompt
```

### 15.2 Prompt 结构

审核 System Prompt 统一结构（支持顺序/并行/对话三种模式）：

```
## 审核上下文
- 文档类型: {doc_type}
- 当前小节: {title}（{breadcrumb}）
- 审核深度: {depth} - {depth_guidance}
- 关注标准: {focus_standards}
- Re-audit round: {round_count}

## Global Context (findings from previous sections)
- [section_idx: title] finding 1
- ...

## Additional Context from User
{conversation_context}

## 预检索法规知识（通用）
{knowledge_context[:4000]}

## Section-Specific Regulatory References
{section_knowledge[:4000]}

---

{domain_prompt}  (或回退通用英文 prompt)
```

### 15.3 深度引导

```python
depth_guidance = {
    "quick": "Quick audit: basic compliance check against key requirements.",
    "standard": "Standard audit: thorough review against relevant standards.",
    "deep": "Deep audit: exhaustive analysis with specific clause references required.",
}
```

### 15.4 JSON Metadata 提取

LLM 输出末尾需附加 JSON metadata 块，`_extract_json` 解析：

```python
def _extract_json(response_text, default):
    # 优先匹配 ```json ... ```
    match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # 回退匹配任意 {...}
    match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return default
```

提取的字段：`{"confidence": 1-5, "key_findings": ["...", ...]}`

---

## 16. 技术风险与缓解措施

| # | 风险 | 影响 | 缓解措施 |
|---|------|------|---------|
| 1 | **本地 LLM 推理慢** | 长文档审核耗时数十分钟 | asyncio 并发 + SSE token 流式 + 心跳保活 + 状态持久化（可中断恢复） |
| 2 | **LLM 编造法规条款号** | 审核报告不可信 | 法规条款引用校验器（正则提取 + 比对合法条款集 + 标注"引用待核实"） |
| 3 | **Send API re-audit 结果重复** | chapter_results 含旧+新结果 | `_dedupe_chapters_node` 按 chapter_idx 保留最新 |
| 4 | **并发 LLM 调用过载** | 本地 Ollama OOM 或超时 | Semaphore 限流（章节级 INNER_CONCURRENCY=3 / 小节级 AUDIT_CONCURRENCY=5）+ Fallback 降级 |
| 5 | **对话 token 膨胀** | 上下文超限 / 成本增加 | `_summarize_conversation_node` 压缩（触发阈值 16 条，保留近 6 条）+ RemoveMessage 修剪 |
| 6 | **SSE 长连接断开** | 用户丢失实时状态 | 心跳保活（60 秒）+ session.touch() + SQLite 检查点恢复 |
| 7 | **interrupt 上下文丢失** | 恢复后 interrupt 无法正确执行 | `var_child_runnable_config.set(config)` 确保子配置上下文 |
| 8 | **JSON 解析失败** | metadata 丢失 | `_extract_json` 两级 fallback（```json 块 -> 任意 {...} -> 默认值） |
| 9 | **re-audit 无限循环** | 用户反复重审卡死 | `MAX_RE_AUDIT_CYCLES=3` 上限 + `re_audit_cycle_count` 计数 |
| 10 | **知识库 chunk 无条款号** | 条款校验误报 | `min_kb_clauses=2` 阈值，知识库条款号 < 2 时跳过校验 |
| 11 | **文档结构解析失败** | sections 为空无法审核 | `analyze_outline_node` LLM 兜底解析（正则失败时） |
| 12 | **多 Agent 子任务失败** | 部分章节无结果 | `audit_chapter_agent` 内部 gather 失败 -> 退化为顺序重试 + 错误占位结果 |

---

## 17. 架构总结

### 17.1 核心架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 框架 | LangGraph StateGraph | 原生 interrupt + checkpointer + Send API 满足 HITL + 并行需求 |
| LLM | Ollama qwen3.5:122b | 本地化数据合规 + OpenAI 兼容 + 128K 上下文 |
| 图模式 | 单 Agent + 多 Agent 并存 | 覆盖一次性审核与对话审核全场景，代码复用 |
| 并行模式 | asyncio.gather + Send API | 两级并发（章节级 Send + 小节级 Semaphore） |
| HITL | interrupt + Command(resume) | LangGraph 原生支持 + SQLite 持久化恢复 |
| 反幻觉 | 条款引用校验器 | 正则提取 + 比对合法条款集 + 不阻断主流程 |
| 长程记忆 | summary + RemoveMessage | 增量摘要 + 修剪旧消息 + 保留近 6 条原文 |
| 流式输出 | SSE + 双 stream_mode | token 级实时渲染 + 节点级状态更新 |

### 17.2 数据流总结

```
用户上传文档
    │
    ▼
doc_processor 解析 (outline + sections)
    │
    ▼
初始化 AuditState / MultiAgentState
    │
    ▼
[单 Agent] analyze_outline -> plan_strategy (审核深度 + 预检索)
[多 Agent] analyze_structure (章节级结构)
    │
    ▼
[单 Agent] batch_audit_all_sections (asyncio.gather 并发)
[多 Agent] Send API fan-out -> audit_chapter ×N (章节级并行)
    │  每小节:
    │  1. _retrieve_section_knowledge (向量检索 + LLM Rerank)
    │  2. _build_audit_system_prompt (领域 Prompt + 多层上下文)
    │  3. LLM 审核 (Ollama qwen3.5:122b)
    │  4. validate_citations (条款引用校验)
    ▼
[单 Agent] audit_results
[多 Agent] chapter_results (reducer 汇集) -> dedupe_chapters
    │
    ▼
cross_validate (跨章节矛盾检测)
    │
    ▼
generate_report / synthesize_report (最终报告)
    │
    ▼
checkpoint_post_completion (用户确认 / 对话 / 导出)
    │
    ▼
[re-audit 循环] 或 [chat 对话环] 或 [END]
```

### 17.3 关键设计模式

1. **闭包注入**：`_make_*_node(llm, retriever)` 工厂函数闭包绑定 LLM/retriever 实例，避免污染 State
2. **reducer 自动合并**：`operator.add` / `add_messages` 让并行结果自动汇集
3. **复用优先**：多 Agent 子 Agent 复用单 Agent 的 `_build_audit_system_prompt` / `generate_report_node` 等核心逻辑
4. **安全降级**：所有外部调用（LLM/RAG/校验）均有 try/except + fallback，不阻断主流程
5. **两级并发**：Send API 章节级 + Semaphore 小节级，适配本地 LLM 显存限制
6. **增量摘要**：对话摘要包含此前摘要，避免信息丢失
7. **意图分类**：LLM 将用户反馈分类为 6 种意图，驱动对话循环路由

---

> **文档版本**：v1.0
> **生成日期**：2026-07-23
> **对应项目**：`documents_review_local_model/project_0428_beta`
> **源码版本**：v2.0 (Agent 模式)
