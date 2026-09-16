"""字数收敛功能测试：_split_full_markdown / _reassemble_full_markdown / _condense_document_to_limit

覆盖：
1. 完整 markdown 拆分与重组 round-trip（保留 # / ## / ### 结构）
2. 字数统计口径 _count_chinese_chars（去 markdown 标记与空白）
3. _condense_document_to_limit：已达标 → 不动、直接返回
4. _condense_document_to_limit：超限 + 每轮减半 → 迭代收敛、无硬截断
5. _condense_document_to_limit：精简无进展 → 提前停止（避免死循环）
6. _condense_document_to_limit：迭代轮数上限被遵守
"""
import pytest
import asyncio
from unittest.mock import patch


def _make_doc(body_chars: int, sections: int = 2) -> str:
    """构造一份每章含 2 个小节的测试文档，正文用中文填充指定字符量。"""
    import math
    per_sub = max(body_chars // (sections * 2), 1)
    chunk = "内容" * (per_sub // 2 + 1)
    parts = []
    for s in range(1, sections + 1):
        parts.append(f"# 第{s}章\n\n## 第{s}章 标题\n")
        for k in range(1, 3):
            parts.append(f"\n### 第{s}章 第{k}节\n\n{chunk}\n")
    return "\n".join(parts)


def test_split_reassemble_roundtrip():
    """拆分 → 重组应保留 # / ## / ### 结构，小节数量一致"""
    from app.services.agent_tools import _split_full_markdown, _reassemble_full_markdown

    doc = "# 概述\n\n## 概述标题\n\n### 1.1 目的\n\n正文A\n\n### 1.2 范围\n\n正文B\n\n# 风险\n\n## 风险标题\n\n### 2.1 分析\n\n正文C\n"
    sections = _split_full_markdown(doc)
    assert [s["name"] for s in sections] == ["概述", "风险"]
    bodies = [sub["body"] for s in sections for sub in s["subsections"]]
    assert len(bodies) == 3

    rebuilt = _reassemble_full_markdown(sections, bodies)
    assert "# 概述" in rebuilt and "# 风险" in rebuilt
    assert "### 1.1 目的" in rebuilt and "### 2.1 分析" in rebuilt
    assert "正文A" in rebuilt and "正文C" in rebuilt


def test_count_chinese_chars():
    """字数口径：去 markdown 标记与空白，统计中英文字符"""
    from app.services.agent_tools import _count_chinese_chars
    assert _count_chinese_chars("贴敷式胰岛素泵") == 7
    assert _count_chinese_chars("## 标题 ###\n\n正文 **加粗**") == len("标题正文加粗")
    assert _count_chinese_chars("") == 0


def test_condense_under_limit_noop():
    """已达标：不调用精简，直接返回原文，converged=True"""
    from app.services.agent_tools import _condense_document_to_limit

    doc = _make_doc(body_chars=200)
    async def _run():
        md, stats = await _condense_document_to_limit(doc, doc_label="测试", target_chars=10000, max_iterations=3)
        return md, stats
    md, stats = asyncio.run(_run())
    assert md == doc
    assert stats["converged"] is True
    assert stats["iterations"] == 0
    assert stats["final_chars"] <= 10000


def test_condense_converges():
    """超限 + 每轮减半：应迭代并收敛（final < original，轮数在 1..max_iterations 内）"""
    from app.services.agent_tools import _condense_document_to_limit

    doc = _make_doc(body_chars=40000)  # 约 40000 字，远超 10000

    async def _halve(sub_title, sub_body, target_chars, chapter_name, doc_label):
        half = sub_body[: max(len(sub_body) // 2, 1)]
        return (sub_title, half, {"status": "ok", "orig_chars": len(sub_body), "new_chars": len(half)})

    async def _run():
        with patch("app.services.agent_tools._summarize_one_subsection", new=_halve):
            md, stats = await _condense_document_to_limit(doc, doc_label="测试", target_chars=10000, max_iterations=3)
            return md, stats
    md, stats = asyncio.run(_run())
    assert stats["final_chars"] < stats["original_chars"]
    assert 1 <= stats["iterations"] <= 3


def test_condense_no_progress_stops():
    """精简无进展：应提前停止（iterations==1），不空转，保留原文"""
    from app.services.agent_tools import _condense_document_to_limit

    doc = _make_doc(body_chars=20000)

    async def _same(sub_title, sub_body, target_chars, chapter_name, doc_label):
        return (sub_title, sub_body, {"status": "ok", "orig_chars": len(sub_body), "new_chars": len(sub_body)})

    async def _run():
        with patch("app.services.agent_tools._summarize_one_subsection", new=_same):
            md, stats = await _condense_document_to_limit(doc, doc_label="测试", target_chars=10000, max_iterations=3)
            return md, stats
    md, stats = asyncio.run(_run())
    assert stats["iterations"] == 1
    assert stats["converged"] is False
    assert stats["final_chars"] == stats["original_chars"]


def test_condense_iteration_cap():
    """精简每次只减一点：轮数被 max_iterations 封顶，不死循环"""
    from app.services.agent_tools import _condense_document_to_limit

    doc = _make_doc(body_chars=20000)

    async def _minus_one(sub_title, sub_body, target_chars, chapter_name, doc_label):
        return (sub_title, sub_body[:-1], {"status": "ok", "orig_chars": len(sub_body), "new_chars": len(sub_body) - 1})

    async def _run():
        with patch("app.services.agent_tools._summarize_one_subsection", new=_minus_one):
            md, stats = await _condense_document_to_limit(doc, doc_label="测试", target_chars=10000, max_iterations=3)
            return md, stats
    md, stats = asyncio.run(_run())
    assert stats["iterations"] == 3
    assert stats["final_chars"] < stats["original_chars"]
