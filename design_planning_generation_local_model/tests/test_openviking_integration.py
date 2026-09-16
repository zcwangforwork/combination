"""
OpenViking 集成单元测试（Phase 1 capture-only）

测试范围（评审决策 #2 完整单元测试）：
1. OpenVikingService 降级路径（init/available/capture/close）
2. capture-only 工具过滤（决策 #3 合规收窄）
3. 增量捕获 + session 隔离
4. 异常静默降级（critical gap 验证）

运行方式：
    cd design_planning_generation_local_model
    source E:/anaconda/anaconda_content/etc/profile.d/conda.sh && conda activate env_01
    python -m pytest tests/test_openviking_integration.py -v
"""
import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage


# ── 测试 OpenVikingService 降级路径 ──

@pytest.mark.asyncio
async def test_service_disabled_when_env_false(monkeypatch):
    """OPENVIKING_ENABLED=false 时服务不初始化，is_available 返回 False。"""
    monkeypatch.setenv("OPENVIKING_ENABLED", "false")
    from app.services.openviking_client import OpenVikingService
    svc = OpenVikingService()
    assert not svc.enabled
    ok = await svc.initialize()
    assert not ok
    assert not svc.is_available()
    assert svc.get_capture_tools() == []


@pytest.mark.asyncio
async def test_capture_silent_degradation_when_unavailable():
    """recorder 不可用时 capture_messages 静默降级（不抛异常）。"""
    from app.services.openviking_client import OpenVikingService
    svc = OpenVikingService()
    svc._recorder = None  # 模拟不可用
    # 不应抛异常
    await svc.capture_messages([HumanMessage(content="test")], "test-session")


@pytest.mark.asyncio
async def test_capture_silent_degradation_on_exception():
    """add_message 抛异常时不传播（critical gap 验证）。

    场景：OpenViking 服务器运行中崩溃，写入消息抛连接异常。
    期望：capture_messages 捕获异常仅记日志，不中断 Agent。
    """
    from app.services.openviking_client import OpenVikingService
    svc = OpenVikingService()
    # 模拟 async client 写入时抛异常（服务器崩溃）
    mock_client = MagicMock()
    mock_client.add_message = AsyncMock(side_effect=ConnectionError("server crash"))
    mock_recorder = MagicMock()
    mock_recorder.get_async_client = AsyncMock(return_value=mock_client)
    svc._recorder = mock_recorder

    # 不应抛异常
    msgs = [HumanMessage(content="test")]
    await svc.capture_messages(msgs, "test-session")


@pytest.mark.asyncio
async def test_capture_empty_session_id_skipped():
    """session_id 为空时跳过 capture。"""
    from app.services.openviking_client import OpenVikingService
    svc = OpenVikingService()
    mock_recorder = MagicMock()
    svc._recorder = mock_recorder

    await svc.capture_messages([HumanMessage(content="test")], "")
    mock_recorder.get_async_client.assert_not_called()


# ── 测试增量捕获 + session 隔离 ──

@pytest.mark.asyncio
async def test_capture_incremental():
    """增量捕获：只捕获新增消息，避免重复写入。"""
    from app.services.openviking_client import OpenVikingService

    svc = OpenVikingService()
    mock_client = MagicMock()
    mock_client.add_message = AsyncMock()
    mock_recorder = MagicMock()
    mock_recorder.get_async_client = AsyncMock(return_value=mock_client)
    svc._recorder = mock_recorder

    # 第一次：1 条消息
    msgs1 = [HumanMessage(content="hello")]
    await svc.capture_messages(msgs1, "session-1")
    assert mock_client.add_message.call_count == 1

    # 第二次：2 条消息（增量 1 条）
    msgs2 = [HumanMessage(content="hello"), AIMessage(content="hi")]
    await svc.capture_messages(msgs2, "session-1")
    assert mock_client.add_message.call_count == 2  # 只捕获增量 1 条


@pytest.mark.asyncio
async def test_capture_no_new_messages_skipped():
    """无新增消息时跳过 capture（如 HITL resume 未产生新回复）。"""
    from app.services.openviking_client import OpenVikingService

    svc = OpenVikingService()
    mock_client = MagicMock()
    mock_client.add_message = AsyncMock()
    mock_recorder = MagicMock()
    mock_recorder.get_async_client = AsyncMock(return_value=mock_client)
    svc._recorder = mock_recorder

    msgs = [HumanMessage(content="hello")]
    await svc.capture_messages(msgs, "session-1")
    assert mock_client.add_message.call_count == 1

    # 再次传入相同消息：无增量，不应调用 add_message
    await svc.capture_messages(msgs, "session-1")
    assert mock_client.add_message.call_count == 1  # 仍为 1


@pytest.mark.asyncio
async def test_capture_session_isolation():
    """不同 session 独立跟踪已捕获量。"""
    from app.services.openviking_client import OpenVikingService

    svc = OpenVikingService()
    mock_client = MagicMock()
    mock_client.add_message = AsyncMock()
    mock_recorder = MagicMock()
    mock_recorder.get_async_client = AsyncMock(return_value=mock_client)
    svc._recorder = mock_recorder

    await svc.capture_messages([HumanMessage(content="a")], "session-A")
    await svc.capture_messages([HumanMessage(content="b")], "session-B")

    assert mock_client.add_message.call_count == 2

    # session-A 第二次：1 条新增
    await svc.capture_messages(
        [HumanMessage(content="a"), AIMessage(content="reply-a")], "session-A"
    )
    assert mock_client.add_message.call_count == 3


# ── 测试 capture-only 工具过滤（决策 #3 合规收窄）──

def test_capture_tools_only_store_and_add_resource():
    """get_capture_tools 只返回 viking_store / viking_add_resource。

    评审决策 #3：Phase 1 capture-only，recall 类工具移到 Phase 3 + audit log。
    """
    from app.services.openviking_client import OpenVikingService
    svc = OpenVikingService()

    # 模拟 capture 工具（与真实 create_openviking_tools 返回的工具名一致）
    store_tool = MagicMock()
    store_tool.name = "viking_store"
    add_resource_tool = MagicMock()
    add_resource_tool.name = "viking_add_resource"
    svc._capture_tools = [store_tool, add_resource_tool]

    tools = svc.get_capture_tools()
    assert len(tools) == 2
    tool_names = {t.name for t in tools}
    assert tool_names == {"viking_store", "viking_add_resource"}
    # 不应包含 recall 类工具
    assert "viking_find" not in tool_names
    assert "viking_search" not in tool_names
    assert "viking_read" not in tool_names


def test_capture_tools_returns_copy():
    """get_capture_tools 返回副本，修改不影响内部状态。"""
    from app.services.openviking_client import OpenVikingService
    svc = OpenVikingService()
    svc._capture_tools = [MagicMock(name="viking_store")]

    tools = svc.get_capture_tools()
    tools.clear()
    # 内部列表不受影响
    assert len(svc._capture_tools) == 1


# ── 测试 close ──

@pytest.mark.asyncio
async def test_close_clears_state():
    """close 清理 recorder 和工具列表。"""
    from app.services.openviking_client import OpenVikingService
    svc = OpenVikingService()
    mock_recorder = MagicMock()
    mock_recorder.aclose = AsyncMock()
    svc._recorder = mock_recorder
    svc._capture_tools = [MagicMock()]
    svc._session_captured_count = {"s1": 5}

    await svc.close()

    assert svc._recorder is None
    assert svc._capture_tools == []
    assert svc._session_captured_count == {}


@pytest.mark.asyncio
async def test_close_silent_on_recorder_failure():
    """recorder.aclose 异常时静默降级。"""
    from app.services.openviking_client import OpenVikingService
    svc = OpenVikingService()
    mock_recorder = MagicMock()
    mock_recorder.aclose = AsyncMock(side_effect=Exception("close failed"))
    svc._recorder = mock_recorder

    # 不应抛异常
    await svc.close()
    assert svc._recorder is None


# ── 测试模块级单例 ──

@pytest.mark.asyncio
async def test_init_and_close_singleton(monkeypatch):
    """init_openviking / get_openviking_service / close_openviking 单例生命周期。"""
    monkeypatch.setenv("OPENVIKING_ENABLED", "false")
    from app.services import openviking_client

    ok = await openviking_client.init_openviking()
    assert not ok  # disabled

    svc = openviking_client.get_openviking_service()
    assert svc is not None
    assert not svc.is_available()

    await openviking_client.close_openviking()
    assert openviking_client.get_openviking_service() is None
