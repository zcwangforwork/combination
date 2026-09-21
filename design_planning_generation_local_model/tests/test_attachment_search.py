"""附件段落级精准检索测试：分词 / 块级打分 / 混合检索核心 / 工具输出

覆盖：
1. _tokenize_query：中文分词 + 停用词过滤（旧空格分词的致命缺陷修复验证）
2. _kw_block_score：术语覆盖打分 + 短语加分
3. _search_attachment_core：关键词路命中（mock 向量降级）+ filename 过滤 + 位置信息 + 精排
4. search_attachment 工具：JSON 输出含 section_path/block_id
"""
import asyncio
import json
from unittest.mock import patch

from app.services import agent_tools


def _mk_att(fid, name, text):
    return {"file_id": fid, "filename": name, "full_text": text, "char_count": len(text)}


def test_tokenize_query_chinese():
    terms = agent_tools._tokenize_query("输注精度的技术要求是什么")
    assert "输注" in terms or "精度" in terms
    assert "输注精度" in terms or ("输注" in terms and "精度" in terms)
    # 停用词被过滤
    assert "的" not in terms and "什么" not in terms
    # 单字字母数字保留
    terms2 = agent_tools._tokenize_query("IPX8 防水等级")
    assert "IPX8" in terms2


def test_kw_block_score_coverage():
    # 中文查询分词后：段落含部分术语即命中（旧空格分词整句匹配会 miss）
    terms = agent_tools._tokenize_query("输注精度的要求")
    para = "基础率输注精度为 0.05U/h，误差不超过 ±5%。"
    s = agent_tools._kw_block_score(para, terms, "输注精度的要求")
    assert s > 0, "术语级命中应大于 0"
    # 完全无关段落 → 0
    assert agent_tools._kw_block_score("皮肤生物相容性评价。", terms, "输注精度") == 0.0
    # 完整短语命中加分
    s_phrase = agent_tools._kw_block_score("输注精度要求如下：0.05U/h。", terms, "输注精度")
    assert s_phrase > 0


def test_search_core_keyword_path_and_location():
    atts = [_mk_att("f1", "技术要求.docx",
                    "# 3 性能指标\n\n## 3.2 输注精度\n\n基础率输注精度为 0.05U/h，误差不超过 ±5%。\n\n"
                    "## 3.3 报警\n\n低电量报警阈值 20%。")]
    agent_tools.set_current_attachments(atts)
    agent_tools._attachment_blocks_cache.clear()
    agent_tools._attachment_vec_cache.clear()

    class FakeReranker:
        def rerank(self, query, chunks, top_k=5, **kw):
            chunks = sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)
            for i, c in enumerate(chunks[:top_k]):
                c["rerank_score"] = 1.0 - i * 0.1
            return chunks[:top_k]

    async def _run():
        with patch.object(agent_tools, "_get_block_vectors",
                          new=lambda *a, **k: asyncio.sleep(0, result=None)), \
             patch("app.services.rag.reranker.Reranker", FakeReranker):
            return await agent_tools._search_attachment_core("输注精度 要求", top_k=5)

    results = asyncio.run(_run())
    assert results, "关键词路应命中"
    top = results[0]
    assert "0.05U/h" in top["content"]
    assert top["source"] == "技术要求.docx"
    assert "3.2 输注精度" in top["section_path"], "位置信息缺失"
    assert top["block_id"].startswith("att-f1-b")


def test_search_core_filename_filter():
    atts = [
        _mk_att("f1", "技术要求.docx", "# 3 性能\n\n输注精度 0.05U/h。"),
        _mk_att("f2", "风险计划.docx", "# 5 风险\n\n输注精度相关风险控制措施。"),
    ]
    agent_tools.set_current_attachments(atts)
    agent_tools._attachment_blocks_cache.clear()

    class FakeReranker:
        def rerank(self, query, chunks, top_k=5, **kw):
            return chunks[:top_k]

    async def _run():
        with patch.object(agent_tools, "_get_block_vectors",
                          new=lambda *a, **k: asyncio.sleep(0, result=None)), \
             patch("app.services.rag.reranker.Reranker", FakeReranker):
            return await agent_tools._search_attachment_core("输注精度", top_k=5, filename="风险计划")

    results = asyncio.run(_run())
    assert results
    assert all(r["source"] == "风险计划.docx" for r in results), "filename 过滤失效"


def test_search_attachment_tool_json_shape():
    atts = [_mk_att("f1", "技术要求.docx", "# 3 性能\n\n## 3.2 输注精度\n\n输注精度 0.05U/h。")]
    agent_tools.set_current_attachments(atts)
    agent_tools._attachment_blocks_cache.clear()

    class FakeReranker:
        def rerank(self, query, chunks, top_k=5, **kw):
            for c in chunks:
                c["rerank_score"] = c.get("score", 0)
            return chunks[:top_k]

    async def _run():
        with patch.object(agent_tools, "_get_block_vectors",
                          new=lambda *a, **k: asyncio.sleep(0, result=None)), \
             patch("app.services.rag.reranker.Reranker", FakeReranker):
            raw = await agent_tools.search_attachment.ainvoke(
                {"query": "输注精度", "top_k": 3})
            return json.loads(raw)

    data = asyncio.run(_run())
    assert data["status"] == "ok"
    assert data["source"] == "hybrid_kw_vec_rerank"
    r0 = data["results"][0]
    assert "section_path" in r0 and "block_id" in r0 and "content" in r0
