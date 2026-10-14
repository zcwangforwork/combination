# -*- coding: utf-8 -*-
"""
stream_buffer — 审核会话的可回放事件通道（P0 优化：SSE 断线重连 + 事件回放）

背景（2026-10-13 差距分析）：原实现用 asyncio.Queue 单消费推送 SSE 事件，
事件「消费即丢」——断线/刷新期间产生的事件永久丢失，且同一时刻只允许一个
消费者（重连的新连接会与旧连接的挂起 get() 竞争抢事件）。对齐写作 agent 的
agent_streams.py 能力，改为带自增 seq 的事件日志 + Condition 通知：

- 生产端接口不变：`await session.queue.put(event)`（EventChannel 提供同名方法，
  33 处生产调用点零改动）；
- 消费端改为游标式：`events_after(cursor)` 拿增量，`wait_for_more(cursor, t)`
  等新事件；每个连接持有自己的游标 → 多连接安全、断线后可用 from_seq 回放；
- 日志容量上限 STREAM_BUFFER_CAP，超限丢弃最旧事件（回放窗口有限，属预期：
  回放覆盖的是断线重连场景，不是全量历史——全量历史走 checkpoint 重建的
  /api/{agent,multi-agent}/conversation/history 端点）。
"""
import asyncio
from typing import Dict, List, Optional, Tuple

# 事件日志容量（条）。事件含 token 碎片，2000 条足够覆盖长审核的最近窗口。
STREAM_BUFFER_CAP = 2000


class EventChannel:
    """带 seq 与回放能力的事件通道（替代 asyncio.Queue 的会话事件总线）

    兼容性：提供异步 put(event)，签名与 asyncio.Queue.put 一致，生产端代码
    无需改动；消费端不再使用 get()，改用 events_after/wait_for_more 游标接口。
    """

    def __init__(self, cap: int = STREAM_BUFFER_CAP):
        self._log: List[Tuple[int, Dict]] = []
        self._seq = 0
        self._cap = cap
        self._cond = asyncio.Condition()

    @property
    def last_seq(self) -> int:
        """已分配的最大事件序号（从 1 开始，0 表示尚无事件）"""
        return self._seq

    @property
    def buffered(self) -> int:
        """当前日志中留存的事件条数（受 cap 截断影响）"""
        return len(self._log)

    async def put(self, event: Dict) -> int:
        """记录一条事件并唤醒所有等待的消费者；返回分配的 seq"""
        async with self._cond:
            self._seq += 1
            self._log.append((self._seq, event))
            if len(self._log) > self._cap:
                del self._log[: len(self._log) - self._cap]
            self._cond.notify_all()
            return self._seq

    def events_after(self, cursor: int) -> List[Tuple[int, Dict]]:
        """返回日志中 seq > cursor 的全部事件（ oldest-first；无则空列表）"""
        if not self._log:
            return []
        return [item for item in self._log if item[0] > cursor]

    def oldest_seq(self) -> Optional[int]:
        """日志中最旧事件的 seq（回放可达的最早位置；空日志返回 None）"""
        return self._log[0][0] if self._log else None

    async def wait_for_more(self, cursor: int, timeout: float) -> bool:
        """等待 seq 超过 cursor 的新事件。

        Returns:
            True  — 有新事件（调用方随后 events_after(cursor) 取增量）
            False — 超时（调用方发心跳保活）
        """
        async with self._cond:
            if self._seq > cursor:
                return True
            try:
                await asyncio.wait_for(
                    self._cond.wait_for(lambda: self._seq > cursor), timeout
                )
                return True
            except asyncio.TimeoutError:
                return False
