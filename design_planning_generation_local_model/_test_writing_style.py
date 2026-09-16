"""快速验证"文档风格选择"功能（mock get_agent，无需启动服务）

覆盖:
1. 风格切换端点: style=concise / detailed 写入 state
2. 风格切换端点: 新线程(无 checkpoint) 用初始状态 seed
3. build_system_prompt: writing_style=concise 注入精炼风格块（仅文档内容生成）
4. build_system_prompt: writing_style=detailed/缺省 注入严谨详细风格块（回归护栏）
5. build_state_snapshot: 暴露 writing_style 供前端初始化
6. create_initial_state: writing_style 默认 detailed
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_state(values):
    """构造 aget_state 返回值"""
    class _State:
        def __init__(self, values):
            self.values = values
    return _State(values)


async def test_mode_endpoint_concise():
    """选择精炼简洁: 写入 writing_style=concise"""
    from app.api import routes as r

    fake_agent = MagicMock()
    fake_agent.aget_state = AsyncMock(return_value=_fake_state({"writing_style": "detailed"}))
    fake_agent.aupdate_state = AsyncMock()
    with patch("app.services.agent_engine.get_agent", return_value=fake_agent):
        resp = await r.agent_set_generation_mode("proj_x", style="concise")

    assert resp["success"] is True and resp["writing_style"] == "concise"
    fake_agent.aupdate_state.assert_awaited_with(
        {"configurable": {"thread_id": "proj_x"}},
        {"writing_style": "concise"},
        as_node="after_tools",
    )
    print("场景1 OK: 选择精炼简洁风格")


async def test_mode_endpoint_detailed():
    """选择严谨详细: 写入 writing_style=detailed"""
    from app.api import routes as r

    fake_agent = MagicMock()
    fake_agent.aget_state = AsyncMock(return_value=_fake_state({"writing_style": "concise"}))
    fake_agent.aupdate_state = AsyncMock()
    with patch("app.services.agent_engine.get_agent", return_value=fake_agent):
        resp = await r.agent_set_generation_mode("proj_x", style="detailed")

    assert resp["success"] is True and resp["writing_style"] == "detailed"
    fake_agent.aupdate_state.assert_awaited_with(
        {"configurable": {"thread_id": "proj_x"}},
        {"writing_style": "detailed"},
        as_node="after_tools",
    )
    print("场景2 OK: 选择严谨详细风格")


async def test_mode_endpoint_fresh_thread():
    """新线程无 checkpoint: 用 create_initial_state 合并风格 seed"""
    from app.api import routes as r

    fake_agent = MagicMock()
    fake_agent.aget_state = AsyncMock(return_value=_fake_state({}))  # 空 values → 无 checkpoint
    fake_agent.aupdate_state = AsyncMock()
    with patch("app.services.agent_engine.get_agent", return_value=fake_agent):
        resp = await r.agent_set_generation_mode("proj_new", style="concise")

    assert resp["success"] is True and resp["writing_style"] == "concise"
    call_args = fake_agent.aupdate_state.await_args
    state_vals = call_args.args[1]
    assert state_vals["writing_style"] == "concise"
    assert state_vals["messages"] == []           # 初始状态被 seed
    assert state_vals["attachments"] == []        # 初始状态被 seed
    assert call_args.kwargs["as_node"] == "after_tools"
    print("场景3 OK: 新线程 seed 初始状态")


async def test_prompt_concise_on():
    """writing_style=concise: 注入精炼风格块，且限定文档内容生成"""
    from app.services.agent_prompt import build_system_prompt

    prompt = build_system_prompt({
        "writing_style": "concise",
        "product_name": "测试产品",
        "attachments": [],
    })
    assert "文档风格：精炼简洁（已选择）" in prompt, "应包含精炼风格块"
    assert "write_chapter" in prompt, "应限定文档生成工具作用域"
    assert "不改变聊天回复风格" in prompt, "应声明聊天回复不受影响"
    assert "# 回复风格" in prompt, "原有回复风格段应保留"
    print("场景4 OK: 精炼风格注入")


async def test_prompt_detailed_default():
    """writing_style=detailed/缺省: 注入严谨详细风格块"""
    from app.services.agent_prompt import build_system_prompt

    default_prompt = build_system_prompt({})
    detailed_prompt = build_system_prompt({"writing_style": "detailed"})
    assert "文档风格：严谨详细（已选择）" in default_prompt
    assert "文档风格：精炼简洁（已选择）" not in default_prompt
    assert default_prompt == detailed_prompt, "缺省时与显式 detailed 应一致"
    print("场景5 OK: 严谨详细为默认风格")


async def test_snapshot_exposes_style():
    """build_state_snapshot 暴露 writing_style 供前端初始化"""
    from app.services.agent_state import build_state_snapshot, create_initial_state

    s_concise = build_state_snapshot({"writing_style": "concise"})
    assert s_concise["writing_style"] == "concise"

    s_off = build_state_snapshot({})
    assert s_off["writing_style"] == "detailed"

    init = create_initial_state()
    assert init["writing_style"] == "detailed", "初始状态 writing_style 应为 detailed"
    print("场景6 OK: 快照暴露 writing_style + 初始状态默认 detailed")


async def main():
    await test_mode_endpoint_concise()
    await test_mode_endpoint_detailed()
    await test_mode_endpoint_fresh_thread()
    await test_prompt_concise_on()
    await test_prompt_detailed_default()
    await test_snapshot_exposes_style()
    print("\nALL WRITING-STYLE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
