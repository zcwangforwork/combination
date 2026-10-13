"""clause_citation_validator 单元测试。

覆盖：
  - extract_citations: 单/多标准号、带/不带年份、带/不带§、中英文混合、空文本
  - extract_kb_clauses: 从模拟 chunk 文本提取条款号集合
  - validate_citations: 全部核实 / 部分未核实 / KB 无条款号跳过 / 空文本兜底 / 去重
  - annotate_unverified: 标注段格式 / 未启用时原样返回 / 超限截断
"""
import sys
import os
import pytest

# 让测试可以从 backend/ 目录直接运行
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from clause_citation_validator import (
    extract_citations,
    extract_kb_clauses,
    validate_citations,
    annotate_unverified,
    _normalize_std,
)


# ============== _normalize_std ==============

class TestNormalizeStd:
    def test_iso_with_year(self):
        assert _normalize_std("ISO 14971:2019") == "ISO14971"

    def test_iso_without_year(self):
        assert _normalize_std("ISO 14971") == "ISO14971"

    def test_gbt_with_year(self):
        assert _normalize_std("GB/T 42062-2022") == "GB/T42062"

    def test_lowercase(self):
        assert _normalize_std("iso 13485:2016") == "ISO13485"

    def test_iec(self):
        assert _normalize_std("IEC 62304") == "IEC62304"


# ============== extract_citations ==============

class TestExtractCitations:
    def test_single_iso_with_section_sign(self):
        text = "差距分析：依据 ISO 14971:2019 §5.4.1，文档未识别能量危害。"
        cites = extract_citations(text)
        assert len(cites) == 1
        std_raw, clause, key, span = cites[0]
        assert std_raw == "ISO 14971:2019"
        assert clause == "5.4.1"
        assert key == "ISO14971|5.4.1"

    def test_without_section_sign(self):
        text = "依据 IEC 62304 5.6.3 要求软件单元测试。"
        cites = extract_citations(text)
        assert len(cites) == 1
        assert cites[0][1] == "5.6.3"

    def test_multiple_citations(self):
        text = (
            "ISO 14971:2019 §5.4 要求危害识别；"
            "GB/T 42062-2022 §5.5 风险估计；"
            "YY/T 0664 §5.1 软件开发计划。"
        )
        cites = extract_citations(text)
        assert len(cites) == 3
        clauses = [c[1] for c in cites]
        assert "5.4" in clauses
        assert "5.5" in clauses
        assert "5.1" in clauses

    def test_chinese_lowercase_input(self):
        text = "iso 14971 §5.4 和 iec 62304 §5.6"
        cites = extract_citations(text)
        assert len(cites) == 2

    def test_empty_text(self):
        assert extract_citations("") == []
        assert extract_citations(None) == []

    def test_no_match(self):
        text = "本章节描述了风险管理流程，无具体条款引用。"
        assert extract_citations(text) == []

    def test_nmpa_gmp(self):
        text = "依据 NMPA GMP §7.5 生产管理要求"
        cites = extract_citations(text)
        assert len(cites) == 1
        assert cites[0][1] == "7.5"

    def test_mdr_eu(self):
        text = "MDR 2017/745 Annex I §3 通用安全性能要求"
        cites = extract_citations(text)
        # MDR 2017/745 后跟 "Annex" 不是数字，不应匹配
        # 但 "MDR 2017/745 §3" 中的 §3 也不会单独匹配（无标准号前缀）
        # 实际匹配：MDR 2017/745 后面没有直接跟数字
        # 这里断言行为：MDR 模式要求标准号后紧跟条款号数字
        # "MDR 2017/745 Annex I §3" 中 MDR 2017/745 后是 "Annex"，不匹配
        assert len(cites) == 0 or cites[0][0].startswith("MDR")

    def test_fda_cfr(self):
        text = "FDA 21 CFR Part 820 §820.30 设计控制"
        cites = extract_citations(text)
        # FDA 21 CFR Part 820 后跟 §820.30，但 820.30 不是 §后接纯数字点数字
        # 实际正则 \d+(?:\.\d+)* 会匹配 820.30
        assert len(cites) >= 1

    def test_multi_level_clause(self):
        text = "ISO 13485:2016 §7.3.2.1 设计输入"
        cites = extract_citations(text)
        assert len(cites) == 1
        assert cites[0][1] == "7.3.2.1"


# ============== extract_kb_clauses ==============

class TestExtractKbClauses:
    def test_normal_kb_chunks(self):
        kb = (
            "**[iso14971.md]**\n"
            "ISO 14971:2019 §5.4 危害识别要求...\n"
            "ISO 14971:2019 §5.5 风险估计...\n"
            "ISO 14971:2019 §5.7 风险控制\n"
            "\n---\n\n"
            "**[gb42062.md]**\n"
            "GB/T 42062-2022 §5.4 危害识别\n"
        )
        clauses = extract_kb_clauses(kb)
        assert "ISO14971|5.4" in clauses
        assert "ISO14971|5.5" in clauses
        assert "ISO14971|5.7" in clauses
        assert "GB/T42062|5.4" in clauses
        assert len(clauses) == 4

    def test_empty_kb(self):
        assert extract_kb_clauses("") == set()
        assert extract_kb_clauses(None) == set()

    def test_kb_without_clauses(self):
        kb = "**[doc.md]**\n这是一段描述性文字，没有具体条款号。"
        assert extract_kb_clauses(kb) == set()


# ============== validate_citations ==============

class TestValidateCitations:
    def test_all_verified(self):
        result_content = (
            "差距分析：依据 ISO 14971:2019 §5.4 危害识别不完整；"
            "ISO 14971:2019 §5.5 风险估计方法不明确。"
        )
        section_knowledge = (
            "**[iso14971.md]**\n"
            "ISO 14971:2019 §5.4 危害识别要求\n"
            "ISO 14971:2019 §5.5 风险估计\n"
            "ISO 14971:2019 §5.6 风险评价\n"
        )
        v = validate_citations(result_content, section_knowledge)
        assert v["enabled"] is True
        assert v["total"] == 2
        assert v["verified"] == 2
        assert v["unverified"] == 0
        assert v["unverified_list"] == []

    def test_partial_unverified(self):
        result_content = (
            "依据 ISO 14971:2019 §5.4 危害识别；"
            "ISO 14971:2019 §9.9 编造的条款；"
            "IEC 62304 §5.6 软件测试。"
        )
        section_knowledge = (
            "**[iso14971.md]**\n"
            "ISO 14971:2019 §5.4 危害识别\n"
            "ISO 14971:2019 §5.5 风险估计\n"
            "IEC 62304 §5.6 软件单元测试\n"
        )
        v = validate_citations(result_content, section_knowledge)
        assert v["enabled"] is True
        assert v["total"] == 3
        assert v["verified"] == 2
        assert v["unverified"] == 1
        assert v["unverified_list"][0]["clause"] == "9.9"

    def test_kb_below_threshold_skip(self):
        result_content = "依据 ISO 14971:2019 §5.4 危害识别"
        section_knowledge = "**[doc.md]**\nISO 14971:2019 §5.4 仅一个条款"
        v = validate_citations(result_content, section_knowledge, min_kb_clauses=2)
        assert v["enabled"] is False
        assert v["total"] == 0

    def test_kb_no_clauses_skip(self):
        result_content = "依据 ISO 14971:2019 §5.4 危害识别"
        section_knowledge = "**[doc.md]**\n纯描述文字，无条款号"
        v = validate_citations(result_content, section_knowledge)
        assert v["enabled"] is False

    def test_empty_result_content(self):
        v = validate_citations("", "whatever")
        assert v["enabled"] is False
        assert v["total"] == 0

    def test_no_citations_in_result(self):
        result_content = "本章节描述了风险管理流程，无具体条款引用。"
        section_knowledge = (
            "**[iso14971.md]**\n"
            "ISO 14971:2019 §5.4 危害识别\n"
            "ISO 14971:2019 §5.5 风险估计\n"
        )
        v = validate_citations(result_content, section_knowledge)
        assert v["enabled"] is False
        assert v["total"] == 0

    def test_dedup_same_citation(self):
        result_content = (
            "ISO 14971:2019 §5.4 出现三次："
            "第一次 ISO 14971:2019 §5.4，"
            "第二次 ISO 14971:2019 §5.4，"
            "第三次 ISO 14971:2019 §5.4。"
        )
        section_knowledge = (
            "**[iso14971.md]**\n"
            "ISO 14971:2019 §5.4 危害识别\n"
            "ISO 14971:2019 §5.5 风险估计\n"
        )
        v = validate_citations(result_content, section_knowledge)
        assert v["total"] == 1  # 去重后只计一次
        assert v["verified"] == 1


# ============== annotate_unverified ==============

class TestAnnotateUnverified:
    def test_append_annotation(self):
        result_content = "审核结果：ISO 14971:2019 §9.9 编造条款。"
        validation = {
            "enabled": True,
            "total": 1,
            "verified": 0,
            "unverified": 1,
            "unverified_list": [
                {"std": "ISO 14971:2019", "clause": "9.9", "raw": "ISO 14971:2019 §9.9"}
            ],
        }
        annotated = annotate_unverified(result_content, validation)
        assert "⚠ 引用核实提示" in annotated
        assert "ISO 14971:2019 §9.9" in annotated
        assert annotated.startswith(result_content)

    def test_no_annotation_when_disabled(self):
        result_content = "审核结果"
        validation = {"enabled": False, "total": 0, "verified": 0, "unverified": 0, "unverified_list": []}
        assert annotate_unverified(result_content, validation) == result_content

    def test_no_annotation_when_all_verified(self):
        result_content = "审核结果"
        validation = {"enabled": True, "total": 2, "verified": 2, "unverified": 0, "unverified_list": []}
        assert annotate_unverified(result_content, validation) == result_content

    def test_max_annotations_truncation(self):
        result_content = "审核结果"
        unverified_list = [
            {"std": f"ISO {i}", "clause": str(i), "raw": f"ISO {i} §{i}"}
            for i in range(10)
        ]
        validation = {
            "enabled": True,
            "total": 10,
            "verified": 0,
            "unverified": 10,
            "unverified_list": unverified_list,
        }
        annotated = annotate_unverified(result_content, validation, max_annotations=3)
        assert "ISO 0 §0" in annotated
        assert "ISO 2 §2" in annotated
        assert "ISO 3 §3" not in annotated  # 被截断
        assert "其余 7 处" in annotated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
