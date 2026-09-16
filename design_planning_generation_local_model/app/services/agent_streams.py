"""后台 Agent 生成流管理器 — 将 Agent 执行与 SSE 连接解耦。

背景问题：
    原实现中 SSE 端点（/messages、/resume、/auto-generate）直接消费
    stream_agent_events() 的异步生成器，浏览器断开连接（切换聊天任务、
    刷新页面、abort）会导致 Starlette 取消响应生成器，进而中断正在执行的
    LangGraph 生成过程。

方案：
    - 每次发起生成时，为该项目创建一个后台 asyncio Task 执行原有事件源，
      事件逐条写入带自增序号（seq）的内存缓冲区；
    - SSE 端点只做「订阅转发」：客户端断开仅结束本次订阅，后台生成继续
      执行到完成，状态照常通过 AsyncSqliteSaver 检查点持久化；
    - 用户切回该聊天任务时，前端通过 GET /stream/status 查询状态，
      GET /stream?from_seq=N 重连：先回放缓冲区事件，再继续实时接收；
    - 「撤回消息」「删除任务」等确实需要中断的场景，通过 cancel_stream()
      显式取消后台任务。

注意：本模块为纯内存实现（进程级），服务重启后进行中的生成无法恢复，
与改造前行为一致；已完成的生成结果始终持久化在 checkpoint 数据库中。
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Callable, Dict, Optional

# 单条流最多缓冲的事件数（超出后淘汰最旧事件，重连回放从最早保留的事件开始）
MAX_BUFFER_EVENTS = 20000
# 已结束流的记录与缓冲保留时长（秒）：便于 shortly-after 切回时查询状态，过期清理
FINISHED_TTL_SECONDS = 600


class ProjectStream:
    """单个项目的后台生成事件流。

    生命周期：start_stream() 创建 → 后台 task 执行 run() 持续 append 事件
    → 事件源结束/异常/被取消时 _finish() 置终态并向订阅者推送结束哨兵。
    """

    def __init__(self, project_id: str, kind: str, meta: Optional[dict] = None):
        self.project_id = project_id
        self.kind = kind                # message | resume | auto-generate
        # meta: 供前端重连时恢复现场（history_count=本轮生成前的历史消息数,
        # user_message=本轮用户消息文本，用于重连时补渲染用户气泡）
        self.meta: dict = dict(meta or {})
        self.status = "running"         # running | done | error | cancelled
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self._events: list = []         # [(seq, event_dict), ...]
        self._next_seq = 0
        self._base_seq = 0              # 缓冲区淘汰后 _events[0] 对应的 seq
        self._subscribers: set = set()  # set[asyncio.Queue]
        self.task: Optional[asyncio.Task] = None

    @property
    def next_seq(self) -> int:
        return self._next_seq

    @property
    def active(self) -> bool:
        return self.status == "running"

    def append(self, event: dict) -> None:
        """写入一条事件：进缓冲区（带 seq）并广播给所有实时订阅者。"""
        seq = self._next_seq
        self._next_seq += 1
        self._events.append((seq, event))
        # 缓冲区超限时淘汰最旧事件（重连回放退化为从最早保留的事件开始）
        if len(self._events) > MAX_BUFFER_EVENTS:
            overflow = len(self._events) - MAX_BUFFER_EVENTS
            del self._events[:overflow]
            self._base_seq = self._events[0][0] if self._events else seq + 1
        for q in list(self._subscribers):
            q.put_nowait((seq, event))

    def _finish(self, status: str) -> None:
        if self.status != "running":
            return
        self.status = status
        self.finished_at = time.time()
        # 向所有订阅者推送结束哨兵，使订阅端 SSE 正常收尾
        for q in list(self._subscribers):
            q.put_nowait(None)

    async def run(self, source_factory: Callable[[], AsyncIterator[dict]]) -> None:
        """后台执行事件源直到结束。与任何 HTTP 连接的生命周期无关。"""
        try:
            async for event in source_factory():
                self.append(event)
            self._finish("done")
        except asyncio.CancelledError:
            # 显式取消（撤回消息/删除任务）：通知订阅者后照常传播取消
            self.append({"type": "cancelled", "message": "本次生成已被取消"})
            self._finish("cancelled")
            raise
        except Exception as e:  # noqa: BLE001
            self.append({"type": "error", "message": f"后台生成异常: {type(e).__name__}: {e}"})
            self._finish("error")

    def snapshot(self, from_seq: int = 0) -> tuple:
        """返回 (缓冲区中 seq >= from_seq 的事件列表, 快照时刻的 next_seq)。

        调用方订阅队列需在调用本方法之前注册（同一事件循环 tick 内完成，
        中间无 await），配合 last_seq 去重可保证不丢事件、不重复。
        """
        start = max(from_seq, self._base_seq)
        events = [ev for seq, ev in self._events if seq >= start]
        return events, self._next_seq

    def add_subscriber(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        # 流已结束时直接放入哨兵，避免订阅者永久等待
        if not self.active:
            q.put_nowait(None)
        return q

    def remove_subscriber(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)


# project_id → ProjectStream（每个项目仅保留最近一次流）
_streams: Dict[str, ProjectStream] = {}


def _cleanup_expired() -> None:
    now = time.time()
    for pid in list(_streams.keys()):
        s = _streams[pid]
        if not s.active and s.finished_at and now - s.finished_at > FINISHED_TTL_SECONDS:
            del _streams[pid]


def get_stream(project_id: str) -> Optional[ProjectStream]:
    """获取项目最近一次流（可能已结束，缓冲区未过期时仍可回放）。"""
    return _streams.get(project_id)


def get_active_stream(project_id: str) -> Optional[ProjectStream]:
    """获取项目进行中的流（无则 None）。"""
    s = _streams.get(project_id)
    return s if s and s.active else None


def start_stream(
    project_id: str,
    kind: str,
    source_factory: Callable[[], AsyncIterator[dict]],
    meta: Optional[dict] = None,
) -> ProjectStream:
    """启动一个后台生成流并立即返回（不等待执行完成）。

    Args:
        project_id: 项目/线程 ID
        kind: 流类型（message | resume | auto-generate）
        source_factory: 无参可调用，返回事件 dict 的异步生成器
            （如 lambda: stream_agent_events(...)）。在后台 task 中调用。
        meta: 附加元数据（history_count / user_message），经 status 接口透出

    Raises:
        RuntimeError: 该项目已有进行中的生成流
    """
    _cleanup_expired()
    if get_active_stream(project_id) is not None:
        raise RuntimeError("该项目已有正在进行的生成任务")
    stream = ProjectStream(project_id, kind, meta)
    _streams[project_id] = stream
    stream.task = asyncio.create_task(stream.run(source_factory))
    return stream


async def subscribe_stream(stream: ProjectStream, from_seq: int = 0) -> AsyncIterator[dict]:
    """订阅事件流：先回放缓冲区中 seq >= from_seq 的事件，再实时接收直至流结束。

    客户端断开时调用方（SSE 响应生成器）被取消，本生成器在 finally 中
    清理订阅即可，后台生成任务不受影响。
    """
    q = stream.add_subscriber()
    try:
        # 注册订阅与快照在同一同步代码块内完成，其间无 await，不会丢事件；
        # 与快照重叠的实时事件通过 last_seq 去重
        events, next_seq_at_snapshot = stream.snapshot(from_seq)
        last_seq = next_seq_at_snapshot - 1
        for ev in events:
            yield ev
        while True:
            item = await q.get()
            if item is None:          # 流结束哨兵
                return
            seq, ev = item
            if seq > last_seq:        # 过滤与回放部分重叠的事件
                last_seq = seq
                yield ev
    finally:
        stream.remove_subscriber(q)


async def cancel_stream(project_id: str) -> bool:
    """取消项目进行中的后台生成任务（撤回消息/删除任务时使用）。

    Returns:
        True 表示确实取消了一个进行中的流；False 表示无进行中的流。
    """
    s = get_active_stream(project_id)
    if s is None or s.task is None:
        return False
    s.task.cancel()
    try:
        # 等待任务真正结束（asyncio.wait 不会因任务被取消而抛异常）
        await asyncio.wait([s.task], timeout=5.0)
    except Exception:  # noqa: BLE001
        pass
    finally:
        # 兜底置终态（幂等）：任务若在首次运行前即被取消，run() 的
        # CancelledError 分支不会执行，状态会停留在 running 并阻塞后续生成
        s._finish("cancelled")
    return True


def get_status(project_id: str) -> dict:
    """项目后台生成流状态（供前端页面加载/切回时决定是否重连续播）。"""
    s = _streams.get(project_id)
    if s is None:
        return {"exists": False, "active": False}
    return {
        "exists": True,
        "active": s.active,
        "kind": s.kind,
        "status": s.status,
        "seq": s.next_seq,
        "started_at": s.started_at,
        "finished_at": s.finished_at,
        "history_count": s.meta.get("history_count", 0),
        "user_message": s.meta.get("user_message", ""),
    }
