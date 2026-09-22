"""知识库参考文件工具测试：find_kb_reference_files / add_kb_files_as_attachment

覆盖：
1. find：向量检索按文件聚合排序，返回候选（含摘要/相关度）；空知识库返回 no_kb_files
2. add：读回全文写入旁路（供 after_tools 合并进 attachments）；重复/无内容跳过
3. 提示词：2e/2f 规则（先询问后添加）存在
"""
import asyncio
import json
from unittest.mock import MagicMock, patch

from app.services import agent_tools


class _FakeStore:
    def __init__(self, chunks=None, texts=None, count=None):
        # chunks: [(doc_text, source_file, distance)]
        self._chunks = chunks or []
        self._texts = texts or {}
        self.collection = MagicMock()
        self.collection.count.return_value = count if count is not None else len(self._chunks)
        self.collection.query.side_effect = lambda **kw: self._query()
        self.embedder = MagicMock()
        self.embedder.encode_single.return_value = [0.1, 0.2]

    def __call__(self, collection_name=None, **kwargs):
        # [KB-ISO] 用户隔离改造后 kb_scope 以 (collection_name, persist_directory)
        # 实例化；无上下文时仅共享库一实例，行为与单库等价
        return self

    def get_text_by_source(self, src):
        return self._texts.get(src, "")

    def _query(self, **kw):
        docs = [c[0] for c in self._chunks]
        metas = [{"source_file": c[1]} for c in self._chunks]
        dists = [c[2] for c in self._chunks]
        return {"ids": [[str(i) for i in range(len(docs))]],
                "documents": [docs], "metadatas": [metas], "distances": [dists]}


def test_find_kb_reference_files_aggregates():
    fake = _FakeStore(chunks=[
        ("输注精度 0.05U/h 的要求……", "技术要求.docx", 0.4),
        ("输注精度实测记录。", "技术要求.docx", 0.6),
        ("风险管理措施描述。", "风险计划.docx", 1.2),
        ("生物相容性评价。", "生物评价.docx", 1.6),
    ])

    async def _run():
        with patch("app.services.rag.vector_store.VectorStore", fake):
            raw = await agent_tools.find_kb_reference_files.ainvoke(
                {"doc_type": "design_input", "instruction": "输注精度要求"})
            return json.loads(raw)

    data = asyncio.run(_run())
    assert data["status"] == "ok"
    cands = data["candidates"]
    assert cands[0]["source_file"] == "技术要求.docx", cands
    assert cands[0]["hits"] == 2
    assert cands[0]["score"] > cands[1]["score"]
    assert "输注精度" in cands[0]["sample"]


def test_find_kb_reference_files_empty():
    fake = _FakeStore(count=0)

    async def _run():
        with patch("app.services.rag.vector_store.VectorStore", fake):
            raw = await agent_tools.find_kb_reference_files.ainvoke({"doc_type": "design_input"})
            return json.loads(raw)

    data = asyncio.run(_run())
    assert data["status"] == "no_kb_files" and data["candidates"] == []


def test_add_kb_files_writes_bypass():
    fake = _FakeStore(texts={
        "技术要求.docx": "全文内容。",
        "空文件.docx": "   ",
    })
    agent_tools.set_current_attachments([])
    agent_tools._pending_kb_attachments.pop("files", None)

    async def _run():
        with patch("app.services.rag.vector_store.VectorStore", fake):
            raw = await agent_tools.add_kb_files_as_attachment.ainvoke(
                {"source_files": "技术要求.docx, 空文件.docx, 不存在.docx"})
            return json.loads(raw)

    data = asyncio.run(_run())
    assert data["status"] == "ok"
    assert data["added"] == ["技术要求.docx"]
    assert len(data["skipped"]) == 2  # 空内容 + 不存在
    pending = agent_tools._pending_kb_attachments.get("files") or []
    assert len(pending) == 1
    att = pending[0]
    assert att["filename"] == "技术要求.docx" and att["full_text"] == "全文内容。"
    assert att["status"] == "completed" and att["file_id"] == "技术要求.docx"
    # 清理旁路（避免污染其他测试）
    agent_tools.pop_pending_kb_attachments()


def test_add_kb_files_dedup_existing():
    fake = _FakeStore(texts={"技术要求.docx": "全文。"})
    agent_tools.set_current_attachments([
        {"file_id": "技术要求.docx", "filename": "技术要求.docx"}])
    agent_tools._pending_kb_attachments.pop("files", None)

    async def _run():
        with patch("app.services.rag.vector_store.VectorStore", fake):
            raw = await agent_tools.add_kb_files_as_attachment.ainvoke(
                {"source_files": "技术要求.docx"})
            return json.loads(raw)

    data = asyncio.run(_run())
    assert data["added"] == []
    assert any("已在附件列表" in s for s in data["skipped"])
    assert not agent_tools._pending_kb_attachments.get("files")


def test_prompt_rules_exist():
    from app.services.agent_prompt import TOOL_RULES
    assert "find_kb_reference_files" in TOOL_RULES
    assert "add_kb_files_as_attachment" in TOOL_RULES
    assert "严禁未经用户确认直接添加" in TOOL_RULES
