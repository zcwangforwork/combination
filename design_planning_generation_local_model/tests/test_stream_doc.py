"""文档流式输出测试：_call_minimax_api_raw_stream / _stream_llm_to_sink / _interleaved_agent_stream

覆盖：
1. _call_minimax_api_raw_stream：逐 chunk 解析 thinking/content 字段
2. _stream_llm_to_sink：有 sink 时推 chunk 到队列 + 累积正文
3. _stream_llm_to_sink：无 sink 时退化为阻塞调用
4. _interleaved_agent_stream：graph 事件与 doc chunk 交织产出、正常终止
"""
import asyncio
import json
from unittest.mock import patch

from langchain_core.messages import HumanMessage


# ── minimax 流式变体 ──

class _FakeResponse:
    """伪造 requests.post(stream=True) 返回的响应对象。"""

    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        for line in self._lines:
            yield line


def test_call_minimax_stream_parses_thinking_and_content():
    """流式响应按顺序 yield (thinking/content) 元组。"""
    from app.services.minimax import _call_minimax_api_raw_stream

    lines = [
        '{"message":{"thinking":"思考1"},"done":false}',
        '{"message":{"content":"正文A"},"done":false}',
        '{"message":{"content":"正文B"},"done":true}',
    ]
    with patch("app.services.minimax.requests.post", return_value=_FakeResponse(lines)):
        chunks = list(_call_minimax_api_raw_stream(system_prompt="sys", user_prompt="u"))
    assert chunks == [
        ("thinking", "思考1"),
        ("content", "正文A"),
        ("content", "正文B"),
    ]


# ── agent_tools 流式通道 ──

def test_stream_llm_to_sink_always_blocking():
    """前端已下线文档流式输出：工具调用恢复阻塞语义（不推 sink chunk）。"""
    from app.services import agent_tools

    async def _run():
        sink = asyncio.Queue()
        agent_tools.set_stream_sink(sink)
        try:
            with patch("app.services.minimax._call_minimax_api_raw", return_value="阻塞结果") as mock:
                result = await agent_tools._stream_llm_to_sink("sys", "user")
                # 让线程池任务完全结束，确认 sink 始终为空（无 chunk 推送）
                await asyncio.sleep(0.05)
                return result, mock.call_count, sink.empty()
        finally:
            agent_tools.set_stream_sink(None)

    result, calls, sink_empty = asyncio.run(_run())
    assert result == "阻塞结果"
    assert calls == 1
    assert sink_empty is True


def test_stream_llm_to_sink_fallback_no_sink():
    """无 sink 时退化为普通阻塞调用。"""
    from app.services import agent_tools

    async def _run():
        agent_tools.set_stream_sink(None)
        with patch("app.services.minimax._call_minimax_api_raw", return_value="阻塞结果") as mock:
            result = await agent_tools._stream_llm_to_sink("sys", "user")
            return result, mock.call_count

    result, count = asyncio.run(_run())
    assert result == "阻塞结果"
    assert count == 1


# ── agent_engine 交织流 ──

def test_interleaved_agent_stream_yields_events_and_docs():
    """graph 事件与 doc chunk 交织产出，且正常终止。"""
    from app.services.agent_engine import _interleaved_agent_stream

    class FakeAgent:
        def __init__(self, doc_queue):
            self.doc_queue = doc_queue

        async def astream_events(self, agent_input, config=None, version="v2"):
            yield {"event": "on_tool_start", "name": "write_chapter", "data": {"input": {}}}
            # 模拟工具执行期间推入 doc chunk
            await self.doc_queue.put(("thinking", "思"))
            await self.doc_queue.put(("content", "正文"))
            yield {"event": "on_tool_end", "name": "write_chapter", "data": {"output": ""}}

    async def _run():
        doc_queue = asyncio.Queue()
        agent = FakeAgent(doc_queue)
        items = []
        async for item in _interleaved_agent_stream(agent, {}, {}, doc_queue):
            items.append(item)
        return items

    items = asyncio.run(_run())
    kinds = [item[0] for item in items]
    assert kinds.count("event") == 2          # on_tool_start + on_tool_end
    assert kinds.count("doc") == 2            # thinking + content
    # doc chunk 在两次 event 之间产出
    doc_payloads = [item[1] for item in items if item[0] == "doc"]
    assert ("thinking", "思") in doc_payloads
    assert ("content", "正文") in doc_payloads


# ── 主 agent 思维链保留 ──

def test_thinking_chat_openai_preserves_reasoning():
    """_ThinkingChatOpenAI 把 reasoning_content 注入 additional_kwargs，不被 langchain 丢弃。"""
    from langchain_core.messages import AIMessageChunk
    from app.services.agent_engine import _ThinkingChatOpenAI

    llm = _ThinkingChatOpenAI(
        model="qwen3.5:122b",
        base_url="http://localhost:11435/v1",
        api_key="ollama",
    )
    # 模拟 Ollama OpenAI 兼容端点的流式 delta（含 reasoning_content）
    chunk = {"choices": [{"delta": {"reasoning_content": "正在思考", "content": ""}}]}
    gen = llm._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)
    assert gen is not None
    assert gen.message.additional_kwargs.get("reasoning_content") == "正在思考"

    # 无 reasoning_content 时不影响正常 chunk
    chunk2 = {"choices": [{"delta": {"content": "正文"}}]}
    gen2 = llm._convert_chunk_to_generation_chunk(chunk2, AIMessageChunk, None)
    assert gen2 is not None
    assert "reasoning_content" not in (gen2.message.additional_kwargs or {})
    assert gen2.message.content == "正文"


def test_thinking_chat_openai_preserves_reasoning_field():
    """Ollama /v1 端点用 delta.reasoning（字符串）承载思维链，也应被捕获。"""
    from langchain_core.messages import AIMessageChunk
    from app.services.agent_engine import _ThinkingChatOpenAI

    llm = _ThinkingChatOpenAI(
        model="qwen3.5:122b",
        base_url="http://localhost:11435/v1",
        api_key="ollama",
    )
    chunk = {"choices": [{"delta": {"reasoning": "Thinking Process", "content": ""}}]}
    gen = llm._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)
    assert gen is not None
    assert gen.message.additional_kwargs.get("reasoning_content") == "Thinking Process"


def test_leak_filter_granular_flush():
    """_LeakFilter 无换行长句达到阈值应提前冲刷，而非整段憋到结束（流式平滑）。"""
    from app.services.agent_engine import _LeakFilter

    f = _LeakFilter()
    # 超过 _FLUSH_CHARS(20) 的无换行长句：应产出片段
    long_text = "这是一句超过二十个字符的长句子用于测试平滑流式输出效果"
    out = f.feed(long_text)
    assert out, "超过阈值的长句应提前冲刷"
    assert long_text in out
    # 完整行仍正常按行输出
    out2 = f.feed("第二条完整行\n")
    assert any("第二条完整行" in o for o in out2)
    # flush 冲刷残余
    f.feed("残余内容")
    flushed = f.flush()
    assert any("残余内容" in o for o in flushed)
