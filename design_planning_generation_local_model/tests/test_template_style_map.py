"""模板贴近增强测试：风格总结懒加载核心 + 模板分节对位映射

覆盖：
1. _analyze_template_style_core：mock LLM 提炼总结 / 无模板返回空
2. analyze_template_style 工具：复用核心，返回 JSON
3. _map_templates_to_outline：LLM 输出解析合并 / 失败静默空映射
4. _get_or_build_template_map：缓存命中（第二次零调用）/ 空模板短路 / 旁路写入
5. _assigned_template_block：注入格式 / 未命中空
6. 提示词：显式指定模板规则存在
"""
import asyncio
import json
from unittest.mock import patch

from app.services import agent_tools


OUTLINE = json.dumps({
    "chapters": [
        {"title": "3 性能指标", "sections": [
            {"subsections": [{"title": "3.2 输注精度", "content_points": ["基础率"]}]}]},
    ],
}, ensure_ascii=False)


def _mk_tpl(tid, name, text):
    return {"template_id": tid, "filename": name, "full_text": text}


def test_analyze_style_core_with_llm():
    agent_tools.set_current_templates([_mk_tpl("t1", "模板A.docx", "# 3 性能\n\n条目式写法。" * 40)])

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value="## 风格总结\n- 短句条目式\n- 多用小表格"):
            return await agent_tools._analyze_template_style_core()

    summary = asyncio.run(_run())
    assert "风格总结" in summary and "小表格" in summary


def test_analyze_style_core_no_templates():
    agent_tools.set_current_templates([])

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw") as m:
            core = await agent_tools._analyze_template_style_core()
            return core, m.call_count

    core, calls = asyncio.run(_run())
    assert core == "" and calls == 0


def test_analyze_template_style_tool_reuses_core():
    agent_tools.set_current_templates([_mk_tpl("t1", "模板A.docx", "正文内容。" * 100)])

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value="句式总结") as m:
            raw = await agent_tools.analyze_template_style.ainvoke({})
            return json.loads(raw), m.call_count

    data, calls = asyncio.run(_run())
    assert data["status"] == "ok"
    assert data["style_summary"] == "句式总结"
    assert data["template_count"] == 1
    assert calls == 1  # 复用核心，只调一次 LLM


def test_map_templates_merges():
    tpls = [_mk_tpl("t1", "模板A.docx",
                    "# 3 输注精度要求\n\n- 精度条目式写法样例。\n\n" + "细节。" * 300)]

    def fake_llm(system_prompt="", user_prompt="", **kw):
        return json.dumps({
            "assignments": [{"block_id": "att-t1-b001", "chapters": ["3 性能指标"],
                             "reason": "同为指标条目式写法"}],
            "chapter_hints": {"3 性能指标": "采用条目+小表格式，编号用 X.Y"},
        }, ensure_ascii=False)

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw", side_effect=fake_llm):
            return await agent_tools._map_templates_to_outline(OUTLINE, tpls)

    mapping = asyncio.run(_run())
    entry = mapping["chapters"]["3 性能指标"]
    assert entry["hint"] == "采用条目+小表格式，编号用 X.Y"
    assert entry["blocks"] and entry["blocks"][0]["filename"] == "模板A.docx"
    assert mapping["outline_hash"] and mapping["templates_hash"]


def test_get_or_build_template_map_cache_and_bypass():
    tpls = [_mk_tpl("t1", "模板A.docx", "# 3 性能\n\n条目样例。" * 100)]
    agent_tools.set_current_templates(tpls)
    agent_tools.set_current_template_map({})
    agent_tools._template_map_cache.clear()
    agent_tools._pending_template_map.pop("map", None)

    calls = []

    def fake_llm(system_prompt="", user_prompt="", **kw):
        calls.append(1)
        return json.dumps({"assignments": [
            {"block_id": "att-t1-b001", "chapters": ["3 性能指标"]}]}, ensure_ascii=False)

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw", side_effect=fake_llm):
            m1 = await agent_tools._get_or_build_template_map(OUTLINE)
            m2 = await agent_tools._get_or_build_template_map(OUTLINE)
            return m1, m2

    m1, m2 = asyncio.run(_run())
    assert len(calls) == 1, "第二次应命中缓存"
    assert "3 性能指标" in m2["chapters"]
    assert agent_tools._pending_template_map.get("map") is not None
    # 空模板短路
    agent_tools.set_current_templates([])
    assert asyncio.run(agent_tools._get_or_build_template_map(OUTLINE)) == {}


def test_assigned_template_block_format():
    agent_tools.set_current_template_map({
        "outline_hash": "h", "templates_hash": "a",
        "chapters": {"3 性能指标": {
            "hint": "条目+小表格，编号 X.Y",
            "blocks": [{"filename": "模板A.docx", "section_path": "3 输注精度要求",
                        "text": "- 精度条目式写法样例。", "reason": "同指标条目式"}],
        }}})
    blk = agent_tools._assigned_template_block("3 性能指标")
    assert "写法要点" in blk and "模板A.docx" in blk and "条目式写法样例" in blk
    assert agent_tools._assigned_template_block("不存在的章") == ""
    agent_tools.set_current_template_map({})
    assert agent_tools._assigned_template_block("3 性能指标") == ""


def test_prompt_explicit_template_rule():
    from app.services.agent_prompt import SOP_KNOWLEDGE
    assert "用户显式指定模板" in SOP_KNOWLEDGE
    assert "template_id" in SOP_KNOWLEDGE and "只按该模板" in SOP_KNOWLEDGE
