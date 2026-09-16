"""agent_streams 后台生成流管理器测试

验证「生成执行与 SSE 连接解耦」的核心行为：
1. 订阅者断开（客户端切换聊天任务）不会取消后台生成任务；
2. 重连后能从 from_seq 回放已缓冲事件并继续实时接收；
3. cancel_stream 显式取消（撤回消息/删除任务场景）；
4. 同一项目重复启动生成会被拒绝（busy 保护）。

通过 importlib 直接按文件加载模块，避免引入整个 app 包的重依赖。
"""
import asyncio
import importlib.util
from pathlib import Path

import pytest

_mod_path = Path(__file__).parent.parent / "app" / "services" / "agent_streams.py"
_spec = importlib.util.spec_from_file_location("agent_streams_under_test", _mod_path)
agent_streams = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent_streams)


def _make_source(n_events, delay=0.01, hang=False):
    """构造一个产生 n_events 条事件的异步事件源工厂"""
    async def _source():
        for i in range(n_events):
            yield {"type": "token", "content": f"t{i}"}
            await asyncio.sleep(delay)
        if hang:
            # 模拟长时间生成（等待被取消）
            await asyncio.sleep(3600)
    return _source


async def _collect(agen, max_events=None):
    """消费订阅生成器，收集事件（max_events 到达后主动断开，模拟客户端切走）"""
    out = []
    async for ev in agen:
        out.append(ev)
        if max_events is not None and len(out) >= max_events:
            break
    return out


@pytest.fixture(autouse=True)
def _clear_streams():
    agent_streams._streams.clear()
    yield
    agent_streams._streams.clear()


async def test_disconnect_does_not_cancel_background():
    """核心：订阅者中途断开后，后台生成仍执行到完成"""
    stream = agent_streams.start_stream("p1", "message", _make_source(10, delay=0.02))

    # 模拟 SSE 订阅者：只收 3 条就断开（生成器被 aclose，等价于连接取消）
    sub = agent_streams.subscribe_stream(stream, from_seq=0)
    partial = await _collect(sub, max_events=3)
    await sub.aclose()
    assert len(partial) == 3

    # 后台任务不受影响，等待其完成
    await asyncio.wait_for(stream.task, timeout=5)
    assert stream.status == "done"
    assert stream.next_seq == 10

    # 缓冲区保留了全部事件
    events, next_seq = stream.snapshot(0)
    assert len(events) == 10
    assert next_seq == 10


async def test_reconnect_replays_all_events():
    """断开后重连：from_seq=0 回放全部事件"""
    stream = agent_streams.start_stream("p2", "message", _make_source(5, delay=0.01))
    sub1 = agent_streams.subscribe_stream(stream, from_seq=0)
    await _collect(sub1, max_events=2)
    await sub1.aclose()

    await asyncio.wait_for(stream.task, timeout=5)

    # 重连（流已结束但缓冲未过期）：应回放全部 5 条并正常终止
    replayed = await asyncio.wait_for(
        _collect(agent_streams.subscribe_stream(stream, from_seq=0)), timeout=2)
    assert [e["content"] for e in replayed] == ["t0", "t1", "t2", "t3", "t4"]


async def test_reconnect_from_seq_partial():
    """from_seq=N 只回放 seq >= N 的事件"""
    stream = agent_streams.start_stream("p3", "message", _make_source(6, delay=0.01))
    await asyncio.wait_for(stream.task, timeout=5)

    replayed = await asyncio.wait_for(
        _collect(agent_streams.subscribe_stream(stream, from_seq=4)), timeout=2)
    assert [e["content"] for e in replayed] == ["t4", "t5"]


async def test_live_events_dedup_on_reconnect():
    """重连进行中的流：回放 + 实时续接，无丢失、无重复"""
    stream = agent_streams.start_stream("p4", "message", _make_source(20, delay=0.02))
    await asyncio.sleep(0.1)  # 让前几条事件先进缓冲

    events = await asyncio.wait_for(
        _collect(agent_streams.subscribe_stream(stream, from_seq=0)), timeout=5)
    contents = [e["content"] for e in events]
    assert contents == [f"t{i}" for i in range(20)]  # 完整且有序、无重复


async def test_cancel_stream():
    """显式取消：状态置 cancelled，订阅者收到 cancelled 事件与结束哨兵"""
    stream = agent_streams.start_stream("p5", "message", _make_source(3, delay=0.01, hang=True))
    await asyncio.sleep(0.1)

    ok = await agent_streams.cancel_stream("p5")
    assert ok is True
    assert stream.status == "cancelled"

    # 回放中应包含 cancelled 通知事件
    events, _ = stream.snapshot(0)
    assert events[-1]["type"] == "cancelled"

    # 无进行中流时再次取消返回 False
    assert await agent_streams.cancel_stream("p5") is False


async def test_busy_guard():
    """同一项目已有进行中生成时，重复启动被拒绝"""
    agent_streams.start_stream("p6", "message", _make_source(3, delay=0.05, hang=True))
    with pytest.raises(RuntimeError):
        agent_streams.start_stream("p6", "message", _make_source(1))
    assert agent_streams.get_active_stream("p6") is not None

    # 结束后（TTL 内）仍可从 status 查到，但 active=False
    await agent_streams.cancel_stream("p6")
    status = agent_streams.get_status("p6")
    assert status["exists"] is True
    assert status["active"] is False
    assert status["status"] == "cancelled"


async def test_status_fields():
    """status 接口透出 meta（history_count / user_message）供前端重连恢复现场"""
    stream = agent_streams.start_stream(
        "p7", "message", _make_source(2, delay=0.01),
        meta={"history_count": 4, "user_message": "帮我生成计划书"})
    await asyncio.wait_for(stream.task, timeout=5)

    status = agent_streams.get_status("p7")
    assert status["active"] is False
    assert status["status"] == "done"
    assert status["kind"] == "message"
    assert status["seq"] == 2
    assert status["history_count"] == 4
    assert status["user_message"] == "帮我生成计划书"

    # 不存在的项目
    none_status = agent_streams.get_status("nope")
    assert none_status == {"exists": False, "active": False}
