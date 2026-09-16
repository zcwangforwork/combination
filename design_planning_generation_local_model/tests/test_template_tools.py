"""
test_template_tools.py - outline_from_template 工具与 PHASE1_TOOLS 注册回归护栏

覆盖:
- PHASE1_TOOLS 已注册 outline_from_template（位于 outline_from_attachment 之后）
- 无模板 / 指定不存在的 template_id / 无全文模板 → 降级错误
- 正常路径 → 返回 design_outline 兼容 JSON，且全文按预算截断分发给 LLM
- LLM 提取失败 → 错误带「请改用 design_outline 或 outline_from_attachment」指引
"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services import agent_tools


def _sample_template(full_text="第一章 概述\n贴敷式胰岛素泵属于有源医疗器械…\n第二章 性能要求\n…",
                     template_id="tpl_abc", filename="KF-CGM-2-0004 设计输入 V7.0.pdf"):
    return {
        "template_id": template_id,
        "name": "设计输入 V7.0",
        "filename": filename,
        "doc_type": "design_input",
        "char_count": 12000,
        "preview": "预览…",
        "toc": "1 目的\n2 范围",
        "full_text": full_text,
        "status": "completed",
    }


def _valid_outline_json():
    return json.dumps({
        "doc_title": "设计输入 V7.0",
        "chapters": [
            {"id": 1, "title": "第一章 概述", "description": "d", "key_standards": [],
             "subsections": [{"title": "1.1 目的", "content_points": ["p1"]}]}
        ],
    }, ensure_ascii=False)


class TestPHASE1ToolsRegistration:
    def test_outline_from_template_registered(self):
        """PHASE1_TOOLS 应包含 outline_from_template"""
        names = [t.name for t in agent_tools.PHASE1_TOOLS]
        assert "outline_from_template" in names

    def test_registered_after_outline_from_attachment(self):
        """outline_from_template 应注册在 outline_from_attachment 之后"""
        names = [t.name for t in agent_tools.PHASE1_TOOLS]
        assert names.index("outline_from_template") > names.index("outline_from_attachment")

    def test_registered_before_write_chapter(self):
        """outline_from_template 应注册在 write_chapter 之前（生成路径连续）"""
        names = [t.name for t in agent_tools.PHASE1_TOOLS]
        assert names.index("outline_from_template") < names.index("write_chapter")


class TestOutlineFromTemplateErrors:
    def test_no_templates(self):
        """无模板时返回降级错误"""
        agent_tools.set_current_templates([])
        result = asyncio.run(agent_tools.outline_from_template.ainvoke(
            {"template_id": "", "doc_type": "design_development_plan", "product_name": "贴敷式胰岛素泵"}
        ))
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "添加模板" in parsed["message"]

    def test_template_id_not_found(self):
        """指定不存在的 template_id 时返回降级错误"""
        agent_tools.set_current_templates([_sample_template()])
        result = asyncio.run(agent_tools.outline_from_template.ainvoke(
            {"template_id": "nope", "doc_type": "design_development_plan", "product_name": "贴敷式胰岛素泵"}
        ))
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "nope" in parsed["message"]

    def test_no_template_with_full_text(self):
        """所有模板均无 full_text 时返回降级错误"""
        agent_tools.set_current_templates([_sample_template(full_text="")])
        result = asyncio.run(agent_tools.outline_from_template.ainvoke(
            {"template_id": "", "doc_type": "design_development_plan", "product_name": "贴敷式胰岛素泵"}
        ))
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "文本" in parsed["message"] or "full_text" in parsed["message"]

    def test_extract_error_has_guidance(self):
        """LLM 提取失败时错误应带降级指引"""
        agent_tools.set_current_templates([_sample_template()])

        async def _raise(*a, **k):
            raise agent_tools._OutlineExtractError("章节结构识别失败: boom。")

        with patch.object(agent_tools, "_extract_outline_from_text", side_effect=_raise):
            result = asyncio.run(agent_tools.outline_from_template.ainvoke(
                {"template_id": "", "doc_type": "design_development_plan", "product_name": "贴敷式胰岛素泵"}
            ))
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "outline_from_attachment" in parsed["message"]


class TestOutlineFromTemplateHappyPath:
    def test_returns_valid_outline_json(self):
        """正常路径返回 design_outline 兼容 JSON"""
        agent_tools.set_current_templates([_sample_template()])

        async def _fake_extract(text_sample, filename_display, doc_label, doc_type):
            return _valid_outline_json()

        with patch.object(agent_tools, "_extract_outline_from_text", side_effect=_fake_extract):
            result = asyncio.run(agent_tools.outline_from_template.ainvoke(
                {"template_id": "", "doc_type": "design_development_plan", "product_name": "贴敷式胰岛素泵"}
            ))
        parsed = json.loads(result)
        assert "doc_title" in parsed
        assert parsed["chapters"][0]["title"] == "第一章 概述"

    def test_template_full_text_passed_to_extractor(self):
        """模板全文与文件名应传给提取器"""
        agent_tools.set_current_templates([_sample_template()])
        captured = {}

        async def _fake_extract(text_sample, filename_display, doc_label, doc_type):
            captured["text"] = text_sample
            captured["name"] = filename_display
            captured["label"] = doc_label
            return _valid_outline_json()

        with patch.object(agent_tools, "_extract_outline_from_text", side_effect=_fake_extract):
            asyncio.run(agent_tools.outline_from_template.ainvoke(
                {"template_id": "", "doc_type": "design_development_plan", "product_name": "贴敷式胰岛素泵"}
            ))
        assert "第一章 概述" in captured["text"]
        assert "KF-CGM-2-0004 设计输入 V7.0.pdf" in captured["name"]
        assert "项目开发计划书" in captured["label"]  # DOC_TYPE_LABELS 映射

    def test_template_id_selects_single(self):
        """指定 template_id 时只使用该模板（不引入其他模板全文）"""
        tpl2 = _sample_template(full_text="其他模板独有内容 " * 50)
        agent_tools.set_current_templates([_sample_template(), tpl2])
        captured = {}

        async def _fake_extract(text_sample, filename_display, doc_label, doc_type):
            captured["text"] = text_sample
            return _valid_outline_json()

        with patch.object(agent_tools, "_extract_outline_from_text", side_effect=_fake_extract):
            asyncio.run(agent_tools.outline_from_template.ainvoke(
                {"template_id": "tpl_abc", "doc_type": "design_development_plan", "product_name": "贴敷式胰岛素泵"}
            ))
        assert "其他模板独有内容" not in captured["text"]

    def test_multi_template_all_represented(self):
        """未指定 template_id 时所有有全文的模板都应分发（预算等额分配）"""
        agent_tools.set_current_templates([
            _sample_template(),
            _sample_template(full_text="模板B独有内容", template_id="tpl_b", filename="B.txt"),
        ])
        captured = {}

        async def _fake_extract(text_sample, filename_display, doc_label, doc_type):
            captured["text"] = text_sample
            return _valid_outline_json()

        with patch.object(agent_tools, "_extract_outline_from_text", side_effect=_fake_extract):
            asyncio.run(agent_tools.outline_from_template.ainvoke(
                {"template_id": "", "doc_type": "design_development_plan", "product_name": "贴敷式胰岛素泵"}
            ))
        assert "模板B独有内容" in captured["text"]

    def test_long_full_text_truncated_to_budget(self):
        """超长模板全文应按 50000 预算截断"""
        long_text = "长内容 " * 50000  # 约 15 万字符
        agent_tools.set_current_templates([_sample_template(full_text=long_text)])
        captured = {}

        async def _fake_extract(text_sample, filename_display, doc_label, doc_type):
            captured["text"] = text_sample
            return _valid_outline_json()

        with patch.object(agent_tools, "_extract_outline_from_text", side_effect=_fake_extract):
            asyncio.run(agent_tools.outline_from_template.ainvoke(
                {"template_id": "", "doc_type": "design_development_plan", "product_name": "贴敷式胰岛素泵"}
            ))
        # text_parts 含 "=== 模板: ... ===\n" 前缀，去掉前缀换行后正文部分不超过 50000
        body = captured["text"].split("===")[-1].lstrip("\n")
        assert len(body) <= 50000
