"""
test_template_prompt.py - 添加模板功能的 prompt 注入回归护栏

覆盖:
- build_system_prompt 无模板时不注入模板段（不回归）
- 有模板时注入「用户已添加模板」段（名称/预览/目录/outline_from_template 指引）
- TOOL_RULES 5c 段包含 outline_from_template 工具说明
- SOP_KNOWLEDGE 步骤4 在无模板/有模板时切换（模板优先路径）
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def _build(style="detailed", **overrides):
    from app.services.agent_state import create_initial_state
    from app.services.agent_prompt import build_system_prompt
    state = create_initial_state()
    state.update({"writing_style": style, **overrides})
    return build_system_prompt(state)


def _sample_template():
    return {
        "template_id": "tpl_abc",
        "name": "设计输入 V7.0",
        "filename": "KF-CGM-2-0004 设计输入 V7.0.pdf",
        "doc_type": "design_input",
        "char_count": 12000,
        "preview": "本文件规定贴敷式胰岛素泵的设计输入要求…",
        "toc": "1 目的\n2 范围\n3 术语与定义\n4 系统组成\n5 性能要求",
        "full_text": "（全文内容）",
        "status": "completed",
    }


class TestNoTemplateBaseline:
    def test_no_template_section_when_empty(self):
        """没有模板时不应注入模板段"""
        prompt = _build()
        assert "用户已添加模板" not in prompt

    def test_no_outline_from_template_hint_when_empty(self):
        """没有模板时不应注入动态的模板优先指引（TOOL_RULES 静态文档不受影响）"""
        prompt = _build()
        assert "优先向用户提供「按模板生成」选项" not in prompt


class TestTemplateInjection:
    def test_template_section_present(self):
        """有模板时注入「用户已添加模板」段"""
        prompt = _build(templates=[_sample_template()])
        assert "用户已添加模板" in prompt

    def test_template_name_injected(self):
        """模板名称/文件名应被注入"""
        prompt = _build(templates=[_sample_template()])
        assert "设计输入 V7.0" in prompt
        assert "KF-CGM-2-0004 设计输入 V7.0.pdf" in prompt

    def test_template_doc_type_injected(self):
        """模板文档类型应被注入"""
        prompt = _build(templates=[_sample_template()])
        assert "design_input" in prompt

    def test_template_preview_injected(self):
        """模板内容预览应被注入"""
        prompt = _build(templates=[_sample_template()])
        assert "贴敷式胰岛素泵的设计输入要求" in prompt

    def test_template_toc_injected(self):
        """模板目录（章节结构）应被注入"""
        prompt = _build(templates=[_sample_template()])
        assert "1 目的" in prompt
        assert "5 性能要求" in prompt

    def test_template_style_instruction_present(self):
        """生成时模仿模板写作风格的指引应存在"""
        prompt = _build(templates=[_sample_template()])
        assert "写作风格" in prompt
        assert "outline_from_template" in prompt

    def test_multiple_templates_listed(self):
        """多个模板应全部列出"""
        tpl2 = {**_sample_template(), "template_id": "tpl_2", "name": "风险管理计划 V2", "doc_type": "risk_management_plan"}
        prompt = _build(templates=[_sample_template(), tpl2])
        assert "设计输入 V7.0" in prompt
        assert "风险管理计划 V2" in prompt

    def test_template_without_preview_toc_still_injected(self):
        """无 preview/toc 的模板也应注入名称与类型"""
        tpl = {**_sample_template(), "preview": "", "toc": ""}
        prompt = _build(templates=[tpl])
        assert "用户已添加模板" in prompt
        assert "设计输入 V7.0" in prompt


class TestToolRulesSection5c:
    def test_outline_from_template_documented(self):
        """TOOL_RULES 应包含 outline_from_template 工具说明"""
        prompt = _build()
        assert "outline_from_template" in prompt

    def test_outline_from_template_style_mimic(self):
        """工具说明应提到模仿模板写作风格"""
        prompt = _build()
        assert "模仿" in prompt and "模板" in prompt


class TestSopStep4TemplatePath:
    def test_offer_template_option_when_templates_present(self):
        """有模板时步骤4应提供「按模板生成」选项"""
        prompt = _build(templates=[_sample_template()])
        assert "按模板生成" in prompt
        assert "outline_from_template" in prompt

    def test_attachment_path_still_present_when_templates_present(self):
        """有模板时原有附件路径说明不应被顶掉"""
        prompt = _build(templates=[_sample_template()])
        assert "outline_from_attachment" in prompt


class TestWritingStyleNotAffected:
    def test_template_and_style_coexist(self):
        """模板段与文档风格选择互不影响"""
        prompt = _build(style="concise", templates=[_sample_template()])
        assert "用户已添加模板" in prompt
        assert "文档风格：精炼简洁（已选择）" in prompt
