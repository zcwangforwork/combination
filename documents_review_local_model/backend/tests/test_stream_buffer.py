"""stream_buffer.EventChannel 单元测试（P0 优化新增）

覆盖 SSE 断线回放所需的核心语义：
1. seq 单调递增，events_after(cursor) 返回 oldest-first 增量
2. 断线回放：消费到 seq=N 后，用 cursor=N 重放能取到之后的新事件
3. wait_for_more：超时返回 False（心跳路径）；有新事件被唤醒返回 True
4. 容量截断：超过 cap 丢最旧事件（回放窗口有限属预期）
5. 多消费者并存：两个连接各持游标互不干扰（旧 asyncio.Queue 做不到）
6. 生产端兼容性：put() 为异步方法，签名对齐 asyncio.Queue.put（33 处调用点零改动的前提）

不依赖 pytest-asyncio：全部用 asyncio.run 驱动（对齐 test_review_auth.py）。
"""
import asyncio

from stream_buffer import EventChannel


def test_put_assigns_increasing_seq():
    async def scenario():
        ch = EventChannel()
        assert ch.last_seq == 0
        s1 = await ch.put({"event": "a"})
        s2 = await ch.put({"event": "b"})
        assert (s1, s2) == (1, 2)
        assert ch.last_seq == 2
        assert ch.buffered == 2
    asyncio.run(scenario())


def test_events_after_returns_increment_oldest_first():
    async def scenario():
        ch = EventChannel()
        for i in range(3):
            await ch.put({"event": f"e{i}"})
        # 全量回放（from_seq=0）
        assert [seq for seq, _ in ch.events_after(0)] == [1, 2, 3]
        assert [e["event"] for _, e in ch.events_after(0)] == ["e0", "e1", "e2"]
        # 增量（游标=2 → 只拿 seq 3）
        assert [seq for seq, _ in ch.events_after(2)] == [3]
        # 游标领先 → 空
        assert ch.events_after(3) == []
    asyncio.run(scenario())


def test_replay_after_disconnect():
    """模拟：消费到 seq=1 断线 → 期间产生 seq 2/3 → 重连 from_seq=1 补齐"""
    async def scenario():
        ch = EventChannel()
        await ch.put({"event": "checkpoint"})
        seen = ch.events_after(0)          # 消费方拿到 seq 1
        cursor = seen[-1][0]
        await ch.put({"event": "token"})   # 断线期间
        await ch.put({"event": "complete"})
        missed = ch.events_after(cursor)   # 重连回放
        assert [e["event"] for _, e in missed] == ["token", "complete"]
    asyncio.run(scenario())


def test_wait_for_more_timeout_returns_false():
    async def scenario():
        ch = EventChannel()
        assert await ch.wait_for_more(0, timeout=0.05) is False
    asyncio.run(scenario())


def test_wait_for_more_woken_by_put():
    async def scenario():
        ch = EventChannel()
        await ch.put({"event": "x"})

        async def producer():
            await asyncio.sleep(0.02)
            await ch.put({"event": "y"})

        await asyncio.gather(
            ch.wait_for_more(1, timeout=2.0),  # 等待 seq>1
            producer(),
            return_exceptions=False,
        )
        assert ch.last_seq == 2
        assert await ch.wait_for_more(1, timeout=0.01) is True  # 已有新事件立即返回
    asyncio.run(scenario())


def test_cap_trims_oldest():
    async def scenario():
        ch = EventChannel(cap=3)
        for i in range(5):
            await ch.put({"event": f"e{i}"})
        assert ch.buffered == 3
        assert ch.oldest_seq() == 3           # seq 1/2 已被丢弃
        assert [seq for seq, _ in ch.events_after(0)] == [3, 4, 5]
        assert [seq for seq, _ in ch.events_after(2)] == [3, 4, 5]  # 越过截断窗口
    asyncio.run(scenario())


def test_two_consumers_independent_cursors():
    """多连接并存：慢消费者重放旧事件时，快消费者仍能拿到新事件"""
    async def scenario():
        ch = EventChannel()
        await ch.put({"event": "a"})
        await ch.put({"event": "b"})

        slow = ch.events_after(0)    # 慢连接从 0 回放
        fast_cursor = 2
        await ch.put({"event": "c"})
        fast = ch.events_after(fast_cursor)

        assert [e["event"] for _, e in slow] == ["a", "b"]
        assert [e["event"] for _, e in fast] == ["c"]
    asyncio.run(scenario())


def test_put_api_compatible_with_queue_await():
    """生产端兼容性：await channel.put(event) 与 await queue.put(event) 等价可用"""
    async def scenario():
        ch = EventChannel()
        # 与 asyncio.Queue 相同的调用形态（main.py 33 处生产点的写法）
        await ch.put({"event": "heartbeat"})
        assert ch.events_after(0)[0][1] == {"event": "heartbeat"}
    asyncio.run(scenario())
