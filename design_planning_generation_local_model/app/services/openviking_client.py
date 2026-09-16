"""
OpenVikingService - OpenViking 集成封装（Phase 3: capture + recall）

设计原则（与项目"静默降级"一致）：
- OPENVIKING_ENABLED=false 时不初始化，所有方法返回空/无操作
- OpenViking 服务不可用时不影响现有 Agent 功能
- 所有 OpenViking 调用包在 try/except 中，异常仅记日志

Phase 3 范围（capture + recall）：
- ✅ capture：每轮 agent 对话后捕获消息到 OpenViking
- ✅ capture 工具：viking_store / viking_add_resource（LLM 可主动调用）
- ✅ recall 工具：viking_find / viking_search / viking_read（LLM 可主动检索记忆）
- ✅ 自动上下文注入：每轮对话前自动检索相关历史记忆，注入 system prompt

集成方式：手动集成（非 middleware）
- 原因：StateGraph.compile() 不支持 middleware 参数（LangGraph 1.2.5），
  OpenVikingContextMiddleware 是 langchain.agents.create_agent() 工厂的概念，
  不适用于项目自定义 StateGraph。
- 做法：在 agent_engine._agent_node 中注入记忆上下文 + 末尾 capture_messages()。
"""
import os
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class OpenVikingService:
    """OpenViking 集成服务封装（单例，Phase 1 capture-only）。"""

    def __init__(self):
        self.url = os.getenv("OPENVIKING_URL", "http://localhost:1933")
        self.api_key = os.getenv("OPENVIKING_API_KEY", "")
        self.account = os.getenv("OPENVIKING_ACCOUNT", "my-team")
        self.user = os.getenv("OPENVIKING_USER", "wangzichen")
        self.actor_peer_id = os.getenv("OPENVIKING_ACTOR_PEER_ID", "design-plan-agent")
        self.enabled = os.getenv("OPENVIKING_ENABLED", "false").lower() == "true"

        self._recorder = None
        self._capture_tools: list = []
        # 每个 session 已捕获的消息数（增量捕获，避免重复写入）
        self._session_captured_count: dict[str, int] = {}

    async def initialize(self) -> bool:
        """初始化 OpenViking 连接，返回是否成功（失败时静默降级）。"""
        if not self.enabled:
            logger.info("[OpenViking] Disabled by OPENVIKING_ENABLED=false")
            return False

        try:
            from langchain_openviking.recording import OpenVikingSessionRecorder
            from langchain_openviking.tools import create_openviking_tools

            # 初始化 recorder（capture 用）
            self._recorder = OpenVikingSessionRecorder(
                url=self.url,
                api_key=self.api_key,
                account=self.account,
                user=self.user,
                actor_peer_id=self.actor_peer_id,
                auto_initialize=True,
            )

            # 冒烟测试 + 获取 capture + recall 工具（Phase 3: capture + recall）
            all_tools = create_openviking_tools(
                url=self.url,
                api_key=self.api_key,
                account=self.account,
                user=self.user,
                actor_peer_id=self.actor_peer_id,
                auto_initialize=True,
            )
            self._capture_tools = [
                t for t in all_tools
                if t.name in (
                    "viking_store", "viking_add_resource",   # capture
                    "viking_find", "viking_search", "viking_read",  # recall
                )
            ]

            logger.info(
                "[OpenViking] Initialized: %d tools (capture + recall), recorder ready",
                len(self._capture_tools),
            )
            return True

        except Exception as e:
            logger.warning("[OpenViking] Initialization failed (non-fatal): %s", e)
            self._recorder = None
            self._capture_tools = []
            return False

    def is_available(self) -> bool:
        """OpenViking capture 是否可用。"""
        return self._recorder is not None

    def get_capture_tools(self) -> list:
        """返回 capture + recall 工具列表（Phase 3: capture + recall）。

        返回 viking_store / viking_add_resource（capture）
        + viking_find / viking_search / viking_read（recall）。
        """
        return list(self._capture_tools)

    async def search_memories(self, query: str, limit: int = 5,
                              score_threshold: float = 0.3) -> list[dict]:
        """语义搜索 OpenViking 中的相关记忆（静默降级）。

        用于自动上下文注入：每轮对话前，用当前用户消息作为查询，
        从 OpenViking 中检索跨会话的相关历史记忆，注入 system prompt。

        使用 stateless find（跨会话搜索），而非 session-aware search，
        因为我们需要从所有历史会话中召回，而非仅当前会话。

        Args:
            query: 搜索查询（通常是用户的最新消息）
            limit: 返回结果数上限
            score_threshold: 最低相关性分数阈值

        Returns:
            记忆列表，每项含 uri, score, abstract, overview 等字段。
            失败或不可用时返回空列表。
        """
        if not self._recorder or not query or not query.strip():
            return []

        try:
            client = await self._recorder.get_async_client()
            result = await client.find(
                query=query.strip(),
                limit=limit,
                score_threshold=score_threshold,
            )
            memories = result.get("memories", [])
            if memories:
                logger.debug(
                    "[OpenViking] search_memories found %d results for query: %s",
                    len(memories), query[:80],
                )
            return memories
        except Exception as e:
            logger.warning("[OpenViking] search_memories failed (degraded): %s", e)
            return []

    async def capture_messages(self, messages: list, session_id: str) -> int:
        """增量捕获消息到 OpenViking（静默降级）。

        在 agent_engine._agent_node 末尾调用，捕获当前对话消息。
        使用 _session_captured_count 跟踪每个 session 的已捕获量，
        只写入增量消息，避免重复捕获。

        Args:
            messages: 当前 state 中的完整消息列表
            session_id: 会话 ID（LangGraph thread_id）

        Returns:
            本次新捕获的消息条数（未捕获/无新增/失败时为 0）
        """
        if not self._recorder or not session_id:
            return 0

        try:
            prev_count = self._session_captured_count.get(session_id, 0)
            total = len(messages)
            if total <= prev_count:
                # 无新增消息（如 HITL resume 未产生新回复）
                return 0

            new_messages = messages[prev_count:]
            if not new_messages:
                return 0

            await self._capture_messages_single(session_id, new_messages)
            self._session_captured_count[session_id] = total
            logger.debug(
                "[OpenViking] Captured %d messages for session %s (total: %d)",
                len(new_messages),
                session_id,
                total,
            )
            return len(new_messages)
        except Exception as e:
            # 静默降级：capture 失败不影响 Agent 运行
            logger.warning("[OpenViking] capture_messages failed (degraded): %s", e)
            return 0

    async def _capture_messages_single(self, session_id: str, messages: list) -> None:
        """逐条写入消息（绕过 /messages/batch 的客户端-服务器版本不匹配）。

        背景：langchain-openviking 0.1.0 依赖 openviking-sdk 0.1.7，其
        ``batch_add_messages`` 调用 ``POST /api/v1/sessions/{id}/messages/batch``；
        但当前 OpenViking 服务器（openapi 0.1.0）只提供单条接口
        ``POST /api/v1/sessions/{id}/messages``，导致 capture 返回 404。

        因此这里复用 recorder 的异步 client + langchain 消息序列化，逐条调用
        ``add_message``，避免 batch 接口的版本不匹配。若服务器后续升级支持
        ``/messages/batch``，可将本方法改回 ``await self._recorder.arecord(...)``。
        """
        from langchain_openviking.messages import (
            is_recordable_langchain_message,
            langchain_message_to_openviking,
        )

        client = await self._recorder.get_async_client()
        wrote_any = False
        for message in messages:
            if not is_recordable_langchain_message(message):
                continue
            for payload in langchain_message_to_openviking(message):
                await client.add_message(
                    session_id=session_id,
                    role=payload.get("role"),
                    content=payload.get("content"),
                    parts=payload.get("parts"),
                )
                wrote_any = True

        # 关键：add_message 只是把消息写入「活跃 session」，并不生成可检索的记忆。
        # 必须调用 commit_session 才会触发 OpenViking 固化记忆（LLM 提取
        # memory_write/memory_edit，写入 viking://user/{user}/memories/），
        # 之后 find/search（即 recall 的 search_memories）才能检索到。
        # commit 是异步的（返回 accepted + task_id，后台完成），不阻塞本轮对话。
        if wrote_any:
            await client.commit_session(session_id)

    async def close(self) -> None:
        """清理资源（应用关闭时调用）。"""
        if self._recorder is not None:
            try:
                await self._recorder.aclose()
            except Exception as e:
                logger.warning("[OpenViking] recorder close failed (non-fatal): %s", e)
            self._recorder = None
        self._capture_tools = []
        self._session_captured_count.clear()
        logger.info("[OpenViking] Service closed")


# ── 模块级单例 ──

_service: Optional[OpenVikingService] = None


async def init_openviking() -> bool:
    """初始化 OpenViking 服务（应用启动时调用）。

    Returns:
        True if OpenViking 可用，False if 降级（不可用但不影响现有功能）
    """
    global _service
    _service = OpenVikingService()
    ok = await _service.initialize()
    if ok:
        print("[openviking] Service initialized successfully")
    else:
        print("[openviking] Service not available (non-fatal, agent will work without it)")
    return ok


def get_openviking_service() -> Optional[OpenVikingService]:
    """获取 OpenViking 服务单例（未初始化时返回 None）。"""
    return _service


async def close_openviking() -> None:
    """关闭 OpenViking 服务（应用关闭时调用）。"""
    global _service
    if _service is not None:
        await _service.close()
        _service = None
