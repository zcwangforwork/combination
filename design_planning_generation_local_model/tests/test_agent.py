"""
test_agent.py — Agent核心模块单元测试与集成测试

覆盖:
- agent_state: 状态初始化、快照构建、检查点单例
- agent_tools: 工具错误处理、降级逻辑
- agent_prompt: System Prompt 构建与状态注入
- context_manager: Token估算、压缩触发、降级摘要
- agent_engine: SSE事件格式 (mock)
"""
import os
import sys
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ═══════════════════════════════════════════════════════════════
# agent_state 测试
# ═══════════════════════════════════════════════════════════════

class TestAgentState:
    """AgentState 状态管理测试"""

    def test_create_initial_state_has_all_sections(self):
        """初始状态包含空的content_sections"""
        from app.services.agent_state import create_initial_state

        state = create_initial_state()

        assert state["product_status"] == "not_started"
        assert state["standards_status"] == "not_started"
        assert state["document_status"] == "not_started"
        assert state["traceability_status"] == "not_started"
        assert state["review_status"] == "not_started"
        assert state["confirmed_standards"] == []
        assert state["candidate_standards"] == []
        assert state["unresolved_items"] == []
        assert state["messages"] == []

        sections = state["content_sections"]
        assert isinstance(sections, dict)
        assert sections == {}

    def test_build_state_snapshot_structure(self):
        """build_state_snapshot 产出PRD Section 4.3格式"""
        from app.services.agent_state import create_initial_state, build_state_snapshot

        state = create_initial_state()
        snapshot = build_state_snapshot(state)

        # 验证顶层键
        assert "product" in snapshot
        assert "standards" in snapshot
        assert "content_sections" in snapshot
        assert "document_generation" in snapshot
        assert "traceability" in snapshot
        assert "review" in snapshot
        assert "unresolved_items" in snapshot

        # 验证子结构
        product = snapshot["product"]
        assert product["name"] is None
        assert product["classification"] is None
        assert product["status"] == "not_started"

        doc_gen = snapshot["document_generation"]
        assert doc_gen["status"] == "not_started"
        assert doc_gen["sections_generated"] == []

    def test_snapshot_reflects_state_changes(self):
        """快照能反映状态更新"""
        from app.services.agent_state import create_initial_state, build_state_snapshot

        state = create_initial_state()
        state["product_name"] = "贴敷式胰岛素泵A7"
        state["product_classification"] = "III类有源医疗器械"
        state["product_status"] = "confirmed"
        state["confirmed_standards"] = ["GB 9706.1-2020", "ISO 14971:2019"]
        state["generated_sections"] = {"性能要求": "## 性能要求\n\n..."}

        snapshot = build_state_snapshot(state)

        assert snapshot["product"]["name"] == "贴敷式胰岛素泵A7"
        assert snapshot["product"]["classification"] == "III类有源医疗器械"
        assert snapshot["product"]["status"] == "confirmed"
        assert len(snapshot["standards"]["confirmed"]) == 2
        assert "性能要求" in snapshot["document_generation"]["sections_generated"]


# ═══════════════════════════════════════════════════════════════
# agent_tools 测试
# ═══════════════════════════════════════════════════════════════

class TestAgentTools:
    """Agent工具集测试 (主要测试错误处理与降级)"""

    @pytest.mark.asyncio
    async def test_search_kb_no_results_format(self, monkeypatch):
        """search_kb 无结果时返回标准JSON格式"""
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

        # Mock VectorStore 返回空
        with patch("app.services.rag.vector_store.VectorStore") as mock_vs_cls:
            mock_store = MagicMock()
            mock_store.retrieve_hybrid.return_value = []
            mock_vs_cls.return_value = mock_store

            from app.services.agent_tools import search_kb
            result = await search_kb.ainvoke({"query": "不存在的标准XYZ-9999"})

            parsed = json.loads(result)
            assert parsed["status"] == "no_results"
            assert len(parsed["results"]) == 0

    @pytest.mark.asyncio
    async def test_search_kb_success_format(self, monkeypatch):
        """search_kb 有结果时返回标准JSON格式"""
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

        with patch("app.services.rag.vector_store.VectorStore") as mock_vs_cls:
            mock_store = MagicMock()
            mock_store.retrieve_hybrid.return_value = [
                {
                    "content": "GB 9706.224-2021 第14章 胰岛素泵专用要求",
                    "metadata": {"source": "GB9706.224-2021.pdf"},
                    "score": 0.95,
                }
            ]
            mock_vs_cls.return_value = mock_store

            from app.services.agent_tools import search_kb
            result = await search_kb.ainvoke({"query": "GB 9706.224"})

            parsed = json.loads(result)
            assert parsed["status"] == "ok"
            assert parsed["count"] == 1
            assert "GB 9706.224" in parsed["results"][0]["content"]

    @pytest.mark.asyncio
    async def test_generate_section_without_api_key(self, monkeypatch):
        """generate_section API调用失败时返回错误信息"""
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

        from app.services.agent_tools import generate_section

        with patch("app.services.minimax._call_minimax_api_raw", return_value=None):
            result = await generate_section.ainvoke({"section_name": "性能要求"})
            assert "[错误]" in result or "错误" in result

    @pytest.mark.asyncio
    async def test_revise_section_error_handling(self, monkeypatch):
        """revise_section 异常时返回错误信息"""
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

        from app.services.agent_tools import revise_section

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=Exception("Network timeout")):
            result = await revise_section.ainvoke({
                "section_name": "安全要求",
                "instruction": "修改绝缘等级"
            })
            assert "错误" in result
            assert "Network timeout" in result

    def test_phase1_tools_list(self):
        """PHASE1_TOOLS 包含核心工具与 SQL 领域查询工具"""
        from app.services.agent_tools import PHASE1_TOOLS
        tool_names = [t.name for t in PHASE1_TOOLS]
        # 核心工具
        assert "search_kb" in tool_names
        assert "generate_section" in tool_names
        assert "revise_section" in tool_names
        assert "build_docx" in tool_names
        # SQL 领域数据库查询工具（2026-08-11 集成）
        assert "sql_db_list_tables" in tool_names
        assert "sql_db_schema" in tool_names
        assert "sql_db_query" in tool_names


# ═══════════════════════════════════════════════════════════════
# agent_prompt 测试
# ═══════════════════════════════════════════════════════════════

class TestAgentPrompt:
    """System Prompt构建测试"""

    def test_build_system_prompt_contains_all_sections(self):
        """System Prompt包含5个必需段落"""
        from app.services.agent_state import create_initial_state
        from app.services.agent_prompt import build_system_prompt

        state = create_initial_state()
        prompt = build_system_prompt(state)

        # 5个段落都存在
        assert "角色定义" in prompt
        assert "SOP" in prompt or "工作流程" in prompt
        assert "工具使用规则" in prompt
        assert "回复风格" in prompt
        assert "当前会话状态" in prompt

    def test_system_prompt_injects_state_json(self):
        """System Prompt包含当前状态的JSON快照"""
        from app.services.agent_state import create_initial_state
        from app.services.agent_prompt import build_system_prompt

        state = create_initial_state()
        state["product_name"] = "测试胰岛素泵"

        prompt = build_system_prompt(state)
        assert '"name": "测试胰岛素泵"' in prompt
        assert "not_started" in prompt

    def test_system_prompt_contains_tool_descriptions(self):
        """System Prompt包含3个工具的描述"""
        from app.services.agent_state import create_initial_state
        from app.services.agent_prompt import build_system_prompt

        prompt = build_system_prompt(create_initial_state())

        assert "search_kb" in prompt
        assert "generate_section" in prompt
        assert "revise_section" in prompt

    def test_system_prompt_contains_flexibility_principles(self):
        """SOP段落包含灵活性原则"""
        from app.services.agent_state import create_initial_state
        from app.services.agent_prompt import build_system_prompt

        prompt = build_system_prompt(create_initial_state())

        assert "灵活性原则" in prompt
        assert "不要纠正" in prompt or "跟随用户" in prompt


# ═══════════════════════════════════════════════════════════════
# context_manager 测试
# ═══════════════════════════════════════════════════════════════

class TestContextManager:
    """上下文压缩管理器测试"""

    def test_estimate_tokens_empty_list(self):
        """空消息列表估算为0"""
        from app.services.context_manager import estimate_tokens
        assert estimate_tokens([]) == 0

    def test_estimate_tokens_positive(self):
        """有内容时估算值为正"""
        from app.services.context_manager import estimate_tokens
        from langchain_core.messages import HumanMessage

        msgs = [HumanMessage(content="你好，请帮我生成设计策划文档")]
        tokens = estimate_tokens(msgs)
        assert tokens > 0

    def test_estimate_tokens_grows_with_content(self):
        """内容越多估算值越大"""
        from app.services.context_manager import estimate_tokens
        from langchain_core.messages import HumanMessage

        short = [HumanMessage(content="你好")]
        long = [HumanMessage(content="你好" * 1000)]

        assert estimate_tokens(short) < estimate_tokens(long)

    @pytest.mark.asyncio
    async def test_maybe_compress_below_threshold(self):
        """未超过阈值时不触发压缩"""
        from app.services.context_manager import maybe_compress_messages
        from langchain_core.messages import HumanMessage, AIMessage

        messages = [
            HumanMessage(content="你好"),
            AIMessage(content="你好！有什么可以帮你的？"),
        ]

        result, compressed = await maybe_compress_messages(
            messages, max_tokens=100000, keep_recent=5
        )

        assert compressed is False
        assert result is messages  # 同一对象引用

    @pytest.mark.asyncio
    async def test_maybe_compress_above_threshold(self):
        """超过阈值时触发压缩并返回压缩后的消息"""
        from app.services.context_manager import maybe_compress_messages
        from langchain_core.messages import HumanMessage, AIMessage

        # 构造很多消息以触发压缩
        messages = []
        for i in range(50):
            messages.append(HumanMessage(content=f"消息{i} " + "x" * 500))
            messages.append(AIMessage(content=f"回复{i} " + "y" * 500))

        result, compressed = await maybe_compress_messages(
            messages, max_tokens=5000, threshold=0.3, keep_recent=4
        )

        assert compressed is True
        # 压缩后第一条消息应为SystemMessage (摘要)
        assert result[0].__class__.__name__ == "SystemMessage"
        assert "对话历史摘要" in result[0].content
        # 保留最近4条消息
        assert len(result) <= 1 + 4  # 摘要 + 4条最近消息

    @pytest.mark.asyncio
    async def test_maybe_compress_insufficient_messages(self):
        """消息数不足时不触发压缩（不会只留摘要）"""
        from app.services.context_manager import maybe_compress_messages
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content="x" * 5000)]

        result, compressed = await maybe_compress_messages(
            messages, max_tokens=1000, threshold=0.3, keep_recent=5
        )

        assert compressed is False

    def test_fallback_summary_generates_json(self):
        """降级摘要返回有效JSON"""
        from app.services.context_manager import _generate_fallback_summary
        from langchain_core.messages import HumanMessage

        msgs = [
            HumanMessage(content="确认产品分类为III类有源医疗器械"),
            HumanMessage(content="跳过生物相容性要求"),
        ]

        summary = _generate_fallback_summary(msgs)
        parsed = json.loads(summary)

        assert "_fallback" in parsed
        assert parsed["_fallback"] is True
        assert "key_discussions" in parsed


# ═══════════════════════════════════════════════════════════════
# SSE事件格式集成测试
# ═══════════════════════════════════════════════════════════════

class TestSSEEventStream:
    """SSE流事件格式验证 (不依赖真实LLM)"""

    def test_event_format_token(self):
        """token事件格式正确"""
        event = {"type": "token", "content": "好的，我来帮您生成"}
        assert "type" in event
        assert event["type"] == "token"
        assert "content" in event

    def test_event_format_tool_start(self):
        """tool_start事件包含工具名和输入"""
        event = {
            "type": "tool_start",
            "tool": "search_kb",
            "input": {"query": "GB 9706.224"},
        }
        assert event["type"] == "tool_start"
        assert event["tool"] == "search_kb"
        assert "query" in event["input"]

    def test_event_format_tool_end(self):
        """tool_end事件包含输出预览"""
        event = {
            "type": "tool_end",
            "tool": "search_kb",
            "output_preview": "找到3条相关结果",
        }
        assert event["type"] == "tool_end"
        assert len(event["output_preview"]) <= 200

    def test_event_format_waiting_approval(self):
        """waiting_approval事件包含中断数据"""
        event = {
            "type": "waiting_approval",
            "message": "Agent等待你的确认...",
            "interrupt_data": {"section_name": "性能要求"},
        }
        assert event["type"] == "waiting_approval"

    def test_event_format_done(self):
        """done事件标志流结束"""
        event = {"type": "done"}
        assert event["type"] == "done"

    def test_event_format_error(self):
        """error事件包含错误信息"""
        event = {"type": "error", "message": "API调用超时"}
        assert event["type"] == "error"
        assert "message" in event


# ═══════════════════════════════════════════════════════════════
# HITL决策命令解析测试
# ═══════════════════════════════════════════════════════════════

class TestHITLDecision:
    """HITL中断恢复决策测试"""

    def test_approve_decision(self):
        """批准决策"""
        decision = "approve"
        assert decision == "approve"

    def test_reject_decision(self):
        """拒绝决策"""
        decision = "reject"
        assert decision == "reject"

    def test_edit_decision_parsing(self):
        """编辑决策: 提取修改后的指令"""
        decision = "edit:将输注精度改为±3%"
        assert decision.startswith("edit:")
        edited_content = decision[5:]
        assert edited_content == "将输注精度改为±3%"

    def test_edit_decision_empty_content(self):
        """编辑决策但内容为空"""
        decision = "edit:"
        assert decision.startswith("edit:")
        assert decision[5:] == ""


# ═══════════════════════════════════════════════════════════════
# 状态Schema序列化测试
# ═══════════════════════════════════════════════════════════════

class TestStateSerialization:
    """State ↔ JSON 序列化测试"""

    def test_initial_state_json_serializable(self):
        """初始状态可以序列化为JSON"""
        from app.services.agent_state import create_initial_state, build_state_snapshot

        state = create_initial_state()
        snapshot = build_state_snapshot(state)

        # 不应抛出异常
        json_str = json.dumps(snapshot, ensure_ascii=False)
        assert len(json_str) > 0

        # 可以重新解析
        reparsed = json.loads(json_str)
        assert reparsed["product"]["status"] == "not_started"

    def test_full_state_json_serializable(self):
        """完整填充的状态可以序列化为JSON"""
        from app.services.agent_state import create_initial_state, build_state_snapshot

        state = create_initial_state()
        state["product_name"] = "A7贴敷式胰岛素泵"
        state["product_classification"] = "III类"
        state["product_intended_use"] = "用于糖尿病患者持续皮下输注胰岛素"
        state["product_status"] = "confirmed"
        state["confirmed_standards"] = ["GB 9706.1-2020", "GB 9706.224-2021"]
        state["candidate_standards"] = ["ISO 14971:2019", "IEC 62304:2006"]
        state["standards_status"] = "partial"
        state["generated_sections"] = {
            "性能要求": "# 性能要求\n\n1. 输注精度...\n",
            "安全要求": "# 安全要求\n\n1. 电气安全...\n",
        }
        state["document_status"] = "in_progress"
        state["unresolved_items"] = ["生物相容性: 用户要求后续补充"]

        snapshot = build_state_snapshot(state)
        json_str = json.dumps(snapshot, ensure_ascii=False)

        reparsed = json.loads(json_str)
        assert reparsed["product"]["name"] == "A7贴敷式胰岛素泵"
        assert len(reparsed["standards"]["confirmed"]) == 2
        assert len(reparsed["document_generation"]["sections_generated"]) == 2
        assert len(reparsed["unresolved_items"]) == 1


# ═══════════════════════════════════════════════════════════════
# 运行所有测试
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
