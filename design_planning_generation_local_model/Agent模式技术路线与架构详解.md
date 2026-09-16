# 设计策划文档生成系统 v2.0 — Agent 模式技术路线与架构详解

> 本文档详细阐述 Agent 模式下的技术选型、架构设计、核心机制与实现细节。
> 适用版本：v2.0.0 | 更新日期：2026-07-22

---

## 目录

1. [技术路线总览](#1-技术路线总览)
2. [核心技术选型与决策](#2-核心技术选型与决策)
3. [Agent 架构总览](#3-agent-架构总览)
4. [LangGraph 状态机详解](#4-langgraph-状态机详解)
5. [多代理协作机制](#5-多代理协作机制)
6. [工具体系设计（15 个工具）](#6-工具体系设计15-个工具)
7. [HITL 人机协同机制](#7-hitl-人机协同机制)
8. [状态持久化与恢复](#8-状态持久化与恢复)
9. [上下文管理策略](#9-上下文管理策略)
10. [System Prompt 工程](#10-system-prompt-工程)
11. [RAG 检索架构](#11-rag-检索架构)
12. [SSE 流式输出机制](#12-sse-流式输出机制)
13. [关键技术风险与对策](#13-关键技术风险与对策)
14. [架构总结](#14-架构总结)

---

## 1. 技术路线总览

### 1.1 设计目标

Agent 模式旨在将传统的"表单提交 -> 等待 -> 下载"文档生成模式，升级为**对话式、可控、可恢复的智能协作模式**，实现：

| 目标 | 传统表单模式 | Agent 模式 |
|------|-------------|-----------|
| 交互方式 | 一次性表单提交 | 多轮自然语言对话 |
| 生成控制 | 黑盒，无法干预 | HITL 逐章节确认/修改/拒绝 |
| 上下文感知 | 无状态，每次独立 | 状态持久化，支持中断恢复 |
| 文档框架 | 预定义固定结构 | LLM 自主设计 + 用户确认 |
| 章节质量 | 单次生成 | 子代理逐小节精写 |
| 长文档处理 | token 超限风险 | 上下文压缩 + 摘要 |
| 知识检索 | 固定查询 | LLM 自主决策检索策略 |

### 1.2 技术路线图

```
对话式交互 ──────────────────────────────────────────────────────
    │
    ├─ LangGraph StateGraph ──── ReAct Agent 循环（LLM 自主决策）
    │      │
    │      ├─ HITL interrupt() ──── 人机协同（章节确认/修改/拒绝）
    │      │
    │      ├─ SqliteSaver ──────── 状态持久化（中断恢复）
    │      │
    │      └─ astream_events ──── SSE 流式输出
    │
    ├─ Multi-Agent 协作 ──────── 专业化分工
    │      ├─ Main Agent ─────── 对话编排 + 工具调度
    │      ├─ outline_agent ──── 框架设计（子代理A）
    │      ├─ chapter_agent ──── 章节编写（子代理B）
    │      └─ summary_agent ──── 摘要压缩（子代理C）
    │
    ├─ 本地化 LLM ──────────── Ollama qwen3.5:122b
    │      └─ OpenAI 兼容接口 ── ChatOpenAI 适配层
    │
    ├─ RAG 增强 ─────────────── 混合检索 + 重排序
    │      ├─ 向量检索 ──────── ChromaDB (doubao-embedding 1024维)
    │      ├─ BM25 检索 ─────── rank_bm25 + jieba 医疗词典
    │      └─ Reranker ──────── 语义重排序
    │
    └─ 上下文管理 ──────────── 滑动窗口 + 摘要压缩
           └─ 85% 阈值触发 ─── 保留最近 15 轮完整对话
```

---

## 2. 核心技术选型与决策

### 2.1 LangGraph（Agent 编排框架）

| 维度 | LangGraph | LangChain Agent | AutoGen | CrewAI |
|------|-----------|-----------------|---------|--------|
| 状态管理 | TypedDict + 持久化 | 无状态 | 对象级 | 任务级 |
| HITL 支持 | interrupt() 原生 | 需自定义 | 不支持 | 不支持 |
| 流式输出 | astream_events | 基础流式 | 不支持 | 不支持 |
| 检查点恢复 | SqliteSaver 原生 | 不支持 | 不支持 | 不支持 |
| 图结构 | StateGraph 显式 | 隐式 | 隐式 | 隐式 |
| 工具集成 | ToolNode + tools_condition | bind_tools | 自定义 | 自定义 |

**决策**：选用 **LangGraph**，核心原因：
1. **HITL 原生支持**：`interrupt()` + `Command(resume=...)` 是唯一原生支持人机协同暂停/恢复的框架
2. **状态持久化**：`AsyncSqliteSaver` 自动检查点，进程重启后可恢复完整对话
3. **显式图结构**：`StateGraph` 让 Agent 流转逻辑清晰可维护
4. **SSE 流式**：`astream_events(version="v2")` 支持 token 级流式 + 工具事件 + 中断事件

### 2.2 Ollama（本地 LLM 部署）

| 维度 | Ollama 本地 | OpenAI API | Anthropic API | vLLM |
|------|------------|-----------|---------------|------|
| 数据隐私 | 数据不出企业 | 数据上云 | 数据上云 | 数据不出企业 |
| 部署成本 | 单机部署 | 零部署 | 零部署 | 需 GPU 服务器 |
| 接口兼容 | OpenAI 兼容 | 原生 | 原生 | OpenAI 兼容 |
| 模型选择 | 任意开源模型 | 仅 GPT 系列 | 仅 Claude | 任意开源模型 |
| 成本 | 一次性硬件 | 按 token 计费 | 按 token 计费 | 一次性硬件 |

**决策**：选用 **Ollama + qwen3.5:122b**，核心原因：
1. **数据隐私**：医疗器械文档涉及企业核心 IP，本地化部署确保数据不出企业
2. **OpenAI 兼容**：通过 `ChatOpenAI(base_url=ollama:11435/v1)` 无缝接入 LangChain 生态
3. **128K 上下文**：qwen3.5:122b 支持长上下文，适合长文档生成场景
4. **零 API 成本**：避免大量章节生成的高昂 API 费用

### 2.3 ChromaDB（向量数据库）

**决策**：沿用 **ChromaDB 0.4.22**，核心原因：
1. **嵌入式部署**：无需独立数据库服务，Python 进程内直接使用
2. **持久化**：`chroma_db_insulin_pump/` 目录持久化，重启不丢数据
3. **多 Collection**：`medical_device_kb_v2` + `uploads` 分离系统知识库与用户附件
4. **与 LangChain 集成**：原生支持，开发成本低

### 2.4 MinerU（文档视觉解析）

**决策**：opt-in 集成 **MinerU2.5-Pro-2605-1.2B**，核心原因：
1. **视觉模型优势**：PDF/Office/图片统一用视觉模型解析，处理扫描件、复杂表格优于传统 OCR
2. **子进程隔离**：`mineru_runner.py` 在独立子进程中执行，避免 torch/transformers 与主服务冲突
3. **opt-in 设计**：默认关闭（`USE_MINERU=false`），未启用时自动回退到 python-docx/pdfplumber
4. **本地部署**：无 API 配额限制，适合批量文档摄入

---

## 3. Agent 架构总览

### 3.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                     前端层 (agent.html)                       │
│   聊天界面 | SSE 接收 | HITL 弹窗 | 附件管理 | 章节进度       │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST /api/agent/projects/:id/messages
                           │ POST /api/agent/projects/:id/resume
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    API 层 (routes.py)                         │
│   agent_send_message | agent_resume | agent_auto_generate   │
│   agent_batch_generate | agent_summarize | agent_get_state  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                Agent 引擎层 (agent_engine.py)                 │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │           LangGraph StateGraph (ReAct)               │  │
│   │                                                      │  │
│   │   agent ──> tools_condition ──> pre_tools ──> tools  │  │
│   │      ↑                              │            │   │  │
│   │      └──── after_tools ←────────────┘            │   │  │
│   │                                                   │   │  │
│   │   HITL: interrupt() in pre_tools                  │   │  │
│   │   State: AgentState (TypedDict)                   │   │  │
│   │   Persist: AsyncSqliteSaver                        │   │  │
│   │   Stream: astream_events v2                        │   │  │
│   └──────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  子代理层     │ │  工具层       │ │  LLM 层      │
│ (subagents)  │ │(agent_tools) │ │  (Ollama)    │
│              │ │              │ │              │
│ outline_A    │ │ 15 个工具    │ │ qwen3.5:122b │
│ chapter_B    │ │ search/generate/build... │ ChatOpenAI   │
│ summary_C    │ │              │ │ 兼容接口     │
└──────────────┘ └──────┬───────┘ └──────────────┘
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  RAG 层      │ │ 外部搜索     │ │ 文档解析     │
│ ChromaDB     │ │ Playwright   │ │ MinerU       │
│ BM25         │ │ Bing/DDG     │ │ python-docx  │
│ Reranker     │ │              │ │ pdfplumber   │
└──────────────┘ └──────────────┘ └──────────────┘
```

### 3.2 核心文件职责

| 文件 | 大小 | 职责 |
|------|------|------|
| `agent_engine.py` | 27KB | LangGraph 图构建、节点定义、HITL 中断、SSE 流式、resume 恢复 |
| `agent_prompt.py` | 66KB | System Prompt 构建（5 个 Section：角色/领域知识/SOP/工具规则/回复风格） |
| `agent_state.py` | 7KB | AgentState TypedDict 定义、状态快照构建、SqliteSaver 管理 |
| `agent_tools.py` | 103KB | 15 个工具实现（检索/生成/构建/摘要/搜索/解析/入库） |
| `subagents.py` | 11.5KB | 3 个子代理定义（outline/chapter/summary） |
| `context_manager.py` | 5KB | 滑动窗口上下文压缩（85% 阈值 + 摘要） |
| `routes.py` | 48KB | Agent API 端点（13+ 接口） |

---

## 4. LangGraph 状态机详解

### 4.1 图结构

```python
# agent_engine.py - _build_graph()

workflow = StateGraph(AgentState)

# 4 个节点
workflow.add_node("agent",       _agent_node)        # LLM 决策
workflow.add_node("pre_tools",   _pre_tool_node)     # HITL 检查
workflow.add_node("tools",       ToolNode(PHASE1_TOOLS))  # 工具执行
workflow.add_node("after_tools", _after_tools_node)  # 结果写回 state

# 边
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition, {
    "tools": "pre_tools",
    END: END,
})
workflow.add_edge("pre_tools", "tools")
workflow.add_edge("tools", "after_tools")
workflow.add_edge("after_tools", "agent")  # 循环回到 agent

# 编译（含检查点）
_agent_graph = workflow.compile(checkpointer=checkpointer)
```

### 4.2 节点职责详解

#### 节点 1：`agent`（`_agent_node`）

**核心职责**：LLM ReAct 决策 —— 决定回复还是调用工具

```
执行流程:
1. 获取当前 messages
2. maybe_compress_messages()  ← 上下文压缩检查
3. _sync_doc_context(state)    ← 同步文档上下文到工具层
4. _sync_attachment_context()  ← 同步附件上下文
5. build_system_prompt(state)  ← 构建动态 System Prompt
6. model.ainvoke(system + messages)  ← 调用 Ollama LLM
7. 返回 {messages: [response]}
```

**关键设计**：
- System Prompt 每轮动态构建，注入当前状态快照
- 上下文压缩在调用 LLM 前执行，确保不超 token 限制
- 文档/附件上下文通过模块级全局变量同步到工具层（避免 LLM 传递大段文本）

#### 节点 2：`pre_tools`（`_pre_tool_node`）

**核心职责**：HITL 暂停检查

```
执行流程:
1. 获取最后一条 message 的 tool_calls
2. 如果 auto_mode = True → 跳过 HITL
3. 检查是否含 generate_section 调用
4. 如果含 → interrupt() 暂停，等待用户确认
5. 返回 {} (未暂停时放行到 tools)
```

**HITL 触发条件**：
- `tool_calls` 中包含 `generate_section`
- `auto_mode != True`
- 非异常情况（Python 3.10 contextvar 跨 async 传播问题时静默放行）

#### 节点 3：`tools`（`ToolNode`）

**核心职责**：执行 LLM 决定的工具调用

- LangGraph 内置 `ToolNode`，自动解析 `tool_calls` 并并行执行
- 工具结果以 `ToolMessage` 形式追加到 messages
- 支持单次多工具并行调用（如同时调用多个 `write_chapter`）

#### 节点 4：`after_tools`（`_after_tools_node`）

**核心职责**：将工具结果写回 AgentState

```
执行流程:
1. 从 messages 末尾收集所有新增 ToolMessage
2. 构建 tool_call_id → (tool_name, tool_args) 映射
3. 遍历 ToolMessage:
   - generate_section/revise_section → 写入 generated_sections
   - build_docx → 更新 document_status = "completed"
   - design_outline/outline_from_attachment → 写入 outline + outline_status
   - write_chapter → 从旁路 dict 读取完整内容写入 generated_sections
4. 返回更新后的 state diff
```

**关键设计 —— 旁路 dict**：
`write_chapter` 子代理生成的章节内容可能很长，直接放入 `ToolMessage` 会污染 LLM 对话历史。因此通过模块级 `set_current_doc_context()` 旁路传递，`_after_tools_node` 从旁路 dict 读取完整内容写入 state，避免大段内容进入对话。

### 4.3 条件路由（`tools_condition`）

LangGraph 内置的 `tools_condition` 函数：
- 检查最后一条 AIMessage 是否含 `tool_calls`
- 有 → 路由到 `"tools"`（即 `pre_tools` 节点）
- 无 → 路由到 `END`（LLM 直接回复，对话轮次结束）

### 4.4 递归限制

```python
config = {
    "configurable": {"thread_id": thread_id},
    "recursion_limit": 100,  # 防止无限循环
}
```

单次对话最多 100 次 agent↔tools 循环，防止 Agent 陷入工具调用死循环。

---

## 5. 多代理协作机制

### 5.1 代理架构

```
                    ┌─────────────────┐
                    │   Main Agent    │
                    │  (ReAct 循环)   │
                    │  对话编排+调度  │
                    └───────┬─────────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ outline_agent│ │chapter_agent │ │summary_agent │
    │  (子代理A)   │ │  (子代理B)   │ │  (子代理C)   │
    │              │ │              │ │              │
    │ 框架设计师   │ │ 章节编写师   │ │ 摘要师       │
    │ 输出JSON框架 │ │ 输出章节MD   │ │ 输出压缩摘要 │
    └──────────────┘ └──────────────┘ └──────────────┘
            │               │               │
            └───────────────┼───────────────┘
                            │
                    ┌───────▼─────────┐
                    │  共享 AgentState │
                    │  (TypedDict)    │
                    │                 │
                    │ outline         │
                    │ generated_sections│
                    │ chapter_write_queue│
                    └─────────────────┘
```

### 5.2 子代理定义（subagents.py）

每个子代理拥有**独立 LLM 实例**（避免上下文污染），通过 `create_agent()` 创建，主 Agent 通过工具包装调用。

#### 子代理 A：outline_agent（框架设计师）

**职责**：根据文档类型设计完整的多层级章节框架

**输入**：`doc_type` + `product_name` + `special_requirements`

**输出**：严格 JSON 格式框架
```json
{
  "doc_title": "贴敷式胰岛素泵-{文档类型名称}",
  "chapters": [
    {
      "id": 1,
      "title": "第X章 章节标题",
      "description": "本章覆盖范围（≤30字）",
      "key_standards": ["GB XXXX-XXXX", "ISO XXXX:XXXX"],
      "sections": [
        {
          "title": "X.1 节标题",
          "subsections": [
            {
              "title": "X.1.1 小节标题",
              "content_points": ["要点1", "要点2"],
              "sub_subsections": [
                {"title": "X.1.1.1 子小节", "content_points": ["..."]}
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

**内置领域知识**：
- 贴敷式胰岛素泵：III类器械，C级软件，关键参数（45×35×12mm，200-300U，0.05U/h，BLE 5.0，IPX8）
- 适用标准：ISO 13485 §7.3.2、ISO 14971 §4.4、IEC 62304 §5.1、IEC 62366-1 §5、GB 9706.224、YY 9706.102、ISO 10993-1

**工作流程**：
1. 收到 doc_type 后，先调用 `search_kb` 检索该文档类型的标准要求
2. 基于标准要求设计多层级章节结构
3. 输出严格 JSON

#### 子代理 B：chapter_agent（章节编写师）

**职责**：基于框架和检索结果编写单章节内容

**输入**：`chapter_name` + `outline_json` + `doc_type` + 检索结果

**输出**：单章节 Markdown 内容

**关键特性**：
- 从 outline JSON 中提取目标章节的子小节结构
- 逐小节生成，质量优于单次整章生成
- 内部自动调用 `generate_search_query` + `search_kb` 检索参考资料
- 支持**并行调用**：主 Agent 可在一次回复中同时调用多个 `write_chapter`，系统自动并行执行

#### 子代理 C：summary_agent（摘要师）

**职责**：将长章节内容压缩为摘要

**输入**：长章节内容 + 摘要目标字数

**输出**：压缩摘要

**工作流程**：
1. `_split_chapter_into_subsections()` 将章节按标题拆分为子小节
2. `_count_chinese_chars()` 统计中文字符数
3. `_summarize_one_subsection()` 逐子小节摘要
4. 合并为完整摘要

### 5.3 主 Agent 与子代理的通信

```
Main Agent (LLM 决策)
    │
    ├─ "需要设计框架" → 调用 design_outline 工具
    │       │
    │       └─ design_outline() 内部:
    │           1. _get_outline_agent() 获取子代理A实例
    │           2. 子代理A.ainvoke(doc_type + product_name)
    │           3. _extract_json() 提取JSON框架
    │           4. 返回 JSON 给主Agent
    │
    ├─ "需要编写章节" → 调用 write_chapter 工具
    │       │
    │       └─ write_chapter() 内部:
    │           1. _get_chapter_agent() 获取子代理B实例
    │           2. _find_chapter_subsections() 从outline提取子小节
    │           3. 子代理B.ainvoke(章节信息 + 检索结果)
    │           4. 返回章节Markdown
    │
    └─ "需要摘要" → 调用 summarize_section 工具
            │
            └─ summarize_section() 内部:
                1. _get_summary_agent() 获取子代理C实例
                2. 拆分子小节 + 逐节摘要
                3. 返回压缩摘要
```

**通信机制**：
- 子代理通过工具包装调用（主 Agent 视为普通工具）
- 子代理有独立 LLM 实例和上下文，与主 Agent 对话历史隔离
- 共享数据通过 `AgentState` 传递（outline、generated_sections 等）
- 大段内容通过旁路 dict 传递（避免污染主 Agent 对话历史）

---

## 6. 工具体系设计（15 个工具）

### 6.1 工具分类总览

| 类别 | 工具 | 功能 | HITL |
|------|------|------|------|
| **知识检索** | `search_kb` | 知识库混合检索（向量+BM25+Reranker） | 否 |
| | `search_attachment` | 用户附件语义检索 | 否 |
| | `generate_search_query` | LLM 生成优化检索查询 | 否 |
| **文档分析** | `analyze_document_structure` | 分析附件章节结构（LLM 识别） | 否 |
| | `outline_from_attachment` | 基于附件结构生成框架 | 否 |
| | `ingest_attachment_to_kb` | 附件摄入主知识库 | 否 |
| **框架设计** | `design_outline` | 子代理A 设计完整章节框架 | 否 |
| | `update_outline` | 子代理A 修改框架 | 否 |
| **章节生成** | `generate_section` | 直接生成章节（降级路径） | **是** |
| | `write_chapter` | 子代理B 按框架逐小节编写 | 否 |
| | `revise_section` | 根据指令修订章节 | 否 |
| **摘要压缩** | `summarize_section` | 子代理C 章节摘要 | 否 |
| | `summarize_document` | 全文档摘要 | 否 |
| **文档构建** | `build_docx` | Markdown → Word 文档 | 否 |
| **外部搜索** | `web_search` | Playwright 网页搜索 | 否 |

### 6.2 PHASE1_TOOLS 定义

```python
# agent_tools.py

PHASE1_TOOLS = [
    # 知识检索
    search_kb,
    search_attachment,
    web_search,
    analyze_document_structure,
    ingest_attachment_to_kb,
    generate_search_query,
    # 章节生成
    generate_section,      # ← HITL 暂停点
    revise_section,
    build_docx,
    # 子代理工具
    design_outline,        # 子代理A
    outline_from_attachment,
    write_chapter,         # 子代理B
    update_outline,
    summarize_section,     # 子代理C
    summarize_document,
]
```

### 6.3 工具使用规则（System Prompt Section 3）

每个工具在 System Prompt 中都有明确的使用时机和规则：

```
## 知识检索
1. search_kb - 检索贴敷式胰岛素泵知识库
   何时用: 涉及具体标准条款、限值、测试方法时必须先调用
   规则: 不要在未检索的情况下编造标准条款号和具体限值

2. search_attachment - 搜索用户上传的附件内容
   何时用: 用户上传了参考文档，需要从附件中查找信息时
   规则: 用户提到附件中有相关内容时，优先调用

## 子代理工具 (多代理协作核心)
5. design_outline - [子代理A] 调用框架设计专家
   何时用: 开始生成新文档时
   规则: 子代理返回JSON框架，需展示给用户确认后再进入章节编写

6. write_chapter - [子代理B] 调用章节编写专家
   何时用: 框架已确认，需要生成某章节内容时
   重要: 可以在一次回复中同时调用多个 write_chapter，系统自动并行执行

8. generate_section - 直接生成指定章节（降级路径）
   与 write_chapter 的区别: generate_section 无需框架可直接生成整章
   规则: 有框架时优先用 write_chapter，无框架时用 generate_section
```

### 6.4 关键工具设计

#### search_kb（知识库检索）

```python
@tool
async def search_kb(query: str, top_k: int = 5, use_rerank: bool = True) -> str:
    """检索知识库，返回 JSON:
    {"status": "ok", "query": "...", "count": N, "results": [...]}
    """
    # 1. 向量检索 (doubao-embedding 1024维)
    # 2. BM25 检索 (jieba 分词)
    # 3. 加权融合 (向量 0.6-0.7, BM25 0.3-0.4)
    # 4. Reranker 重排序 (可选)
    # 5. 跨 Collection 检索 (uploads)
```

#### generate_section（HITL 暂停点）

```python
@tool
async def generate_section(section_name: str, doc_type: str = "...") -> str:
    """生成指定章节 — HITL 暂停点

    执行流程:
    1. pre_tools 节点检测到 generate_section 调用
    2. interrupt() 暂停，SSE 推送 waiting_approval
    3. 前端弹出确认框 [确认] [修改] [拒绝]
    4. 用户 resume:
       - approve → 正常生成
       - edit → 带修改指令生成
       - reject → 跳过
    5. 生成完成后返回章节内容
    """
```

#### build_docx（Word 构建）

```python
@tool
async def build_docx(doc_type: str = "", product_name: str = "", markdown: str = "") -> str:
    """将 Markdown 转换为 Word 文档

    返回 JSON:
    {"status": "ok", "download_id": "...", "filename": "...", "size_bytes": N}

    关键设计:
    - markdown 参数可选，为空时从 _current_doc_context 旁路读取
    - 生成的 docx 存储在内存 dict 中，通过 download_id 下载
    - SSE 推送 file_ready 事件，前端弹出下载按钮
    """
```

---

## 7. HITL 人机协同机制

### 7.1 HITL 核心设计

HITL（Human-in-the-Loop）是 Agent 模式的核心差异化能力，允许用户在关键节点介入决策。

**HITL 触发点**：`generate_section` 工具调用时

**实现机制**：LangGraph `interrupt()` + `Command(resume=...)`

### 7.2 HITL 完整流程

```
                          ┌─────────────────────┐
                          │ Main Agent 决策      │
                          │ 调用 generate_section│
                          └──────────┬──────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │ pre_tools 节点       │
                          │ 检测到 generate_section│
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │ auto_mode = True?   │
                          └────┬──────────┬─────┘
                           是  │          │ 否
                              ▼          ▼
                    ┌────────────┐ ┌─────────────────┐
                    │ 跳过 HITL  │ │ interrupt() 暂停│
                    │ 直接执行   │ │ 保存检查点      │
                    └────────────┘ └────────┬────────┘
                                            │
                               ┌────────────▼────────────┐
                               │ SSE: on_interrupt        │
                               │ {type: "waiting_approval"│
                               │  interrupt_data: {...}}  │
                               └────────────┬────────────┘
                                            │
                               ┌────────────▼────────────┐
                               │ 前端弹出确认对话框       │
                               │ [确认] [修改] [拒绝]    │
                               └────────────┬────────────┘
                                            │
                          ┌─────────────────┼─────────────────┐
                          │                 │                 │
                     ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
                     │ approve │      │  edit   │      │ reject  │
                     └────┬────┘      └────┬────┘      └────┬────┘
                          │                │                 │
                          ▼                ▼                 ▼
                 ┌─────────────────────────────────────────────┐
                 │ POST /api/agent/projects/:id/resume         │
                 │ {action: "approve" | "edit:xxx" | "reject"} │
                 └────────────────────┬────────────────────────┘
                                      │
                          ┌───────────▼───────────┐
                          │ resume_agent()        │
                          │ Command(resume=...)   │
                          └───────────┬───────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
               ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
               │ 正常生成 │      │ 带修改  │      │ 跳过    │
               │ 章节内容 │      │ 指令生成│      │ 该章节  │
               └─────────┘      └─────────┘      └─────────┘
```

### 7.3 resume 实现

```python
# agent_engine.py - resume_agent()

async def resume_agent(thread_id: str, decision: str):
    """HITL 恢复

    Args:
        decision: "approve" | "reject" | "edit:修改内容"
    """
    if decision.startswith("edit:"):
        edited_content = decision[len("edit:"):]
        resume_value = Command(resume={"action": "edit", "content": edited_content})
    elif decision == "reject":
        resume_value = Command(resume={"action": "reject"})
    else:  # approve
        resume_value = Command(resume={"action": "approve"})

    # 恢复执行，继续 SSE 流式输出
    async for event in agent.astream_events(
        None, config=config, version="v2"
    ):
        # ... 同 stream_agent_events 的事件处理
```

### 7.4 auto_mode（自动模式）

当 `auto_mode = True` 时，跳过所有 HITL 确认，一键生成全文档：

- `pre_tools` 节点检测到 `auto_mode` 后直接放行
- 所有 `generate_section` 调用自动 approve
- 适用于用户信任 Agent 生成质量、希望快速产出的场景
- 通过 `/api/agent/projects/:id/auto-generate` 端点触发

---

## 8. 状态持久化与恢复

### 8.1 持久化架构

```
┌─────────────────────────────────────────────────────┐
│                  Agent 运行时                        │
│                                                     │
│   每轮对话后                                        │
│       │                                             │
│       ▼                                             │
│   AsyncSqliteSaver.aput_checkpoint()                │
│       │                                             │
│       ▼                                             │
│   ┌─────────────────────────────────────────────┐  │
│   │ project_store/agent_checkpoints.db          │  │
│   │                                             │  │
│   │ 表结构:                                     │  │
│   │ - checkpoints (thread_id, checkpoint_id,    │  │
│   │                parent_id, checkpoint,        │  │
│   │                metadata)                     │  │
│   │ - writes (thread_id, checkpoint_ns,         │  │
│   │           task_id, task_path, type,          │  │
│   │           value)                             │  │
│   │                                             │  │
│   │ 特性:                                       │  │
│   │ - 按 thread_id (项目ID) 隔离                │  │
│   │ - 增量保存（只存 diff）                     │  │
│   │ - 支持中断状态恢复                          │  │
│   │ - WAL 模式并发读写                          │  │
│   └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 8.2 检查点恢复流程

```python
# 应用启动时
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化 Agent（含 SqliteSaver）
    from app.services.agent_engine import init_agent
    await init_agent()
    yield
    # 关闭时清理
    from app.services.agent_state import close_checkpointer
    await close_checkpointer()

# 用户发消息时
async def stream_agent_events(user_message, thread_id, initial_state):
    config = {
        "configurable": {"thread_id": thread_id},  # 按项目隔离
        "recursion_limit": 100,
    }
    # LangGraph 自动从 SqliteSaver 加载该 thread_id 的历史状态
    # 如果是中断恢复，从中断点继续执行
    async for event in agent.astream_events(state, config=config):
        ...
```

### 8.3 thread_id 隔离

- 每个 `project_id` 对应一个 `thread_id`
- 不同项目的对话历史和状态完全隔离
- 同一项目可跨会话恢复（关闭浏览器后重新打开继续）

### 8.4 状态快照（build_state_snapshot）

`agent_state.py` 中的 `build_state_snapshot()` 函数将 AgentState 序列化为 JSON 快照，供前端展示进度：

```python
def build_state_snapshot(state: AgentState) -> dict:
    """构建状态快照，供前端展示"""
    return {
        "step": current_step,                    # 当前步骤 (1-6)
        "product": {
            "name": state.get("product_name"),
            "classification": state.get("product_classification"),
            "intended_use": state.get("product_intended_use"),
            "status": state.get("product_status"),
        },
        "standards": {
            "confirmed": state.get("confirmed_standards", []),
            "candidate": state.get("candidate_standards", []),
            "status": state.get("standards_status"),
        },
        "outline": state.get("outline"),
        "outline_status": state.get("outline_status"),
        "generated_sections": list(state.get("generated_sections", {}).keys()),
        "document_status": state.get("document_status"),
        "attachments": state.get("attachments", []),
        "unresolved_items": state.get("unresolved_items", []),
    }
```

---

## 9. 上下文管理策略

### 9.1 问题背景

qwen3.5:122b 虽然支持 128K 上下文，但：
1. 长上下文导致推理速度变慢
2. 上下文过长时 LLM 注意力分散，质量下降
3. 大量工具结果（检索片段、章节内容）快速消耗 token

### 9.2 滑动窗口 + 摘要压缩

```python
# context_manager.py

MAX_CONTEXT_TOKENS = 28000       # 总上下文窗口 (留余量)
TRIGGER_THRESHOLD = 0.85         # 85% 时触发压缩
KEEP_RECENT_TURNS = 15           # 保留最近 15 轮完整对话
```

### 9.3 压缩流程

```
messages = [msg1, msg2, ..., msgN]  (N 条消息)

1. estimate_tokens(messages) → total_tokens
2. if total_tokens > MAX_CONTEXT_TOKENS * TRIGGER_THRESHOLD:
3.   old_messages = messages[:-KEEP_RECENT_TURNS]  # 旧消息
4.   recent_messages = messages[-KEEP_RECENT_TURNS:]  # 最近15轮
5.   summary = summarize_old_messages(old_messages)  # LLM 摘要
6.   messages = [SystemMessage(summary)] + recent_messages
7.   return messages, was_compressed=True
8. else:
9.   return messages, was_compressed=False
```

### 9.4 Token 估算

```python
def estimate_tokens(messages: list[BaseMessage]) -> int:
    """中英文混合粗略估算 (字符数/2)"""
    total = 0
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        total += len(content) // 2 + 1
    return total
```

### 9.5 摘要结构

摘要只保留关键信息，不列设计输入细节（细节由 AgentState 快照提供）：

```
摘要内容 (≤500字):
- 关键决策: 已确认的产品参数、标准、设计输入项
- 当前进度: 各步骤完成状态
- 待处理项: 用户跳过或待确认的内容
```

### 9.6 旁路传递机制

为避免大段内容污染 LLM 对话历史，采用**旁路 dict** 设计：

```
问题: write_chapter 生成的章节内容 (可能数千字)
      如果放入 ToolMessage → 进入对话历史 → 消耗 token

解决: 旁路 dict
      1. write_chapter 生成后，内容存入模块级 dict
         set_current_doc_context(section_name, content)
      2. ToolMessage 只返回简短摘要 "[章节: XXX] 已生成"
      3. _after_tools_node 从旁路 dict 读取完整内容
         get_pending_chapter_content(chapter_name)
      4. 写入 state.generated_sections，不进入对话历史
```

---

## 10. System Prompt 工程

### 10.1 Prompt 结构（5 个 Section）

```python
# agent_prompt.py

def build_system_prompt(state: AgentState) -> str:
    """构建动态 System Prompt"""
    return "\n\n".join([
        ROLE_DEFINITION,      # Section 1: 角色定义 (~200 tokens)
        DOMAIN_PRIMING,       # Section 1b: 领域知识体系
        SOP_KNOWLEDGE,        # Section 2: SOP流程知识 (~800 tokens)
        TOOL_RULES,           # Section 3: 工具使用规则 (~300 tokens)
        REPLY_STYLE,          # Section 4: 回复风格 (~200 tokens)
        build_state_snapshot(state),  # Section 5: 当前状态快照 (~500 tokens, 动态)
    ])
```

### 10.2 各 Section 详解

#### Section 1: 角色定义（ROLE_DEFINITION）

```
你是贴敷式胰岛素泵RA文档专家，拥有15年以上医疗器械注册申报经验，
专精于医疗器械设计控制文档编写，覆盖设计策划->设计输入->设计输出->
设计验证->设计确认->设计转化6大阶段。

你精通以下领域:
- III类有源医疗器械设计控制流程 (ISO 13485 §7.3.2)
- 贴敷式胰岛素泵专用标准 (GB 9706.224, IEC 62304 C级)
- 医疗器械风险管理 (ISO 14971, GB/T 42062)
- 医疗器械可用性工程 (IEC 62366-1)
- NMPA III类器械注册法规
- DM Stage-Gate开发流程

你的工作方式: 心里有一套标准SOP流程，但灵活响应用户的即时需求。
永远不要说"我们不在这个阶段"或"请先完成上一步"。
```

**设计要点**：
- 明确角色身份（15年RA专家）
- 列出精通领域（引导 LLM 在这些领域更自信）
- 强调灵活响应（不强制按步骤，先响应用户即时需求）

#### Section 1b: 领域知识体系（DOMAIN_PRIMING）

注入产品核心参数、适用标准体系表、关键设计约束、DHF 清单阶段概览。

**设计要点**：Domain Priming 让 LLM 在对话前就具备领域知识背景，减少 hallucination。

#### Section 2: SOP 流程知识（SOP_KNOWLEDGE）

定义 6 阶段 100 项文档的完整编写 SOP，包括：
- 步骤 0: 文档类型识别（列出完整 100 项文档目录）
- 步骤 1-6: 产品画像 → 标准适用性 → 内容采集 → 文档生成 → 追溯矩阵 → 审核

**设计要点**：SOP 作为 LLM 的"默认工作流程"，但允许灵活跳转。

#### Section 3: 工具使用规则（TOOL_RULES）

为每个工具定义"何时用"和"规则"，引导 LLM 正确选择工具。

#### Section 4: 回复风格（REPLY_STYLE）

定义回复的语言风格、长度、格式规范。

#### Section 5: 当前状态快照（动态）

每轮对话动态注入当前 AgentState 快照，让 LLM 知道"现在进行到哪一步"。

### 10.3 Prompt 动态构建

```python
# 每轮 agent 节点执行时
async def _agent_node(state: AgentState) -> dict:
    messages = list(state.get("messages", []))
    # ... 上下文压缩 ...
    system_prompt = build_system_prompt(state)  # ← 动态构建，含状态快照
    full_messages = [SystemMessage(content=system_prompt)] + messages
    response = await model.ainvoke(full_messages)
    return {"messages": [response]}
```

**关键设计**：System Prompt 每轮重建，确保 LLM 始终看到最新状态。

---

## 11. RAG 检索架构

### 11.1 混合检索流水线

```
查询输入
    │
    ▼
┌─────────────────────────────────┐
│ 查询预处理                       │
│ - generate_search_query (可选)  │
│   LLM 生成优化查询词             │
│ - Tokenizer 分词                 │
│   jieba + 医疗器械词典            │
│   stopwords 过滤                 │
└──────────────┬──────────────────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
┌──────────┐    ┌──────────┐
│ 向量检索  │    │ BM25检索 │
│          │    │          │
│ Embedder │    │ rank_bm25│
│ 1024维   │    │ BM25Okapi│
│          │    │          │
│ ChromaDB │    │ 关键词匹配│
│ 余弦相似度│    │          │
│          │    │ 大collection│
│ 阈值≥0.3 │    │ >5万条跳过│
│          │    │          │
│ doc_type │    └────┬─────┘
│ 过滤     │         │
│ 自动降级 │         │
└────┬─────┘         │
     │               │
     └───────┬───────┘
             │
             ▼
     ┌───────────────┐
     │ 加权融合       │
     │ 向量 0.6-0.7  │
     │ BM25 0.3-0.4  │
     └───────┬───────┘
             │
             ▼
     ┌───────────────┐
     │ 跨Collection   │
     │ uploads 检索   │
     └───────┬───────┘
             │
             ▼
     ┌───────────────┐
     │ Reranker       │
     │ 语义重排序     │
     │ 截断 top_k     │
     └───────┬───────┘
             │
             ▼
     ┌───────────────┐
     │ 结构化输出     │
     │ 标题+内容片段  │
     │ 注入 Prompt    │
     └───────────────┘
```

### 11.2 检索优化设计

| 优化点 | 实现 | 效果 |
|--------|------|------|
| **Reranker** | `reranker.py` 对混合检索结果二次排序 | 提升相关性，降低噪声 |
| **医疗词典分词** | `tokenizer.py` + `medical_device_dict.txt` | 提升 BM25 在专业术语上的准确性 |
| **doc_type 过滤** | 按文档类型过滤检索范围 | 提升精确度 |
| **自动降级** | doc_type 过滤无结果时取消过滤 | 避免空结果 |
| **大 collection 跳过 BM25** | >5万条时跳过 BM25 | 避免内存过载 |
| **跨 Collection 检索** | 同时检索 `medical_device_kb_v2` + `uploads` | 整合知识库与用户附件 |
| **查询优化** | `generate_search_query` LLM 生成查询词 | 提升检索召回率 |

### 11.3 嵌入模型

- **模型**：火山方舟 `doubao-embedding-vision-250615`
- **维度**：1024
- **调用**：逐条调用（间隔 0.1s 避免限流）
- **重试**：3 次 + 指数退避

---

## 12. SSE 流式输出机制

### 12.1 SSE 事件类型

```python
# agent_engine.py - stream_agent_events()

async for event in agent.astream_events(state, config=config, version="v2"):
    event_type = event.get("event", "")

    # ── 1. LLM 逐 token 输出 ──
    if event_type == "on_chat_model_stream":
        yield {"type": "token", "content": chunk.content}

    # ── 2. 工具开始 ──
    elif event_type == "on_tool_start":
        yield {"type": "tool_start", "tool": tool_name, "input": safe_input}
        # 子代理进度事件
        if tool_name == "design_outline":
            yield {"type": "subagent_start", "agent": "outline_agent"}
        elif tool_name == "write_chapter":
            yield {"type": "subagent_start", "agent": "chapter_agent", "chapter": chapter}

    # ── 3. 工具结束 ──
    elif event_type == "on_tool_end":
        yield {"type": "tool_end", "tool": tool_name, "output_preview": output[:200]}
        # RAG 结果推送
        if tool_name in ("search_kb", "search_attachment"):
            yield {"type": "rag_results", "results": parsed["results"]}
        # 文件就绪
        if tool_name == "build_docx":
            yield {"type": "file_ready", "download_id": result["download_id"]}
        # 章节就绪
        if tool_name in ("generate_section", "revise_section"):
            yield {"type": "sections_ready"}
        # 子代理完成
        if tool_name == "design_outline":
            yield {"type": "subagent_complete", "agent": "outline_agent"}
        elif tool_name == "write_chapter":
            yield {"type": "subagent_complete", "agent": "chapter_agent"}

    # ── 4. HITL 暂停 ──
    elif event_type == "on_interrupt":
        yield {"type": "waiting_approval", "interrupt_data": event["data"]}

yield {"type": "done"}
```

### 12.2 SSE 事件清单

| 事件类型 | 触发时机 | 前端行为 |
|----------|----------|----------|
| `token` | LLM 逐 token 输出 | 打字机效果渲染 |
| `tool_start` | 工具开始执行 | 展示"检索中..." |
| `tool_end` | 工具执行结束 | 展示结果摘要 |
| `rag_results` | search_kb/search_attachment 完成 | 展示检索结果列表 |
| `file_ready` | build_docx 完成 | 弹出下载按钮 |
| `sections_ready` | generate_section/revise_section 完成 | 启用下载按钮 |
| `subagent_start` | 子代理开始 | 展示"框架设计师工作中..." |
| `subagent_complete` | 子代理完成 | 展示完成提示 |
| `waiting_approval` | HITL 暂停 | 弹出确认对话框 |
| `done` | 流结束 | 关闭加载状态 |

### 12.3 前端 SSE 处理

```javascript
// agent.html
const eventSource = new EventSource(`/api/agent/projects/${projectId}/messages`);

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch(data.type) {
        case 'token':
            appendToChat(data.content);  // 打字机效果
            break;
        case 'tool_start':
            showToolStatus(data.tool, 'running');
            break;
        case 'rag_results':
            renderRagResults(data.results);
            break;
        case 'waiting_approval':
            showHITLDialog(data.interrupt_data);  // HITL 弹窗
            break;
        case 'file_ready':
            showDownloadButton(data.download_id);
            break;
        case 'done':
            eventSource.close();
            break;
    }
};
```

---

## 13. 关键技术风险与对策

### 13.1 风险清单

| 编号 | 风险 | 影响 | 对策 |
|------|------|------|------|
| R1 | 上下文窗口溢出 | LLM 报错或质量下降 | 滑动窗口 + 摘要压缩（85% 阈值） |
| R2 | 工具调用死循环 | 资源耗尽 | `recursion_limit=100` |
| R3 | HITL 中断后进程重启 | 状态丢失 | SqliteSaver 检查点持久化 |
| R4 | LLM hallucination 标准条款 | 文档不合规 | System Prompt 强制"先检索后引用"规则 |
| R5 | 大段内容污染对话历史 | token 快速消耗 | 旁路 dict 传递机制 |
| R6 | Python 3.10 contextvar 跨 async 传播 | HITL interrupt 失败 | 异常捕获 + 静默放行降级 |
| R7 | MinerU torch 与主服务冲突 | 服务崩溃 | 子进程隔离执行 |
| R8 | BM25 大 collection 内存过载 | OOM | >5万条自动跳过 BM25 |
| R9 | 多工具并行结果丢失 | 章节内容丢失 | `_after_tools_node` 遍历所有新增 ToolMessage |
| R10 | Ollama 服务不可用 | Agent 完全不可用 | 降级为旧版表单模式 |

### 13.2 R6 详解：Python 3.10 contextvar 问题

```python
# agent_engine.py - _pre_tool_node()

try:
    decision = interrupt({
        "type": "generate_section_approval",
        "section_name": section_name,
        "message": f"即将生成「{section_name}」章节。请确认、修改或跳过。",
    })
except RuntimeError as e:
    if "get_config" in str(e):
        # Python 3.10 下 LangGraph get_config() 的 contextvar
        # 可能跨 async 任务传播失败。跳过 HITL 直接放行。
        print(f"[agent_engine] get_config unavailable, skipping HITL")
    else:
        raise
```

### 13.3 R9 详解：多工具并行结果处理

```python
# agent_engine.py - _after_tools_node()

# 问题: 主 Agent 一次调用多个 write_chapter，ToolNode 并行执行
#        如果只看 messages[-1]，前几个工具结果会被丢弃

# 解决: 从末尾向前扫描所有连续的 ToolMessage
new_tool_messages = []
for msg in reversed(messages):
    if isinstance(msg, ToolMessage):
        new_tool_messages.append(msg)
    else:
        break  # 遇到非 ToolMessage 即停止

# 遍历所有新增 ToolMessage，确保不丢结果
for tool_msg in reversed(new_tool_messages):
    tool_name, tool_args = tool_call_map.get(tool_msg.tool_call_id, (None, {}))
    if tool_name in ("generate_section", "revise_section"):
        section_name = tool_args.get("section_name", "")
        generated_sections[section_name] = content  # 写入 state
```

---

## 14. 架构总结

### 14.1 架构特点

| 特点 | 实现方式 |
|------|----------|
| **对话式交互** | LangGraph ReAct Agent + SSE 流式输出 |
| **人机协同** | interrupt() HITL + approve/edit/reject |
| **状态持久化** | AsyncSqliteSaver + thread_id 隔离 |
| **多代理协作** | outline/chapter/summary 三个子代理 |
| **本地化部署** | Ollama qwen3.5:122b + MinerU |
| **混合检索** | 向量 + BM25 + Reranker |
| **上下文管理** | 滑动窗口 + 摘要压缩 + 旁路 dict |
| **灵活工作流** | SOP 引导但允许跳转 |
| **降级容错** | auto_mode / contextvar 异常 / MinerU opt-in |

### 14.2 数据流总结

```
用户消息 → API → Agent Engine
    → 加载状态 (SqliteSaver)
    → 上下文压缩 (85% 阈值)
    → 构建 System Prompt (5 Section + 状态快照)
    → LLM 决策 (ReAct)
    → tools_condition 路由
        ├─ 直接回复 → SSE token → 前端
        └─ 调用工具
            → pre_tools (HITL 检查)
                ├─ generate_section + 非 auto → interrupt → 用户确认
                └─ 其他 → 直接执行
            → ToolNode 执行
                ├─ search_kb → RAG (向量+BM25+Reranker)
                ├─ design_outline → 子代理A
                ├─ write_chapter → 子代理B
                ├─ summarize_section → 子代理C
                ├─ build_docx → Word 输出
                └─ ...
            → after_tools (结果写回 state)
            → SqliteSaver 保存检查点
            → 循环回到 LLM 决策
```

### 14.3 关键设计原则

1. **LLM 自主决策**：ReAct 模式让 LLM 自主选择工具和策略，而非硬编码流程
2. **人类最终把关**：HITL 确保关键章节经用户确认，保证文档质量
3. **状态可恢复**：所有状态持久化，支持中断恢复和跨会话继续
4. **上下文可控**：滑动窗口 + 摘要 + 旁路 dict，确保 token 消耗可控
5. **专业分工**：多代理协作，每个子代理专注一个任务
6. **本地化优先**：LLM + 文档解析 + 向量库全部可本地部署
7. **优雅降级**：MinerU opt-in、HITL 异常放行、BM25 大 collection 跳过
8. **流式体验**：SSE 实时推送，用户无需等待

---

> **相关文档**：
> - [项目介绍.md](项目介绍.md) — 项目概述与功能介绍
> - [技术架构图.md](技术架构图.md) — 多视角架构图表
> - [ARCHITECTURE.md](ARCHITECTURE.md) — 基础架构设计文档
