"""法规引用剥离测试：_strip_regulation_subsection / _strip_regulations_from_document

覆盖：
1. 剥离函数：LLM 输出去除法规引用 + 标题行去重
2. LLM 失败/超时/空返回 → 静默降级保留原文
3. 整篇剥离：拆章分节并行处理 + 结构重组
4. 开关 STRIP_REGULATIONS_ON_EXPORT=false 时函数不调用
"""
import asyncio
from unittest.mock import patch


def test_strip_subsection_removes_regulations():
    from app.services import agent_tools

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value="### 性能要求\n\n输注精度为 0.05U/h，误差不超过 ±5%。"):
            return await agent_tools._strip_regulation_subsection(
                "### 性能要求",
                "依据 GB 9706.224 第4章规定，输注精度为 0.05U/h。",
            )

    body = asyncio.run(_run())
    assert "GB" not in body and "9706" not in body
    assert "0.05U/h" in body
    assert "### 性能要求" not in body  # 标题由重组层拼接，剥离响应中的标题行应被去掉


def test_strip_subsection_failure_keeps_original():
    from app.services import agent_tools

    original = "依据 ISO 13485 §7.3.2 的内容原文"

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=RuntimeError("boom")):
            return await agent_tools._strip_regulation_subsection("### 标题", original)

    assert asyncio.run(_run()) == original


def test_strip_subsection_empty_response_keeps_original():
    from app.services import agent_tools

    original = "原文内容保持不变"

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw", return_value=""):
            return await agent_tools._strip_regulation_subsection("### 标题", original)

    assert asyncio.run(_run()) == original


def test_strip_document_parallel_and_reassemble():
    from app.services import agent_tools

    md = (
        "# 第1章 概述\n\n## 第1章 概述\n\n### 1.1 目的\n\n"
        "依据 ISO 13485，建立质量管理体系。\n\n"
        "# 第2章 要求\n\n## 第2章 要求\n\n### 2.1 性能\n\n"
        "按照 GB 9706.224 要求，精度 0.05U/h。\n\n"
        "### 2.2 检验\n\n依据 YY 9706.102 进行 EMC 检验。\n"
    )

    calls = []

    def fake_llm(system_prompt="", user_prompt="", **kw):
        calls.append(user_prompt)
        # 模拟剥离：去掉含标准号开头的句子
        lines = []
        for ln in user_prompt.split("\n"):
            if any(k in ln for k in ("ISO", "GB ", "YY ", "依据", "按照")) and "章" not in ln:
                continue
            lines.append(ln)
        return "\n".join(lines).strip()

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw", side_effect=fake_llm):
            return await agent_tools._strip_regulations_from_document(md)

    stripped, n = asyncio.run(_run())
    assert n == 3  # 3 个小节并行处理
    assert len(calls) == 3
    # 结构保留：章节标题与小节标题完整
    assert "# 第1章 概述" in stripped and "# 第2章 要求" in stripped
    assert "### 1.1 目的" in stripped and "### 2.1 性能" in stripped and "### 2.2 检验" in stripped
    # 法规引用被剥离
    assert "ISO 13485" not in stripped and "GB 9706" not in stripped and "YY 9706" not in stripped


def test_strip_enabled_flag_env(monkeypatch=None):
    import importlib
    import os
    from app.services import agent_tools as at

    # 默认开启
    assert at._STRIP_REGULATIONS_ENABLED is True
    # env 关闭
    os.environ["STRIP_REGULATIONS_ON_EXPORT"] = "false"
    try:
        importlib.reload(at)
        assert at._STRIP_REGULATIONS_ENABLED is False
    finally:
        os.environ.pop("STRIP_REGULATIONS_ON_EXPORT", None)
        importlib.reload(at)  # 恢复默认，避免污染其他测试
    assert at._STRIP_REGULATIONS_ENABLED is True
