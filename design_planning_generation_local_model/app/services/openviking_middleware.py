"""
OpenVikingResilientMiddleware - 静默降级版 OpenVikingContextMiddleware

Phase 0 验证发现 OpenVikingContextMiddleware.awrap_model_call 在 assemble 失败时
（OpenViking 服务器崩溃/不可达）异常会传播到 Agent，中断运行。

本子类重写 awrap_model_call / aafter_agent，捕获 OpenViking 相关异常降级为日志，
不传播到 Agent。符合项目"静默降级"设计原则：OpenViking 不可用时不影响现有功能。
"""
import logging

from langchain_openviking.middleware import OpenVikingContextMiddleware

logger = logging.getLogger(__name__)


class OpenVikingResilientMiddleware(OpenVikingContextMiddleware):
    """静默降级版 OpenVikingContextMiddleware。

    与父类行为一致，但在 OpenViking 调用失败时不中断 Agent：
    - awrap_model_call: assemble 或 handler 失败时，降级为无 context 调用 handler
    - aafter_agent: capture 失败时仅记日志，跳过本次 capture
    """

    async def awrap_model_call(self, request, handler):
        """异步注入 OpenViking context，失败时降级为直接调用 handler。"""
        try:
            return await super().awrap_model_call(request, handler)
        except Exception as e:
            # CancelledError 是 BaseException，不会被 except Exception 捕获，可安全传播
            logger.warning(
                "[OpenViking] awrap_model_call failed (degraded): %s. "
                "Retrying without OpenViking context.",
                e,
            )
            # 降级：用原始 request（无 context 注入）重试 handler
            return await handler(request)

    async def aafter_agent(self, state, runtime):
        """异步捕获消息，失败时降级为日志（不传播异常）。"""
        try:
            return await super().aafter_agent(state, runtime)
        except Exception as e:
            logger.warning(
                "[OpenViking] aafter_agent capture failed (degraded): %s. "
                "Session capture skipped.",
                e,
            )
            return None
