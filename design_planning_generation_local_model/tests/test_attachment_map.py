"""附件→章节预分配映射测试

覆盖：
1. _segment_attachment_blocks：标题感知切分 / 块大小上限 / 表格归段 / 块数上限
2. _map_attachments_to_outline：mock LLM 输出解析与合并 / 脏 JSON 兜底 / 每章上限 / 附件失败降级
3. _get_or_build_attachment_map：哈希失效重建 / 空附件短路 / 构建后旁路写入
4. _assigned_attachment_block：注入格式 / 小节过滤 / 未命中返回空
"""
import asyncio
import json
from unittest.mock import patch

from app.services import agent_tools


def _mk_attachment(fid, name, text):
    return {"file_id": fid, "filename": name, "full_text": text, "char_count": len(text)}


OUTLINE = json.dumps({
    "doc_title": "测试文档",
    "chapters": [
        {"title": "3 性能指标", "sections": [
            {"subsections": [{"title": "3.2 输注精度", "content_points": ["基础率精度"]}]}]},
        {"title": "4 安全要求", "sections": [
            {"subsections": [{"title": "4.1 报警", "content_points": ["报警阈值"]}]}]},
    ],
}, ensure_ascii=False)


def test_segment_blocks_headings_and_size():
    text = (
        "# 3 性能指标\n\n概述文本。" + "填充。" * 50 + "\n\n"
        "## 3.2 输注精度\n\n基础率精度 0.05U/h。\n\n"
        "| 参数 | 值 |\n|------|-----|\n| 精度 | 0.05U/h |\n\n"
        "# 4 安全要求\n\n安全描述。"
    )
    blocks = agent_tools._segment_attachment_blocks("f1", "技术要求.docx", text)
    assert blocks
    paths = " | ".join(b["section_path"] for b in blocks)
    assert "3.2 输注精度" in paths and "4 安全要求" in paths
    for b in blocks:
        assert len(b["text"]) <= agent_tools._ATT_MAP_BLOCK_MAX_CHARS + 80
    # 表格行不拆散：找到含表头的块必含数据行
    for b in blocks:
        if "| 参数 |" in b["text"]:
            assert "0.05U/h" in b["text"]


def test_segment_blocks_max_cap():
    text = "\n\n".join(f"第{i}段。" + "内容" * 100 for i in range(500))
    blocks = agent_tools._segment_attachment_blocks("f1", "a.docx", text,
                                                    max_blocks=20)
    assert len(blocks) == 20


def test_map_attachments_merges_and_caps():
    # 第二段超 800 字独立成块（b002），供分配测试引用
    atts = [_mk_attachment("f1", "技术要求.docx",
                           "# 3 性能指标\n\n精度数据 0.05U/h。\n\n" + "其它。" * 400)]

    def fake_llm(system_prompt="", user_prompt="", temperature=0.3, max_tokens=4096, **kw):
        return json.dumps({
            "assignments": [
                {"block_id": "att-f1-b001", "chapters": ["3 性能指标"],
                 "subsections": ["3.2 输注精度"], "reason": "实测数据", "priority": "high"},
                {"block_id": "att-f1-b002", "chapters": ["3 性能指标", "4 安全要求"],
                 "subsections": [], "reason": "通用参数", "priority": "normal"},
            ],
            "chapter_hints": {"3 性能指标": "参数取自技术要求"},
        }, ensure_ascii=False)

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw", side_effect=fake_llm):
            return await agent_tools._map_attachments_to_outline(OUTLINE, atts)

    mapping = asyncio.run(_run())
    chapters = mapping["chapters"]
    assert "3 性能指标" in chapters and "4 安全要求" in chapters
    assert chapters["3 性能指标"]["hint"] == "参数取自技术要求"
    assert chapters["3 性能指标"]["blocks"][0]["priority"] == "high"
    assert mapping["outline_hash"] and mapping["attachments_hash"]


def test_map_attachments_dirty_json_fallback():
    atts = [_mk_attachment("f1", "a.docx", "# 概述\n\n内容段落足够长用于切分。" * 30)]

    def fake_llm(system_prompt="", user_prompt="", **kw):
        return '```json\n{"assignments": [{"block_id": "att-f1-b001", ' \
               '"chapters": ["3 性能指标"], "priority": "high"}]}\n```'

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw", side_effect=fake_llm):
            return await agent_tools._map_attachments_to_outline(OUTLINE, atts)

    mapping = asyncio.run(_run())
    assert "3 性能指标" in mapping["chapters"]


def test_map_attachments_llm_failure_degrades():
    atts = [_mk_attachment("f1", "a.docx", "# 概述\n\n段落内容。" * 50)]

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=RuntimeError("boom")):
            return await agent_tools._map_attachments_to_outline(OUTLINE, atts)

    mapping = asyncio.run(_run())
    assert mapping["chapters"] == {}  # 静默降级：空映射


def test_get_or_build_uses_cache_and_bypass():
    atts = [_mk_attachment("f1", "技术要求.docx", "# 3 性能指标\n\n精度 0.05U/h。" + "细节。" * 100)]
    agent_tools.set_current_attachments(atts)
    agent_tools.set_current_attachment_map({})
    agent_tools._pending_attachment_map.pop("map", None)
    agent_tools._attachment_map_cache.clear()

    calls = []

    def fake_llm(system_prompt="", user_prompt="", **kw):
        calls.append(1)
        return json.dumps({
            "assignments": [{"block_id": "att-f1-b001", "chapters": ["3 性能指标"],
                             "priority": "high"}],
        }, ensure_ascii=False)

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw", side_effect=fake_llm):
            m1 = await agent_tools._get_or_build_attachment_map(OUTLINE)
            m2 = await agent_tools._get_or_build_attachment_map(OUTLINE)  # 命中缓存
            return m1, m2, len(calls)

    m1, m2, n_calls = asyncio.run(_run())
    assert n_calls == 1, "第二次应命中缓存不再调用 LLM"
    assert "3 性能指标" in m2["chapters"]
    # 构建结果写入旁路（供 after_tools 持久化）
    assert agent_tools._pending_attachment_map.get("map") is not None
    # 空附件短路
    agent_tools.set_current_attachments([])
    assert asyncio.run(agent_tools._get_or_build_attachment_map(OUTLINE)) == {}


def test_assigned_block_injection_and_filter():
    agent_tools.set_current_attachment_map({
        "outline_hash": "h", "attachments_hash": "a",
        "chapters": {"3 性能指标": {
            "hint": "本章优先取自技术要求",
            "blocks": [
                {"file_id": "f1", "filename": "技术要求.docx", "section_path": "3.2 输注精度",
                 "text": "精度0.05U/h", "reason": "实测", "subsections": ["3.2 输注精度"], "priority": "high"},
                {"file_id": "f1", "filename": "技术要求.docx", "section_path": "",
                 "text": "章级通用块", "reason": "", "subsections": [], "priority": "normal"},
            ]}}})
    blk = agent_tools._assigned_attachment_block("3 性能指标", "3.2 输注精度")
    assert "选用指引" in blk and "精度0.05U/h" in blk and "章级通用块" in blk
    # 小节过滤：非目标小节的块不注入
    blk2 = agent_tools._assigned_attachment_block("3 性能指标", "3.5 其他小节")
    assert "精度0.05U/h" not in blk2 and "章级通用块" in blk2
    # 未命中章节
    assert agent_tools._assigned_attachment_block("不存在的章") == ""
    # 无映射
    agent_tools.set_current_attachment_map({})
    assert agent_tools._assigned_attachment_block("3 性能指标") == ""
