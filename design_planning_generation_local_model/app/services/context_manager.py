"""
Context Manager — 滑动窗口上下文管理

当对话历史超过约85%的上下文窗口限制时，自动将最旧的消息压缩为结构化摘要，
保留最近15轮完整对话。解决PRD Risk #3: 上下文窗口溢出。

摘要结构:
- 关键决策 (已确认的产品参数、标准、设计输入项)
- 当前进度 (各步骤完成状态)
- 待处理项 (用户跳过或待确认的内容)
"""
import json
from typing import Optional
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage


# ── Token估算 ──

def estimate_tokens(messages: list[BaseMessage]) -> int:
    """粗略估算消息列表的token数 (中文按字符数/1.5估算)"""
    total = 0
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        # 中英文混合: 粗略按字符数/2估算token数
        total += len(content) // 2 + 1
    return total


# ── 上下文窗口常量 ──

MAX_CONTEXT_TOKENS = 28000       # 总上下文窗口 (qwen3.5:122b ~128K, 留余量)
TRIGGER_THRESHOLD = 0.85         # 达到85%时触发压缩
KEEP_RECENT_TURNS = 15           # 保留最近N轮完整对话


# ── 摘要生成 ──

async def summarize_old_messages(
    old_messages: list[BaseMessage],
) -> str:
    """将旧消息列表压缩为紧凑摘要

    只保留关键决策和进度，不列出每项设计输入细节。
    设计输入细节由 agent_state 的 snapshot 提供，无需在摘要中重复。

    Args:
        old_messages: 需要压缩的旧消息列表

    Returns:
        紧凑的摘要文本（不超过500字）
    """
    try:
        from app.services.minimax import _call_minimax_api_raw

        # 提取对话文本（每条消息截取前100字，减少token消耗）
        conversation_text = ""
        for msg in old_messages:
            role = "用户" if isinstance(msg, HumanMessage) else "助手" if isinstance(msg, AIMessage) else "系统"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            conversation_text += f"[{role}]: {content[:100]}\n"

        summary_prompt = f"""将以下对话历史压缩为极简摘要（不超过300字），只保留：
- 当前在哪一步
- 哪些步骤已完成（只列步骤名，不列细节）
- 用户最近一次的具体要求

对话:
{conversation_text}

要求: 用纯文本紧凑格式，不用JSON，不列具体设计输入项。
**最新优先**: 同一参数/要求出现多个版本时（用户先说A后改为B），只保留最新值B，
旧值A一律丢弃不写入摘要（视为已被用户覆盖作废），避免新旧要求共存误导后续生成。"""

        response = _call_minimax_api_raw(
            system_prompt="你是极简对话摘要助手。每次输出不超过300字，不列清单，只概述进度。",
            user_prompt=summary_prompt,
            temperature=0.1,
            max_tokens=400,
        )

        if response:
            return response.strip()[:500]

        return _generate_fallback_summary(old_messages)

    except ImportError:
        return _generate_fallback_summary(old_messages)
    except Exception:
        return _generate_fallback_summary(old_messages)


def _generate_fallback_summary(messages: list[BaseMessage]) -> str:
    """不依赖LLM的降级摘要: 提取最近的关键决策"""
    key_terms = []
    for msg in messages[-10:]:  # 只看最近10条
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        for line in content.split("\n"):
            if any(kw in line for kw in ["确认", "跳过", "生成", "继续", "修正", "完成"]):
                key_terms.append(line.strip()[:80])

    unique_terms = list(dict.fromkeys(key_terms[-8:]))
    return "进度摘要: " + ("; ".join(unique_terms) if unique_terms else "无关键事件")


# ── 触发检查与压缩 ──

async def maybe_compress_messages(
    messages: list[BaseMessage],
    max_tokens: int = MAX_CONTEXT_TOKENS,
    threshold: float = TRIGGER_THRESHOLD,
    keep_recent: int = KEEP_RECENT_TURNS,
) -> tuple[list[BaseMessage], bool]:
    """检查消息列表是否需要压缩，如果需要则自动执行

    Args:
        messages: 当前消息列表
        max_tokens: 最大token数
        threshold: 触发阈值 (0-1)
        keep_recent: 保留最近N条消息不压缩

    Returns:
        (压缩后的消息列表, 是否发生了压缩)
    """
    current_tokens = estimate_tokens(messages)
    limit = int(max_tokens * threshold)

    if current_tokens <= limit:
        return messages, False

    # 需要压缩: 将前N-keep_recent条消息压缩为摘要
    if len(messages) <= keep_recent:
        return messages, False

    split_point = len(messages) - keep_recent
    old_messages = messages[:split_point]
    recent_messages = messages[split_point:]

    # 生成摘要并作为系统消息插入
    summary = await summarize_old_messages(old_messages)

    compressed = [
        SystemMessage(content=f"（系统内部上下文摘要，仅供你了解此前对话的进度，"
                               f"切勿在回复中复述或引用其原文）\n{summary}"),
        *recent_messages,
    ]

    return compressed, True
