"""
对话阶段向量库检索助手

在对话/聊天阶段（自由对话 + 检查点提问）复用 rag_search 的检索能力：
1. 判断用户问题是否需要检索知识库
2. 调用 RAGRetriever.search_sync_with_rerank 获取相关片段
3. 将检索结果注入 LLM prompt，生成带引用的回答

支持单 agent 与多 agent 两种对话模式共用。

MCP 增强（联网搜索/网页抓取）：mcp_manager 加载了外部 MCP 工具时，
answer_with_rag 自动切换为 tool-calling 回答——LLM 可自主调用联网搜索、
网页抓取、知识库检索、条款查询后再作答；MCP 未加载时保持原直接调用路径。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


# 触发 RAG 检索的关键词（医疗器械法规 / 标准 / 体系文件领域）
_RAG_TRIGGER_KEYWORDS = (
    "法规", "标准", "条款", "ISO", "IEC", "YY/T", "GB/T", "MDR",
    "13485", "14971", "62304", "60601", "NMPA", "GMP", "注册",
    "风险管理", "设计开发", "软件工程", "临床评价", "体系", "审核",
    "要求", "规范", "指南", "符合性", "合规",
)


def should_use_rag(question: str) -> bool:
    """启发式判断：用户问题是否应该检索向量库。

    判定规则:
      - 问题长度过短（< 4 字符）→ 不检索
      - 命中任意领域关键词 → 检索
      - 否则不检索（避免无意义召回）
    """
    if not question or len(question.strip()) < 4:
        return False
    text = question
    for kw in _RAG_TRIGGER_KEYWORDS:
        if kw.lower() in text.lower():
            return True
    return False


def retrieve_knowledge_context(
    question: str,
    retriever: Any,
    top_k: int = 5,
) -> str:
    """复用 rag_search 底层检索逻辑，返回格式化后的知识库片段文本。

    与 agent_tools.rag_search 一致：
      - 优先使用带 LLM listwise 重排的检索（search_sync_with_rerank）
      - 回退到普通检索（search_sync）
      - 失败时返回空字符串，不抛异常
    """
    if retriever is None:
        return ""

    try:
        if hasattr(retriever, "search_sync_with_rerank"):
            docs = retriever.search_sync_with_rerank(question, top_k=top_k)
        else:
            docs = retriever.search_sync(question, top_k=top_k)
    except Exception as e:
        logger.warning(f"[chat_rag] 检索失败: {e}")
        return ""

    if not docs:
        return ""

    parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.get("source", "unknown")
        text = doc.get("text", "")[:1500]
        parts.append(f"--- 参考 {i} (来源: {source}) ---\n{text}")
    return "\n\n".join(parts)


def _build_free_chat_tools(llm: Any, retriever: Any) -> list:
    """构建自由对话工具集：MCP 外部工具（联网搜索/网页抓取）+ 知识库检索/条款查询。

    仅当 mcp_manager 已加载 MCP 工具时启用（否则返回空列表，answer_with_rag
    走原直接调用路径，行为与引入 MCP 前完全一致）。复用
    agent_tools.create_audit_tools 完成模块级 retriever/llm 注入，再筛掉
    审核流程专属工具（parse_document/audit_section/assess_completeness）
    保持对话提示词精简。
    """
    try:
        from mcp_manager import get_mcp_tools
        mcp_tools = get_mcp_tools()
    except Exception:
        return []
    if not mcp_tools:
        return []  # MCP 未加载 → 保持原路径
    try:
        from agent_tools import create_audit_tools
        full = create_audit_tools(retriever, llm)
        keep = {"rag_search", "check_regulation"}
        return [t for t in full if t.name in keep] + list(mcp_tools)
    except Exception as e:
        logger.warning(f"[chat_rag] 工具集构建失败: {e}")
        return []


async def _answer_with_tools(llm: Any, tools: list, system_text: str, question: str) -> str:
    """tool-calling 回答：LLM 可在作答前自主调用联网搜索/网页抓取/知识库检索。

    返回最终回答文本；任何失败抛异常由调用方回退直接调用路径。
    """
    try:
        from langchain.agents import create_agent
    except ImportError:
        try:
            from langgraph.prebuilt import create_react_agent as create_agent  # type: ignore
        except ImportError:
            raise RuntimeError("create_agent / create_react_agent 不可用")

    agent = create_agent(model=llm, tools=tools)
    result = await agent.ainvoke({"messages": [
        SystemMessage(content=system_text),
        HumanMessage(content=question),
    ]})
    # 取最后一条非工具调用的 AI 消息作为回答
    for m in reversed(result.get("messages", [])):
        if getattr(m, "type", "") == "tool":
            continue
        content = getattr(m, "content", "")
        if content and not (getattr(m, "tool_calls", None)):
            return content if isinstance(content, str) else str(content)
    return ""


async def answer_with_rag(
    question: str,
    llm: Any,
    retriever: Any,
    *,
    system_prompt_prefix: str = "",
    report_context: str = "",
    max_context_chars: int = 4000,
    top_k: int = 5,
) -> str:
    """完整的 RAG 增强回答流程。

    Args:
        question: 用户问题原文
        llm: ChatOpenAI 实例
        retriever: RAGRetriever 实例
        system_prompt_prefix: 调用方提供的系统 prompt 前缀（角色描述等）
        report_context: 当前审核报告摘要（如处于审核中），可选
        max_context_chars: 注入 LLM 的检索上下文最大字符数
        top_k: 检索返回片段数

    Returns:
        str: LLM 回答文本
    """
    knowledge_context = ""
    used_rag = False
    if should_use_rag(question):
        knowledge_context = retrieve_knowledge_context(question, retriever, top_k=top_k)
        if knowledge_context:
            knowledge_context = knowledge_context[:max_context_chars]
            used_rag = True

    parts = []
    if system_prompt_prefix:
        parts.append(system_prompt_prefix)
    else:
        parts.append(
            "你是一个医疗器械文档审核专家，精通 ISO 13485、IEC 62304、ISO 14971、"
            "MDR 2017/745、NMPA GMP 等法规标准。"
        )

    if report_context:
        parts.append(f"## 当前审核报告摘要\n{report_context[:1500]}")

    if used_rag:
        parts.append(
            "## 知识库参考\n"
            "以下是从医疗器械法规知识库中检索到的相关内容，请在回答时参考并"
            "在合适位置注明来源（如\"参考片段1\"）：\n\n"
            f"{knowledge_context}"
        )

    parts.append(f"## 用户问题\n{question}")

    if used_rag:
        parts.append(
            "## 回答要求\n"
            "1. 优先基于知识库参考内容回答，避免编造条款编号\n"
            "2. 若知识库参考未覆盖问题要点，可结合专业知识补充，但需明确区分\n"
            "3. 回答简洁清晰"
        )
    else:
        parts.append("请基于专业知识详细回答。")

    prompt = "\n\n".join(parts)

    # MCP 工具增强（联网搜索/网页抓取）：有已加载的 MCP 工具时优先走
    # tool-calling 回答，LLM 可自主联网搜索/读网页/查知识库后再作答；
    # 失败或无工具回退下方直接调用路径（行为与引入 MCP 前一致）
    tools = _build_free_chat_tools(llm, retriever)
    if tools:
        try:
            answer = await _answer_with_tools(llm, tools, prompt, question)
            if answer:
                return answer
        except Exception as e:
            logger.warning(f"[chat_rag] tool-calling 回答失败，回退直接调用: {e}")

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.warning(f"[chat_rag] LLM 回答失败: {e}")
        return f"抱歉，处理您的问题时出错: {e}"
