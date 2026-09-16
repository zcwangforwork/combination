"""
test_sql_prompt.py - TOOL_RULES SQL 段 + writing_style 基线回归护栏

覆盖:
- build_system_prompt 的 TOOL_RULES 包含 SQL 领域数据库查询段（工具名/只读规则/LIMIT）
- writing_style 风格选择: "concise" 注入精炼块, "detailed" 注入严谨详细块（回归护栏）
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


class TestSqlToolRulesSection:
    def test_sql_section_present(self):
        prompt = _build()
        assert "SQL 领域数据库查询" in prompt

    def test_sql_tool_names_mentioned(self):
        prompt = _build()
        assert "sql_db_list_tables" in prompt
        assert "sql_db_schema" in prompt
        assert "sql_db_query" in prompt

    def test_sql_read_only_rule_present(self):
        prompt = _build()
        assert "只读" in prompt
        assert "禁止任何 INSERT" in prompt

    def test_sql_limit_rule_present(self):
        prompt = _build()
        assert "LIMIT" in prompt or "50 行" in prompt

    def test_sql_tables_listed(self):
        prompt = _build()
        for t in ("products", "standards", "materials", "components", "parameters", "risk_items"):
            assert t in prompt

    def test_search_kb_still_present(self):
        """SQL 段不应顶掉既有的 search_kb 工具规则（互补不替代）"""
        prompt = _build()
        assert "search_kb" in prompt


class TestWritingStyleBaseline:
    def test_concise_style_injected_when_concise(self):
        prompt = _build(style="concise")
        assert "文档风格：精炼简洁（已选择）" in prompt

    def test_concise_style_absent_when_detailed(self):
        prompt = _build(style="detailed")
        assert "文档风格：精炼简洁（已选择）" not in prompt
        assert "文档风格：严谨详细（已选择）" in prompt

    def test_style_only_affects_doc_tools_not_chat(self):
        """风格块明确限定文档生成工具，聊天回复不受影响（评审决策回归护栏）"""
        prompt = _build(style="concise")
        assert "write_chapter" in prompt
        assert "不改变聊天回复风格" in prompt

    def test_default_is_detailed(self):
        prompt = _build()
        assert "文档风格：严谨详细（已选择）" in prompt
        assert "文档风格：精炼简洁（已选择）" not in prompt
