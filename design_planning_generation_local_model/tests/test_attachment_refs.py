"""附件参考注入测试：_retrieve_attachment_refs / _attachment_refs_block

覆盖：
1. _retrieve_attachment_refs：search_attachment 命中时解析结果；no_match/异常时静默空列表
2. _attachment_refs_block：格式化为「最高优先级」注入块；无结果返回空串
"""
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock


def test_retrieve_attachment_refs_parses_results():
    from app.services import agent_tools

    payload = json.dumps({
        "status": "ok",
        "query": "风险管理",
        "count": 2,
        "results": [
            {"content": "附件条款A", "source": "风险计划.pdf", "score": 0.9},
            {"content": "附件条款B", "source": "风险计划.pdf", "score": 0.7},
        ],
    }, ensure_ascii=False)

    async def _run():
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value=payload)
        with patch.object(agent_tools, "search_attachment", mock_tool):
            return await agent_tools._retrieve_attachment_refs("风险管理", top_k=5)

    results = asyncio.run(_run())
    assert len(results) == 2
    assert results[0]["content"] == "附件条款A"


def test_retrieve_attachment_refs_no_match_returns_empty():
    from app.services import agent_tools

    payload = json.dumps({
        "status": "no_match",
        "message": "未找到相关内容",
        "results": [],
    }, ensure_ascii=False)

    async def _run():
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value=payload)
        with patch.object(agent_tools, "search_attachment", mock_tool):
            return await agent_tools._retrieve_attachment_refs("无关键词匹配", top_k=5)

    assert asyncio.run(_run()) == []


def test_retrieve_attachment_refs_exception_silent():
    from app.services import agent_tools

    async def _run():
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
        with patch.object(agent_tools, "search_attachment", mock_tool):
            return await agent_tools._retrieve_attachment_refs("查询", top_k=5)

    assert asyncio.run(_run()) == []


def test_attachment_refs_block_format():
    from app.services import agent_tools

    payload = json.dumps({
        "status": "ok",
        "results": [
            {"content": "输注精度0.05U/h", "source": "技术要求.docx", "score": 0.85},
        ],
    }, ensure_ascii=False)

    async def _run():
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value=payload)
        with patch.object(agent_tools, "search_attachment", mock_tool):
            return await agent_tools._attachment_refs_block("输注精度", top_k=5, verb="编写")

    block = asyncio.run(_run())
    assert "最高优先级" in block
    assert "输注精度0.05U/h" in block
    assert "技术要求.docx" in block
    assert "[附件1]" in block


def test_attachment_refs_block_empty_on_no_results():
    from app.services import agent_tools

    payload = json.dumps({"status": "no_match", "results": []}, ensure_ascii=False)

    async def _run():
        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value=payload)
        with patch.object(agent_tools, "search_attachment", mock_tool):
            return await agent_tools._attachment_refs_block("查询", top_k=5)

    assert asyncio.run(_run()) == ""
