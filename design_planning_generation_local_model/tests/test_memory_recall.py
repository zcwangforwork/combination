"""记忆召回精度提升测试：查询增强 / 关键词加权 / 阈值过滤 / 缓存 / 原子化沉淀 / 去重

覆盖：
1. _build_recall_query：退化消息回退 + 状态上下文拼接
2. _is_degenerate / _extract_key_terms / _keyword_score 纯函数
3. _recall_long_term_memory：相似度阈值过滤 + 会话内缓存命中
4. agent_memory._extract_atomic_memories：LLM JSON 解析（含脏输出兜底）
5. agent_memory._is_duplicate / capture_conversation_turn_atomic：去重 + 原子写入
"""
import asyncio
from unittest.mock import patch, AsyncMock

from langchain_core.messages import HumanMessage


# ── 检索侧纯函数（agent_engine） ──

def test_build_recall_query_degenerate_fallback():
    """最后一条是"继续"等退化消息时，回退到上一条实质消息，并拼接状态上下文。"""
    from app.services.agent_engine import _build_recall_query
    messages = [
        HumanMessage(content="帮我生成风险管理计划"),
        HumanMessage(content="继续"),
    ]
    q = _build_recall_query(messages, {"product_name": "贴敷式胰岛素泵", "doc_type": "risk_management_plan"})
    assert "帮我生成风险管理计划" in q
    assert "贴敷式胰岛素泵" in q
    assert "risk_management_plan" in q
    assert "继续" not in q


def test_build_recall_query_no_state():
    """无状态上下文时，仅返回用户消息本身。"""
    from app.services.agent_engine import _build_recall_query
    q = _build_recall_query([HumanMessage(content="请生成设计输入文档")])
    assert q == "请生成设计输入文档"


def test_is_degenerate():
    from app.services.agent_engine import _is_degenerate
    assert _is_degenerate("继续") is True
    assert _is_degenerate("好的") is True
    assert _is_degenerate("帮我生成风险管理计划") is False


def test_extract_key_terms():
    from app.services.agent_engine import _extract_key_terms
    terms = _extract_key_terms("ISO 13485 风险管理 0.05U/h")
    assert "ISO 13485" in terms
    assert "0.05U/h" in terms
    assert "风险管理" in terms


def test_keyword_score():
    from app.services.agent_engine import _keyword_score
    assert _keyword_score("", ["a"]) == 0.0
    assert _keyword_score("包含 ISO 13485", ["ISO 13485", "风险管理"]) == 0.1
    # 命中加分封顶 +0.4
    terms = [f"t{i}" for i in range(10)]
    assert _keyword_score(" ".join(terms), terms) == 0.4


# ── 检索侧集成（_recall_long_term_memory） ──

def test_ltm_recall_threshold_filters_low_score():
    """低于阈值的记忆被过滤，只注入高相关记忆。"""
    from app.services.agent_engine import _recall_long_term_memory, _recall_cache

    async def fake_search(query, limit=5, memory_types=None):
        return [
            {"text": "高相关记忆", "type": "semantic", "score": 0.85},
            {"text": "低相关记忆", "type": "episodic", "score": 0.2},
        ]

    async def _run():
        _recall_cache.clear()
        with patch("app.services.agent_memory.search_memories", side_effect=fake_search):
            return await _recall_long_term_memory(
                [HumanMessage(content="生成设计输入文档")], {"doc_type": "design_input"}
            )

    ctx, count, previews = asyncio.run(_run())
    assert count == 1
    assert len(previews) == 1
    assert "高相关记忆" in ctx
    assert "低相关记忆" not in ctx


def test_ltm_recall_cache_reuses_result():
    """同一查询第二次调用命中缓存，search_memories 只调用一次。"""
    from app.services.agent_engine import _recall_long_term_memory, _recall_cache

    calls = []

    async def fake_search(query, limit=5, memory_types=None):
        calls.append(query)
        return [{"text": "高相关记忆", "type": "semantic", "score": 0.85}]

    async def _run():
        _recall_cache.clear()
        with patch("app.services.agent_memory.search_memories", side_effect=fake_search):
            await _recall_long_term_memory(
                [HumanMessage(content="生成设计输入文档")], {"doc_type": "design_input"}
            )
            await _recall_long_term_memory(
                [HumanMessage(content="生成设计输入文档")], {"doc_type": "design_input"}
            )
            return len(calls)

    assert asyncio.run(_run()) == 1


# ── 写入侧（agent_memory） ──

def test_extract_atomic_memories_parses_json():
    from app.services.agent_memory import _extract_atomic_memories

    async def _run():
        with patch(
            "app.services.minimax._call_minimax_api_raw",
            return_value='[{"text": "用户偏好精炼风格", "type": "procedural"}, '
                        '{"text": "产品为贴敷式胰岛素泵", "type": "semantic"}]',
        ):
            return await _extract_atomic_memories("用户：以后精简些", "agent：好的")

    mems = asyncio.run(_run())
    assert len(mems) == 2
    assert mems[0]["type"] == "procedural"
    assert mems[1]["text"] == "产品为贴敷式胰岛素泵"


def test_extract_atomic_memories_dirty_json_falls_back():
    """LLM 返回带代码围栏的 JSON 也能解析。"""
    from app.services.agent_memory import _extract_atomic_memories

    async def _run():
        with patch(
            "app.services.minimax._call_minimax_api_raw",
            return_value='```json\n[{"text": "记住这条规则", "type": "procedural"}]\n```',
        ):
            return await _extract_atomic_memories("以后记住这条", "agent：收到")

    mems = asyncio.run(_run())
    assert len(mems) == 1
    assert mems[0]["type"] == "procedural"


def test_extract_atomic_memories_bad_json_returns_empty():
    from app.services.agent_memory import _extract_atomic_memories

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw", return_value="无法解析"):
            return await _extract_atomic_memories("用户", "agent")

    assert asyncio.run(_run()) == []


def test_is_duplicate_high_score():
    from app.services.agent_memory import _is_duplicate

    async def _run():
        with patch(
            "app.services.agent_memory.search_memories",
            new=AsyncMock(return_value=[{"text": "近似", "type": "semantic", "score": 0.95}]),
        ):
            return await _is_duplicate("近似内容", "semantic")

    assert asyncio.run(_run()) is True


def test_capture_atomic_stores_and_dedups():
    """LLM 提炼出 2 条记忆，第 2 条判重跳过，最终只写入 1 条。"""
    from app.services.agent_memory import capture_conversation_turn_atomic

    async def _run():
        with patch(
            "app.services.agent_memory._extract_atomic_memories",
            new=AsyncMock(return_value=[
                {"text": "记忆A", "type": "semantic"},
                {"text": "记忆B", "type": "episodic"},
            ]),
        ), patch(
            "app.services.agent_memory._is_duplicate",
            new=AsyncMock(side_effect=[False, True]),
        ), patch(
            "app.services.agent_memory.store_memory",
            new=AsyncMock(return_value=True),
        ) as store:
            n = await capture_conversation_turn_atomic("用户提问内容较长的场景", "agent 回答", "thread1")
            return n, store.call_count

    n, store_calls = asyncio.run(_run())
    assert n == 1
    assert store_calls == 1
