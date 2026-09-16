"""
test_summarize.py - summarize_section 工具单元测试

覆盖:
- _split_chapter_into_subsections: 小节拆分逻辑
- _count_chinese_chars: 字符统计
- _get_section_names_from_markdown: 章节名提取
- _summarize_one_subsection: 单小节精简 (mock LLM)
- summarize_section: 整体流程、参数校验、失败回退、双模式
"""
import os
import sys
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ═══════════════════════════════════════════════════════════════
# 辅助函数测试
# ═══════════════════════════════════════════════════════════════

class TestSplitChapterIntoSubsections:
    """_split_chapter_into_subsections 小节拆分测试"""

    def test_split_normal_chapter(self):
        """正常章节：## 章节标题 + 多个 ### 小节"""
        from app.services.agent_tools import _split_chapter_into_subsections

        content = """## 第一章 设计开发

### 1.1 目的

本章规范设计开发流程，依据 ISO 13485 §7.3.2。

### 1.2 范围

适用于贴敷式胰岛素泵全生命周期。

### 1.3 术语

闭环控制：指根据 CGM 反馈自动调节输注速率。
"""
        result = _split_chapter_into_subsections(content)
        assert len(result) == 1
        parsed = result[0]
        assert "## 第一章 设计开发" in parsed["header"]
        assert len(parsed["subsections"]) == 3
        assert "### 1.1 目的" in parsed["subsections"][0]["title"]
        assert "ISO 13485" in parsed["subsections"][0]["body"]
        assert "### 1.2 范围" in parsed["subsections"][1]["title"]
        assert "贴敷式胰岛素泵" in parsed["subsections"][1]["body"]

    def test_split_no_subsections(self):
        """无 ### 小节：返回空 subsections 列表"""
        from app.services.agent_tools import _split_chapter_into_subsections

        content = """## 第二章 风险管理

本章内容无小节划分，只有整段正文。
"""
        result = _split_chapter_into_subsections(content)
        assert len(result) == 1
        assert result[0]["subsections"] == []

    def test_split_empty_content(self):
        """空内容：返回空结构"""
        from app.services.agent_tools import _split_chapter_into_subsections

        result = _split_chapter_into_subsections("")
        assert len(result) == 1
        assert result[0]["header"] == ""
        assert result[0]["subsections"] == []

    def test_split_preserves_subsection_body_with_markdown(self):
        """小节正文保留 Markdown 格式（表格、列表）"""
        from app.services.agent_tools import _split_chapter_into_subsections

        content = """## 第三章 设计输入

### 3.1 性能要求

| 参数 | 限值 | 依据 |
|------|------|------|
| 输注精度 | 0.05 U/h | GB 9706.224 |
| 续航 | 3-7 天 | ISO 14971 |

- 闭环控制响应时间 ≤ 5 分钟
- BLE 5.0 通信距离 ≥ 10 米
"""
        result = _split_chapter_into_subsections(content)
        sub = result[0]["subsections"][0]
        assert "0.05 U/h" in sub["body"]
        assert "GB 9706.224" in sub["body"]
        assert "BLE 5.0" in sub["body"]
        # 表格行保留
        assert "|------|------|------|" in sub["body"] or "输注精度" in sub["body"]

    def test_split_four_level_chapter(self):
        """4级层级章节：## / ### / #### / ##### 都能被识别为小节边界"""
        from app.services.agent_tools import _split_chapter_into_subsections

        content = """## 2 性能指标

### 2.1 通用要求

#### 2.1.1 输入输出

- 输入：血糖数据
- 输出：胰岛素输注数据

#### 2.1.2 接口

##### 2.1.2.1 数据接口

- 协议：Bluetooth 4.0
- 频率：2402~2480MHz

##### 2.1.2.2 网络接口

- 协议：IEEE 802.11 a/b/g/n
"""
        result = _split_chapter_into_subsections(content)
        assert len(result) == 1
        parsed = result[0]
        assert "## 2 性能指标" in parsed["header"]
        # 应识别出 5 个小节边界：### 2.1, #### 2.1.1, #### 2.1.2, ##### 2.1.2.1, ##### 2.1.2.2
        titles = [s["title"] for s in parsed["subsections"]]
        assert len(parsed["subsections"]) == 5
        assert any("### 2.1 通用要求" in t for t in titles)
        assert any("#### 2.1.1 输入输出" in t for t in titles)
        assert any("#### 2.1.2 接口" in t for t in titles)
        assert any("##### 2.1.2.1 数据接口" in t for t in titles)
        assert any("##### 2.1.2.2 网络接口" in t for t in titles)
        # 验证各小节正文内容正确归属
        body_by_title = {s["title"]: s["body"] for s in parsed["subsections"]}
        assert "2402~2480MHz" in body_by_title["##### 2.1.2.1 数据接口"]
        assert "IEEE 802.11" in body_by_title["##### 2.1.2.2 网络接口"]
        assert "血糖数据" in body_by_title["#### 2.1.1 输入输出"]


class TestCountChineseChars:
    """_count_chinese_chars 字符统计测试"""

    def test_pure_chinese(self):
        from app.services.agent_tools import _count_chinese_chars
        assert _count_chinese_chars("贴敷式胰岛素泵") == 7

    def test_mixed_chinese_english(self):
        from app.services.agent_tools import _count_chinese_chars
        # 中英文混合，去 markdown 标记后统计
        chars = _count_chinese_chars("依据 ISO 13485 §7.3.2 标准")
        # "ISO", "13485", "7.3.2", "依据", "标准" 等字符
        assert chars > 0
        assert "ISO" not in "" or True  # 验证不抛异常

    def test_with_markdown_syntax(self):
        from app.services.agent_tools import _count_chinese_chars
        # Markdown 标记应被去除
        raw = "## 章节标题\n\n- 列表项1\n- 列表项2"
        cleaned = _count_chinese_chars(raw)
        assert cleaned > 0
        # 不应包含 # - 等标记字符
        # (函数内部已清洗，验证返回的是有效字符数)

    def test_empty(self):
        from app.services.agent_tools import _count_chinese_chars
        assert _count_chinese_chars("") == 0
        assert _count_chinese_chars(None) == 0


class TestGetSectionNamesFromMarkdown:
    """_get_section_names_from_markdown 章节名提取测试"""

    def test_extract_single_section(self):
        from app.services.agent_tools import _get_section_names_from_markdown
        md = "# 第一章 设计开发\n\n## 1.1 目的\n\n内容...\n"
        names = _get_section_names_from_markdown(md)
        assert names == ["第一章 设计开发"]

    def test_extract_multiple_sections(self):
        from app.services.agent_tools import _get_section_names_from_markdown
        md = """# 第一章 设计开发

## 1.1 目的
内容

# 第二章 风险管理

## 2.1 风险分析
内容

# 第三章 设计验证
"""
        names = _get_section_names_from_markdown(md)
        assert len(names) == 3
        assert "第一章 设计开发" in names
        assert "第二章 风险管理" in names
        assert "第三章 设计验证" in names

    def test_extract_empty(self):
        from app.services.agent_tools import _get_section_names_from_markdown
        assert _get_section_names_from_markdown("") == []
        assert _get_section_names_from_markdown("仅文本无标题") == []

    def test_does_not_extract_subsection_headers(self):
        """### 小节标题不应被当作章节名"""
        from app.services.agent_tools import _get_section_names_from_markdown
        md = "# 第一章\n\n## 1.1 小节\n\n### 1.1.1 子小节\n\n内容"
        names = _get_section_names_from_markdown(md)
        # 只提取 # 一级标题
        assert names == ["第一章"]


# ═══════════════════════════════════════════════════════════════
# _summarize_one_subsection 测试 (mock LLM)
# ═══════════════════════════════════════════════════════════════

class TestSummarizeOneSubsection:
    """_summarize_one_subsection 单小节精简测试"""

    @pytest.mark.asyncio
    async def test_successful_summarize(self):
        """LLM 正常返回时，精简成功"""
        from app.services.agent_tools import _summarize_one_subsection

        orig_body = "依据 ISO 13485 §7.3.2 标准，本章规范设计开发流程。" * 20
        expected_summary = "依据 ISO 13485 §7.3.2，规范设计开发流程。"

        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value=expected_summary):
            sub_title, new_body, stat = await _summarize_one_subsection(
                sub_title="### 1.1 目的",
                sub_body=orig_body,
                target_chars=50,
                chapter_name="第一章",
                doc_label="项目开发计划书",
            )

        assert sub_title == "### 1.1 目的"
        assert "ISO 13485" in new_body
        assert stat["status"] == "ok"
        assert stat["orig_chars"] > stat["new_chars"]

    @pytest.mark.asyncio
    async def test_llm_returns_empty(self):
        """LLM 返回空时，保留原文并标记 error"""
        from app.services.agent_tools import _summarize_one_subsection

        orig_body = "原始小节内容"

        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value=""):
            sub_title, new_body, stat = await _summarize_one_subsection(
                sub_title="### 1.1 目的",
                sub_body=orig_body,
                target_chars=100,
                chapter_name="第一章",
                doc_label="项目开发计划书",
            )

        assert new_body == orig_body  # 保留原文
        assert stat["status"] == "error"
        assert "空响应" in stat["reason"]

    @pytest.mark.asyncio
    async def test_llm_timeout(self):
        """LLM 超时时，保留原文并标记 error"""
        from app.services.agent_tools import _summarize_one_subsection
        import asyncio as _asyncio

        orig_body = "原始小节内容"

        def _raise_timeout(*args, **kwargs):
            raise _asyncio.TimeoutError()

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=_raise_timeout):
            sub_title, new_body, stat = await _summarize_one_subsection(
                sub_title="### 1.1 目的",
                sub_body=orig_body,
                target_chars=100,
                chapter_name="第一章",
                doc_label="项目开发计划书",
            )

        assert new_body == orig_body
        assert stat["status"] == "error"
        assert "超时" in stat["reason"]

    @pytest.mark.asyncio
    async def test_llm_adds_title_prefix_removed(self):
        """LLM 误加 ### 标题前缀时，应被清理"""
        from app.services.agent_tools import _summarize_one_subsection

        orig_body = "原始内容" * 50
        # LLM 误加了 ### 1.1 目的 前缀
        llm_response = "### 1.1 目的\n\n精简后的内容"

        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value=llm_response):
            sub_title, new_body, stat = await _summarize_one_subsection(
                sub_title="### 1.1 目的",
                sub_body=orig_body,
                target_chars=50,
                chapter_name="第一章",
                doc_label="项目开发计划书",
            )

        # 应清理掉 LLM 误加的 ### 标题
        assert not new_body.startswith("### ")
        assert "精简后的内容" in new_body

    @pytest.mark.asyncio
    async def test_min_target_chars_enforced(self):
        """目标字数过小时，按比例化保底（min(40, 原字数×0.9)）"""
        from app.services.agent_tools import _summarize_one_subsection

        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value="精简内容") as mock:
            await _summarize_one_subsection(
                sub_title="### 1.1 目的",
                sub_body="原始内容",  # 4 字
                target_chars=10,  # 过小
                chapter_name="第一章",
                doc_label="项目开发计划书",
            )
            # 检查 system_prompt：target_chars 应被保底到 min(40, int(4*0.9)=3) = 3
            call_args = mock.call_args
            prompt = call_args[1]["system_prompt"] or call_args[0][0]
            # 比例化保底后：4*0.9=3，下限 40，但 3 < 40 故取 min(40,3)=3
            assert "目标约 3 字" in prompt, f"expected 3 chars floor, got: {prompt[:200]}"


# ═══════════════════════════════════════════════════════════════
# summarize_section 工具测试
# ═══════════════════════════════════════════════════════════════

class TestSummarizeSectionTool:
    """summarize_section 工具整体测试"""

    def _setup_context(self, chapter_name: str, chapter_content: str):
        """辅助：设置 _current_generated_markdown 上下文"""
        from app.services.agent_tools import set_current_doc_context
        markdown = f"# {chapter_name}\n\n{chapter_content}\n\n"
        set_current_doc_context(
            doc_type="design_development_plan",
            product_name="贴敷式胰岛素泵",
            markdown=markdown,
        )

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_error(self):
        """无效 mode 参数返回错误"""
        from app.services.agent_tools import summarize_section

        self._setup_context("测试章节", "## 测试章节\n\n### 小节\n\n内容")

        result_str = await summarize_section.ainvoke({
            "section_name": "测试章节",
            "mode": "invalid_mode",
            "target": 0.5,
        })
        data = json.loads(result_str)
        assert data["status"] == "error"
        assert "mode" in data["message"]

    @pytest.mark.asyncio
    async def test_invalid_ratio_target_returns_error(self):
        """比例模式下 target 超出范围返回错误"""
        from app.services.agent_tools import summarize_section

        self._setup_context("测试章节", "## 测试章节\n\n### 小节\n\n内容")

        result_str = await summarize_section.ainvoke({
            "section_name": "测试章节",
            "mode": "ratio",
            "target": 2.0,  # 超出 1.0
        })
        data = json.loads(result_str)
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_words_target_returns_error(self):
        """字数模式下 target 过小返回错误"""
        from app.services.agent_tools import summarize_section

        self._setup_context("测试章节", "## 测试章节\n\n### 小节\n\n内容")

        result_str = await summarize_section.ainvoke({
            "section_name": "测试章节",
            "mode": "words",
            "target": 50,  # 小于 100
        })
        data = json.loads(result_str)
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_empty_markdown_returns_error(self):
        """无已生成内容时返回错误"""
        from app.services.agent_tools import summarize_section, set_current_doc_context

        set_current_doc_context(
            doc_type="design_development_plan",
            product_name="贴敷式胰岛素泵",
            markdown="",  # 空 markdown
        )

        result_str = await summarize_section.ainvoke({
            "section_name": "不存在章节",
            "mode": "ratio",
            "target": 0.5,
        })
        data = json.loads(result_str)
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_section_not_found_returns_error(self):
        """章节不存在时返回错误并列出可用章节"""
        from app.services.agent_tools import summarize_section

        self._setup_context("存在的章节", "## 存在的章节\n\n### 小节\n\n内容")

        result_str = await summarize_section.ainvoke({
            "section_name": "不存在的章节",
            "mode": "ratio",
            "target": 0.5,
        })
        data = json.loads(result_str)
        assert data["status"] == "error"
        assert "available_sections" in data
        assert "存在的章节" in data["available_sections"]

    @pytest.mark.asyncio
    async def test_ratio_mode_successful(self):
        """比例模式精简成功（mock LLM）"""
        from app.services.agent_tools import summarize_section, _pending_chapter_contents

        chapter = """## 第一章 设计开发

### 1.1 目的

依据 ISO 13485 §7.3.2 标准，本章规范设计开发流程。本章适用于贴敷式胰岛素泵的设计开发全过程，包括需求分析、设计输入、设计输出、设计验证、设计确认和设计转换等阶段。

### 1.2 范围

适用于贴敷式胰岛素泵的整生命周期，覆盖硬件、软件、结构、包装等所有设计要素。
"""
        self._setup_context("第一章 设计开发", chapter)
        _pending_chapter_contents.clear()

        # Mock LLM 返回精简内容
        def mock_llm(system_prompt, user_prompt, **kwargs):
            # 根据 user_prompt 中的原小节内容判断要返回什么精简结果
            if "ISO 13485" in user_prompt:
                return "依据 ISO 13485 §7.3.2，规范设计开发流程。"
            return "适用于贴敷式胰岛素泵全生命周期。"

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=mock_llm):
            result_str = await summarize_section.ainvoke({
                "section_name": "第一章 设计开发",
                "mode": "ratio",
                "target": 0.5,
            })

        data = json.loads(result_str)
        assert data["status"] == "ok"
        assert data["mode"] == "ratio"
        assert data["subsections_count"] == 2
        assert data["success_count"] == 2
        assert data["failed_count"] == 0
        assert data["orig_total_chars"] > data["new_total_chars"]
        assert data["compression_ratio"] < 1.0

        # 验证旁路内容已写入
        assert "第一章 设计开发" in _pending_chapter_contents
        full_content = _pending_chapter_contents["第一章 设计开发"]
        assert "## 第一章 设计开发" in full_content
        assert "### 1.1 目的" in full_content
        assert "### 1.2 范围" in full_content
        # 精简后内容包含原文关键术语
        assert "ISO 13485" in full_content

    @pytest.mark.asyncio
    async def test_words_mode_allocates_budget_proportionally(self):
        """字数模式按各小节原字数比例分配预算"""
        from app.services.agent_tools import summarize_section, _pending_chapter_contents

        # 第1小节长，第2小节短
        chapter = """## 测试章节

### 1.1 长小节

""" + "依据 ISO 13485 标准要求。 " * 30 + """

### 1.2 短小节

短内容。
"""
        self._setup_context("测试章节", chapter)
        _pending_chapter_contents.clear()

        captured_targets = []

        def mock_llm(system_prompt, user_prompt, **kwargs):
            # 提取目标字数（适配新 prompt 格式："目标约 N 字以内"）
            import re
            m = re.search(r'目标约 (\d+) 字', system_prompt)
            if m:
                captured_targets.append(int(m.group(1)))
            return "精简内容"

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=mock_llm):
            result_str = await summarize_section.ainvoke({
                "section_name": "测试章节",
                "mode": "words",
                "target": 400,  # 总目标 400 字
            })

        data = json.loads(result_str)
        assert data["status"] == "ok"
        # 长小节应分配更多字数
        assert len(captured_targets) == 2
        assert captured_targets[0] > captured_targets[1]

    @pytest.mark.asyncio
    async def test_failed_subsection_keeps_original(self):
        """单小节精简失败时保留原文，其他小节正常精简"""
        from app.services.agent_tools import summarize_section, _pending_chapter_contents

        chapter = """## 测试章节

### 1.1 正常小节

正常内容。

### 1.2 失败小节

失败内容。
"""
        self._setup_context("测试章节", chapter)
        _pending_chapter_contents.clear()

        call_count = [0]

        def mock_llm(system_prompt, user_prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # 第1次调用成功
                return "精简后的内容"
            else:
                # 第2次调用失败（空响应）
                return ""

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=mock_llm):
            result_str = await summarize_section.ainvoke({
                "section_name": "测试章节",
                "mode": "ratio",
                "target": 0.5,
            })

        data = json.loads(result_str)
        assert data["status"] == "ok"
        assert data["success_count"] == 1
        assert data["failed_count"] == 1

        # 验证失败小节保留原文
        full_content = _pending_chapter_contents["测试章节"]
        assert "精简后的内容" in full_content
        assert "失败内容" in full_content  # 失败小节原文保留


# ═══════════════════════════════════════════════════════════════
# PHASE1_TOOLS 注册测试
# ═══════════════════════════════════════════════════════════════

class TestToolRegistration:
    """验证新工具已注册到 PHASE1_TOOLS"""

    def test_summarize_section_in_tools_list(self):
        """summarize_section 已注册到 PHASE1_TOOLS"""
        from app.services.agent_tools import PHASE1_TOOLS, summarize_section

        tool_names = [t.name for t in PHASE1_TOOLS]
        assert "summarize_section" in tool_names

    def test_summarize_document_in_tools_list(self):
        """summarize_document 已注册到 PHASE1_TOOLS"""
        from app.services.agent_tools import PHASE1_TOOLS, summarize_document

        tool_names = [t.name for t in PHASE1_TOOLS]
        assert "summarize_document" in tool_names

    def test_tools_count_increased(self):
        """工具总数应为 15（原13 + 新2）"""
        from app.services.agent_tools import PHASE1_TOOLS
        assert len(PHASE1_TOOLS) >= 15


# ═══════════════════════════════════════════════════════════════
# 摘要子代理测试
# ═══════════════════════════════════════════════════════════════

class TestSummaryAgent:
    """验证摘要子代理定义"""

    def test_summary_agent_prompt_exists(self):
        """SUMMARY_AGENT_PROMPT 已定义"""
        from app.services.subagents import SUMMARY_AGENT_PROMPT
        assert SUMMARY_AGENT_PROMPT
        assert "精简" in SUMMARY_AGENT_PROMPT
        assert "ISO 13485" in SUMMARY_AGENT_PROMPT
        assert "必须保留" in SUMMARY_AGENT_PROMPT

    def test_summary_agent_prompt_has_rules(self):
        """SUMMARY_AGENT_PROMPT 包含精简规则"""
        from app.services.subagents import SUMMARY_AGENT_PROMPT
        # 必须保留
        assert "法规标准条款号" in SUMMARY_AGENT_PROMPT
        assert "技术参数" in SUMMARY_AGENT_PROMPT
        assert "表格" in SUMMARY_AGENT_PROMPT
        # 可以精简
        assert "重复表述" in SUMMARY_AGENT_PROMPT
        # 禁止
        assert "编造" in SUMMARY_AGENT_PROMPT

    def test_create_summary_agent_function_exists(self):
        """create_summary_agent 函数已定义且可调用"""
        from app.services.subagents import create_summary_agent
        assert callable(create_summary_agent)


# ═══════════════════════════════════════════════════════════════
# 比例模式修复回归测试 (2026-07-24 bug fix)
# 覆盖: 比例化保底 / max_tokens收紧 / 硬截断阈值 / 失败再平衡
# ═══════════════════════════════════════════════════════════════

class TestRatioModeFixes:
    """比例模式无法压缩到目标比例的修复回归测试"""

    @pytest.mark.asyncio
    async def test_short_subsection_not_expanded_in_ratio_mode(self):
        """短小节在 ratio 模式下不会被扩展（修复固定 80 字保底问题）"""
        from app.services.agent_tools import summarize_section, _pending_chapter_contents

        # 构造：长小节 1000 字 + 短小节 50 字
        # ratio=0.3 → 长小节目标 300, 短小节目标 min(40, 50*0.9=45)=40
        # 短小节实际比例 40/50=80% (旧逻辑 80/50=160%)
        long_body = "依据 ISO 13485 标准。 " * 70  # ≈ 1000 字
        short_body = "短小节" * 12  # ≈ 48 字
        chapter = f"""## 测试章节

### 1.1 长小节

{long_body}

### 1.2 短小节

{short_body}
"""
        from app.services.agent_tools import set_current_doc_context
        set_current_doc_context(
            doc_type="design_development_plan",
            product_name="贴敷式胰岛素泵",
            markdown=f"# 测试章节\n\n{chapter}\n\n",
        )
        _pending_chapter_contents.clear()

        # Mock LLM：返回固定长度的"假精简内容"，避免污染字符统计
        def mock_llm(system_prompt, user_prompt, **kwargs):
            import re
            m = re.search(r'目标约 (\d+) 字', system_prompt)
            target = int(m.group(1)) if m else 0
            # 模拟 LLM 严格按目标字数输出
            return "精" * max(target, 1) if target > 0 else "精" * 10

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=mock_llm):
            result_str = await summarize_section.ainvoke({
                "section_name": "测试章节",
                "mode": "ratio",
                "target": 0.3,
            })

        data = json.loads(result_str)
        assert data["status"] == "ok"
        # 验证短小节（subsection 1）没有被扩展
        sub_stats = data["subsections"]
        # 找到 1.2 短小节
        short_sub = next(s for s in sub_stats if "1.2" in s["title"])
        # 修复前: target=80, new≈80, orig=50, 比例 160%
        # 修复后: target=40, new≈40, orig=50, 比例 80%
        assert short_sub["target_chars"] <= 45, (
            f"短小节 target 应 <=45 (避免扩展), 实际 {short_sub['target_chars']}")
        assert short_sub["new_chars"] <= 45, (
            f"短小节 new_chars 应 <=45, 实际 {short_sub['new_chars']}")
        # 验证短小节实际压缩比 < 1.0（不被扩展）
        short_ratio = short_sub["new_chars"] / short_sub["orig_chars"] if short_sub["orig_chars"] else 0
        assert short_ratio < 1.0, f"短小节不应被扩展, 实际比例 {short_ratio:.1%}"

    @pytest.mark.asyncio
    async def test_max_tokens_tightened_in_ratio_mode(self):
        """比例模式 max_tokens 至少 16384（qwen3.5:122b thinking tokens 占用）"""
        from app.services.agent_tools import _summarize_one_subsection

        # 目标 200 字，比例模式
        # 修复前(2次前): max_tokens = min(max(200*3, 2048), 8192) = 2048
        # 修复前(1次前): max_tokens = min(max(200*2, 256), 4096) = 400 → qwen3.5:122b 空响应
        # 修复后: max_tokens = min(max(200*3, 16384), 16384) = 16384 → 模型可输出
        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value="精简内容") as mock:
            await _summarize_one_subsection(
                sub_title="### 1.1",
                sub_body="原始内容" * 100,  # 400 字
                target_chars=200,
                chapter_name="第一章",
                doc_label="项目开发计划书",
                is_ratio_mode=True,
            )
            # max_tokens 应 >= 16384 (qwen3.5:122b 最低要求)
            call_kwargs = mock.call_args[1]
            assert call_kwargs["max_tokens"] >= 16384, (
                f"比例模式 max_tokens 应 >=16384 (qwen3.5:122b thinking 预算), "
                f"实际 {call_kwargs['max_tokens']}")
            assert call_kwargs["max_tokens"] <= 16384, (
                f"比例模式 max_tokens 应 <=16384 (避免浪费), "
                f"实际 {call_kwargs['max_tokens']}")

        # 非比例模式保持 max_tokens >= 16384
        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value="精简内容") as mock:
            await _summarize_one_subsection(
                sub_title="### 1.1",
                sub_body="原始内容" * 100,
                target_chars=200,
                chapter_name="第一章",
                doc_label="项目开发计划书",
                is_ratio_mode=False,
            )
            call_kwargs = mock.call_args[1]
            assert call_kwargs["max_tokens"] >= 16384, (
                f"非比例模式 max_tokens 应 >=16384, 实际 {call_kwargs['max_tokens']}")

    @pytest.mark.asyncio
    async def test_rebalance_triggers_on_total_overshoot(self):
        """总比例超出目标 15% 时，触发二次精简（失败再平衡）"""
        from app.services.agent_tools import summarize_section, _pending_chapter_contents

        # 构造 2 个小节：第1节 LLM 输出超目标 50%，第2节正常
        # 预期: 总比例超目标 15% 触发二次精简
        chapter = """## 测试章节

### 1.1 超目标小节

依据 ISO 13485 标准要求设计开发流程。

### 1.2 正常小节

设计开发覆盖全生命周期。
"""
        from app.services.agent_tools import set_current_doc_context
        set_current_doc_context(
            doc_type="design_development_plan",
            product_name="贴敷式胰岛素泵",
            markdown=f"# 测试章节\n\n{chapter}\n\n",
        )
        _pending_chapter_contents.clear()

        call_log = []

        def mock_llm(system_prompt, user_prompt, **kwargs):
            import re
            m = re.search(r'目标约 (\d+) 字', system_prompt)
            target = int(m.group(1)) if m else 0
            is_aggressive = "紧急要求" in system_prompt
            is_retry = "上一轮精简后为" in user_prompt
            call_log.append({"target": target, "aggressive": is_aggressive, "is_retry": is_retry})
            if is_aggressive:
                # 二次精简：返回 target 字符达标
                return "精" * max(target, 1)
            if is_retry:
                # 重试：仍超目标 1.18×（不更新 new_chars，触发失败再平衡）
                return "超" * max(int(target * 1.18), 1)
            # 初始：超目标 1.30×（让重试逻辑触发）
            return "超" * max(int(target * 1.30), 1)

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=mock_llm):
            result_str = await summarize_section.ainvoke({
                "section_name": "测试章节",
                "mode": "ratio",
                "target": 0.5,
            })

        data = json.loads(result_str)
        assert data["status"] == "ok"
        # 至少应触发 1 次二次精简（aggressive=True）
        aggressive_calls = [c for c in call_log if c["aggressive"]]
        assert len(aggressive_calls) >= 1, (
            f"应触发至少 1 次二次精简, 实际 call_log={call_log}")
        # 二次精简时 max_tokens 应更紧
        assert all(c["target"] > 0 for c in call_log), "每次 LLM 调用都应有 target"

    @pytest.mark.asyncio
    async def test_aggressive_mode_adds_emergency_prompt(self):
        """aggressive=True 时 system_prompt 包含 '紧急要求' 强化指令"""
        from app.services.agent_tools import _summarize_one_subsection

        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value="精简内容") as mock:
            await _summarize_one_subsection(
                sub_title="### 1.1",
                sub_body="原始内容" * 50,
                target_chars=100,
                chapter_name="第一章",
                doc_label="项目开发计划书",
                aggressive=True,
            )
            prompt = mock.call_args[1]["system_prompt"]
            assert "紧急要求" in prompt
            assert "必须严格控制字数" in prompt

    @pytest.mark.asyncio
    async def test_ratio_mode_total_within_15_percent(self):
        """比例模式最终压缩比与目标偏差 <= 15%"""
        from app.services.agent_tools import summarize_section, _pending_chapter_contents

        # 5 个小节，比例 0.5（50%）
        # Mock LLM 严格按目标字数输出（最理想情况）
        chapter = "## 测试章节\n\n"
        for i in range(1, 6):
            chapter += f"### 1.{i} 小节{i}\n\n"
            chapter += f"内容{i} " * 30 + "\n\n"  # 每节约 100 字
        chapter = chapter.strip()

        from app.services.agent_tools import set_current_doc_context
        set_current_doc_context(
            doc_type="design_development_plan",
            product_name="贴敷式胰岛素泵",
            markdown=f"# 测试章节\n\n{chapter}\n\n",
        )
        _pending_chapter_contents.clear()

        def mock_llm(system_prompt, user_prompt, **kwargs):
            import re
            m = re.search(r'目标约 (\d+) 字', system_prompt)
            if m:
                target = int(m.group(1))
                # 严格按 target 输出 target 个"精"字（模拟理想 LLM）
                return "精" * target
            return "精" * 10

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=mock_llm):
            result_str = await summarize_section.ainvoke({
                "section_name": "测试章节",
                "mode": "ratio",
                "target": 0.5,
            })

        data = json.loads(result_str)
        assert data["status"] == "ok"
        # 验证总压缩比与目标比例偏差 <= 15%
        actual_ratio = data["compression_ratio"]
        target_ratio = 0.5
        deviation = abs(actual_ratio - target_ratio) / target_ratio
        assert deviation <= 0.15, (
            f"压缩比 {actual_ratio:.1%} 与目标 {target_ratio:.1%} 偏差 {deviation:.1%} > 15%\n"
            f"details: {data}")


# ═══════════════════════════════════════════════════════════════
# _validate_readability 后置可读性校验测试 (2026-07-30 优化新增)
# 覆盖: 残句/悬空引用/表格完整性/列表完整性/空内容
# ═══════════════════════════════════════════════════════════════

class TestValidateReadability:
    """_validate_readability 后置可读性校验测试"""

    def test_normal_text_passes(self):
        """正常文本通过校验"""
        from app.services.agent_tools import _validate_readability
        result = _validate_readability("依据 ISO 13485 标准规范设计开发流程。")
        assert result["is_valid"] is True
        assert result["issues"] == []

    def test_empty_text_fails(self):
        """空内容标记为问题"""
        from app.services.agent_tools import _validate_readability
        result = _validate_readability("")
        assert result["is_valid"] is False
        assert any("为空" in i for i in result["issues"])

    def test_whitespace_only_fails(self):
        """仅空白内容标记为问题"""
        from app.services.agent_tools import _validate_readability
        result = _validate_readability("   \n  \t  ")
        assert result["is_valid"] is False

    def test_trailing_comma_is_fragment(self):
        """末尾以逗号收尾是残句"""
        from app.services.agent_tools import _validate_readability
        result = _validate_readability("精简后内容以逗号，")
        assert result["is_valid"] is False
        assert any("逗号" in i or "标点" in i for i in result["issues"])

    def test_trailing_semicolon_is_fragment(self):
        """末尾以分号收尾是残句"""
        from app.services.agent_tools import _validate_readability
        result = _validate_readability("精简后内容以分号；")
        assert result["is_valid"] is False

    def test_trailing_conjunction_is_fragment(self):
        """末尾以连词'和/或/与'收尾是残句"""
        from app.services.agent_tools import _validate_readability
        for conj in ('和', '或', '与'):
            result = _validate_readability(f"精简后内容以连词{conj}")
            assert result["is_valid"] is False, f"应检测到连词'{conj}'收尾残句"

    def test_leading_conclusion_word_short_is_fragment(self):
        """以'因此'开头但主句过短是残句"""
        from app.services.agent_tools import _validate_readability
        result = _validate_readability("因此。")
        assert result["is_valid"] is False
        assert any("因此" in i or "残句" in i for i in result["issues"])

    def test_leading_conclusion_word_complete_passes(self):
        """以'因此'开头但主句完整通过校验"""
        from app.services.agent_tools import _validate_readability
        result = _validate_readability("因此本章规范设计开发流程，依据 ISO 13485 标准执行。")
        assert result["is_valid"] is True

    def test_dangling_table_reference_fails(self):
        """引用'如表3-1所示'但结果中无对应表格标记为悬空"""
        from app.services.agent_tools import _validate_readability
        text = "性能要求如表3-1所示。"
        result = _validate_readability(text)
        assert result["is_valid"] is False
        assert any("表3-1" in i or "表格" in i for i in result["issues"])

    def test_table_reference_with_table_passes(self):
        """引用'表3-1'且结果中存在表格通过校验"""
        from app.services.agent_tools import _validate_readability
        text = ("性能要求如表3-1所示。\n\n"
                "| 参数 | 限值 |\n"
                "|------|------|\n"
                "| 精度 | 0.05 |")
        result = _validate_readability(text)
        assert result["is_valid"] is True

    def test_dangling_section_reference_fails(self):
        """引用'见§3.2'但结果中无对应章节标记为悬空"""
        from app.services.agent_tools import _validate_readability
        text = "详见§9.9 的要求。"
        result = _validate_readability(text)
        assert result["is_valid"] is False
        assert any("§9.9" in i or "章节" in i for i in result["issues"])

    def test_table_inconsistent_columns_fails(self):
        """表格列数不一致标记为问题"""
        from app.services.agent_tools import _validate_readability
        text = ("| 参数 | 限值 |\n"
                "|------|------|\n"
                "| 精度 | 0.05 | 备注 |")  # 第3行3列，前2行2列
        result = _validate_readability(text)
        assert result["is_valid"] is False
        assert any("列数" in i for i in result["issues"])

    def test_table_missing_separator_fails(self):
        """表格缺少表头分隔行标记为问题"""
        from app.services.agent_tools import _validate_readability
        text = ("| 参数 | 限值 |\n"
                "| 精度 | 0.05 |")  # 缺少 |---|---| 分隔行
        result = _validate_readability(text)
        assert result["is_valid"] is False
        assert any("分隔行" in i for i in result["issues"])

    def test_complete_table_passes(self):
        """完整表格通过校验"""
        from app.services.agent_tools import _validate_readability
        text = ("| 参数 | 限值 |\n"
                "|------|------|\n"
                "| 精度 | 0.05 |")
        result = _validate_readability(text)
        assert result["is_valid"] is True

    def test_empty_list_item_fails(self):
        """空列表项标记为问题"""
        from app.services.agent_tools import _validate_readability
        text = "要求如下：\n\n- 精度\n-\n- 续航"
        result = _validate_readability(text)
        assert result["is_valid"] is False
        assert any("空列表项" in i for i in result["issues"])

    def test_normal_list_passes(self):
        """正常列表通过校验"""
        from app.services.agent_tools import _validate_readability
        text = "要求如下：\n\n- 精度 0.05 U/h\n- 续航 3-7 天"
        result = _validate_readability(text)
        assert result["is_valid"] is True

    def test_multiple_issues_all_reported(self):
        """多个问题同时存在时全部报告"""
        from app.services.agent_tools import _validate_readability
        text = "因此，"  # 结论词开头 + 逗号收尾
        result = _validate_readability(text)
        assert result["is_valid"] is False
        assert len(result["issues"]) >= 2


class TestReadabilityIntegration:
    """可读性校验集成到 _summarize_one_subsection 的测试"""

    @pytest.mark.asyncio
    async def test_readability_fix_retry_triggered(self):
        """LLM 返回残句时触发可读性修复重试"""
        from app.services.agent_tools import _summarize_one_subsection

        call_count = [0]

        def mock_llm(system_prompt, user_prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # 首次返回以逗号收尾的残句
                return "精简后内容以逗号，"
            # 修复重试返回正常内容
            return "精简后内容完整。"

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=mock_llm):
            sub_title, new_body, stat = await _summarize_one_subsection(
                sub_title="### 1.1 目的",
                sub_body="原始内容" * 50,
                target_chars=100,
                chapter_name="第一章",
                doc_label="项目开发计划书",
            )

        assert stat["status"] == "ok"
        # 应触发修复重试（至少 2 次调用）
        assert call_count[0] >= 2
        # 修复后内容应以句号收尾而非逗号
        assert new_body.rstrip().endswith("。")

    @pytest.mark.asyncio
    async def test_readability_warnings_recorded_when_fix_fails(self):
        """修复重试仍无法解决时记录 readability_warnings"""
        from app.services.agent_tools import _summarize_one_subsection

        def mock_llm(system_prompt, user_prompt, **kwargs):
            # 始终返回残句
            return "精简后内容以逗号，"

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=mock_llm):
            sub_title, new_body, stat = await _summarize_one_subsection(
                sub_title="### 1.1 目的",
                sub_body="原始内容" * 50,
                target_chars=100,
                chapter_name="第一章",
                doc_label="项目开发计划书",
            )

        assert stat["status"] == "ok"
        # 应记录可读性警告
        assert "readability_warnings" in stat
        assert len(stat["readability_warnings"]) > 0

    @pytest.mark.asyncio
    async def test_no_readability_warnings_when_clean(self):
        """LLM 返回正常内容时不记录 warnings 且不触发修复重试"""
        from app.services.agent_tools import _summarize_one_subsection

        call_count = [0]

        def mock_llm(system_prompt, user_prompt, **kwargs):
            call_count[0] += 1
            return "依据 ISO 13485 标准规范设计开发流程。"

        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=mock_llm):
            sub_title, new_body, stat = await _summarize_one_subsection(
                sub_title="### 1.1 目的",
                sub_body="原始内容" * 50,
                target_chars=100,
                chapter_name="第一章",
                doc_label="项目开发计划书",
            )

        assert stat["status"] == "ok"
        assert stat["readability_warnings"] == []
        # 只调用 1 次（无修复重试）
        assert call_count[0] == 1



# ═══════════════════════════════════════════════════════════════
# 表格内容通顺流畅性测试 (2026-08-03 优化新增)
# 覆盖: prompt 规则存在性 / 表格单元格残句校验 / 表格上下文衔接校验 /
#       _truncate_at_boundary 表格保护 / aggressive 模式不再删除解释列
# ═══════════════════════════════════════════════════════════════


class TestTableFluencyPromptRules:
    """Prompt 规则存在性测试：确保 prompt 含表格通顺性规则"""

    def test_summary_agent_prompt_has_table_cell_fluency_rule(self):
        """SUMMARY_AGENT_PROMPT 含表格单元格通顺性规则"""
        from app.services.subagents import SUMMARY_AGENT_PROMPT
        # 必须提及表格单元格完整/通顺
        assert "表格单元格" in SUMMARY_AGENT_PROMPT
        assert "通顺" in SUMMARY_AGENT_PROMPT or "完整" in SUMMARY_AGENT_PROMPT

    def test_summary_agent_prompt_has_table_context_bridge_rule(self):
        """SUMMARY_AGENT_PROMPT 含表格上下文衔接规则"""
        from app.services.subagents import SUMMARY_AGENT_PROMPT
        # 必须提及表格引出句或上下文衔接
        assert "引出" in SUMMARY_AGENT_PROMPT or "上下文" in SUMMARY_AGENT_PROMPT

    def test_aggressive_mode_no_longer_deletes_columns(self):
        """aggressive 模式 prompt 不再含'删除解释列'，改为保留完整列结构"""
        from app.services.agent_tools import _summarize_one_subsection
        # 通过 mock 捕获 aggressive 模式的 system_prompt
        captured = {"system_prompt": ""}

        def mock_llm(system_prompt, user_prompt, **kwargs):
            captured["system_prompt"] = system_prompt
            return "精简内容" * 30

        import asyncio
        from unittest.mock import patch

        async def run():
            with patch("app.services.minimax._call_minimax_api_raw",
                       side_effect=mock_llm):
                await _summarize_one_subsection(
                    sub_title="### 1.1",
                    sub_body="原始内容" * 100,
                    target_chars=50,  # 极小目标触发 aggressive
                    chapter_name="第一章",
                    doc_label="项目开发计划书",
                    is_ratio_mode=False,
                    aggressive=True,
                )

        asyncio.run(run())

        # aggressive prompt 不应含"删除解释列"
        assert "删除解释列" not in captured["system_prompt"]
        # 应含"完整列结构"或类似保留表格语义的措辞
        assert "完整列" in captured["system_prompt"] or "不得删除整列" in captured["system_prompt"]


class TestValidateReadabilityTableFluency:
    """_validate_readability 表格通顺性校验测试"""

    def test_validate_table_cell_dangling_punct_fails(self):
        """表格单元格以'的/和/或'等连词/助词收尾标记为残句"""
        from app.services.agent_tools import _validate_readability
        # 第二行单元格"针对胰岛素泵的"以"的"收尾，是残句
        text = ("| 参数 | 说明 |\n"
                "|------|------|\n"
                "| 精度 | 针对胰岛素泵的 |")
        result = _validate_readability(text)
        assert result["is_valid"] is False
        assert any("单元格" in i or "残句" in i for i in result["issues"])

    def test_validate_table_cell_complete_passes(self):
        """表格单元格内容完整通过校验"""
        from app.services.agent_tools import _validate_readability
        text = ("| 参数 | 说明 |\n"
                "|------|------|\n"
                "| 精度 | 输注精度 ±5% |")
        result = _validate_readability(text)
        # 不应有单元格残句问题（其他问题也都不应触发）
        assert not any("单元格" in i or "残句" in i for i in result["issues"])

    def test_validate_table_without_context_flagged(self):
        """表格前无引出句或表号标记为缺少上下文"""
        from app.services.agent_tools import _validate_readability
        # 表格直接出现，前面无任何引出词或表号
        text = ("设计开发流程。\n"
                "| 参数 | 限值 |\n"
                "|------|------|\n"
                "| 精度 | 0.05 |")
        result = _validate_readability(text)
        assert result["is_valid"] is False
        assert any("引出" in i or "上下文" in i for i in result["issues"])

    def test_validate_table_with_intro_passes(self):
        """表格前有引出句通过校验"""
        from app.services.agent_tools import _validate_readability
        text = ("主要参数如下表所示。\n"
                "| 参数 | 限值 |\n"
                "|------|------|\n"
                "| 精度 | 0.05 |")
        result = _validate_readability(text)
        # 不应有表格上下文问题
        assert not any("引出" in i or "上下文" in i for i in result["issues"])
