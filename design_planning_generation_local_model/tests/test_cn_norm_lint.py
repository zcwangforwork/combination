"""
test_cn_norm_lint.py - 确定性中文规范校验器测试（方案模块一 §2.3/§2.4）

覆盖:
- autofix_text 安全自动修复: P01 重复标点 / P02 句内半角 / P03 省略号 / N01 全角数字
- M 组助动词: M01 应当 / M02 应该 / M03 必须 / M04 建议+动词 / M05 口语强调词 / M06 画像
- 豁免上下文引擎: 引号内法规原文 / 修订记录表格
- P 组残余: P05 书名号未配对
- N 组: N02 单位混用与数值单位空格 / N03 概数 / N04 千分位（标准号数字段除外）
- S 组: S01 SOP 八股六章缺失与齐全 / S03 章节编号跳号
- R 组: R01 内部编号登记表命中 / R02 标准号归一化
- T 组: 术语表命中与规范形态内嵌跳过
"""
import json
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services import cn_norm_lint


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """隔离外部数据文件（规则开关/术语表/登记表），保证规则测试确定性。"""
    monkeypatch.setattr(cn_norm_lint, "CN_LINT_CONFIG_PATH",
                        str(tmp_path / "lint.json"))
    monkeypatch.setattr(cn_norm_lint, "CN_NORM_TERMS_PATH",
                        str(tmp_path / "terms.json"))
    monkeypatch.setattr(cn_norm_lint, "DOC_REGISTRY_PATH",
                        str(tmp_path / "reg.json"))
    monkeypatch.setattr(cn_norm_lint, "_DISABLED_RULES", None)
    monkeypatch.setattr(cn_norm_lint, "_TERM_CACHE", None)


def _lint(md, doc_type=""):
    return cn_norm_lint.lint_document(md, doc_type=doc_type, autofix=False)


def _rule_ids(report):
    return {v.rule_id for v in report.violations if not v.exempted}


# ───────────────────────── autofix 安全修复 ─────────────────────────

def test_autofix_duplicate_punct():
    fixed, n = cn_norm_lint.autofix_text("测试，，完成。", use_autocorrect=False)
    assert fixed == "测试，完成。" and n >= 1


def test_autofix_halfwidth_punct_in_cjk():
    fixed, _ = cn_norm_lint.autofix_text("电压过高,电流异常", use_autocorrect=False)
    assert fixed == "电压过高，电流异常"


def test_autofix_halfwidth_dot_in_cjk():
    fixed, _ = cn_norm_lint.autofix_text("测试完成.下一句", use_autocorrect=False)
    assert fixed == "测试完成。下一句"


def test_autofix_ellipsis():
    fixed, _ = cn_norm_lint.autofix_text("其余等等...", use_autocorrect=False)
    assert "……" in fixed and "..." not in fixed


def test_autofix_fullwidth_digits():
    fixed, _ = cn_norm_lint.autofix_text("共１２３件", use_autocorrect=False)
    assert fixed == "共123件"


# ───────────────────────── M 组助动词 ─────────────────────────

def test_m01_m02_m03_error_level():
    _, report = _lint("应当校准。应该记录。必须复核。")
    ids = _rule_ids(report)
    assert {"M01", "M02", "M03"} <= ids
    assert report.error_count == 3


def test_m05_warning_level():
    _, report = _lint("严禁涂改。务必执行。应确保有效。")
    assert _rule_ids(report) == {"M05"}
    assert report.error_count == 0 and report.warning_count == 3


def test_m04_suggest_with_verb():
    _, report = _lint("建议采用自动化工具生成索引。")
    assert "M04" in _rule_ids(report)
    m04 = [v for v in report.violations if v.rule_id == "M04"][0]
    assert m04.severity == "Warning"


def test_m04_exempt_in_reference_section():
    md = "# 参考资料\n\n建议采用官方文本作为编制依据。"
    _, report = _lint(md)
    assert "M04" not in _rule_ids(report)


def test_m06_modal_profile():
    _, report = _lint("应校准，不应跳过；宜复核。")
    profile = report.aux_stats.get("modal_profile", {})
    assert profile.get("应", 0) >= 2 and profile.get("宜", 0) >= 1


# ───────────────────────── 豁免上下文引擎 ─────────────────────────

def test_m01_exempted_inside_quotation():
    md = "引用原文：“企业应当具备与产品相适应的生产条件。”"
    _, report = _lint(md)
    assert report.error_count == 0
    assert report.exempted_hits.get("M01") == 1


def test_m01_exempted_in_revision_table():
    md = ("| 版本 | 修订内容 |\n"
          "|---|---|\n"
          "| V1.1 | 调整应当表述 |")
    _, report = _lint(md)
    assert report.error_count == 0
    assert report.exempted_hits.get("M01") == 1


# ───────────────────────── P/N 组 ─────────────────────────

def test_p05_unpaired_book_mark():
    _, report = _lint("见《医疗器械生产质量管理规范相关规定执行。")
    assert "P05" in _rule_ids(report)


def test_n02_unit_mixed_use():
    _, report = _lint("长度为10毫米，宽度为5 mm。")
    n02 = [v for v in report.violations if v.rule_id == "N02"]
    assert n02 and "混用" in n02[0].suggestion


def test_n02_value_unit_spacing():
    _, report = _lint("长度45mm。")
    n02 = [v for v in report.violations if v.rule_id == "N02"]
    assert n02 and "空格" in n02[0].suggestion


def test_n03_approx_number_should_be_chinese():
    _, report = _lint("试验3-5次后判定。")
    assert "N03" in _rule_ids(report)


def test_n04_thousands_separator():
    _, report = _lint("年产量约12000台。")
    assert "N04" in _rule_ids(report)


def test_n04_skips_standard_number():
    _, report = _lint("符合GB/T 42061-2022要求。")
    assert "N04" not in _rule_ids(report)
    # 无年份标准号同样不触发
    _, report2 = _lint("依据GB/T 42061编制。")
    assert "N04" not in _rule_ids(report2)


# ───────────────────────── S 组结构 ─────────────────────────

def test_s01_missing_chapters_reported():
    md = "# 目的\n控制风险。\n\n# 范围\n适用于生产。"
    _, report = _lint(md, doc_type="sop")
    s01 = [v for v in report.violations if v.rule_id == "S01"]
    assert s01 and s01[0].severity == "Error"
    for missing in ("职责", "工作程序", "相关文件", "记录"):
        assert missing in s01[0].suggestion


def test_s01_complete_six_chapters_pass():
    md = ("# 目的\n明确风险。\n\n# 范围\n适用于组装。\n\n"
          "# 职责\n质量部监督。\n\n# 工作程序\n按流程执行。\n\n"
          "# 相关文件\n见上游程序。\n\n# 记录\n表单留存。")
    _, report = _lint(md, doc_type="sop")
    assert "S01" not in _rule_ids(report)


def test_s03_numbering_discontinuity():
    md = "# 2 安装\n\n## 2.1 准备\n\n正文。\n\n## 2.3 测试\n\n正文。"
    _, report = _lint(md)
    s03 = [v for v in report.violations if v.rule_id == "S03"]
    assert s03 and "2.1" in s03[0].suggestion and "2.3" in s03[0].suggestion


# ───────────────────────── R/T 组 ─────────────────────────

def test_r01_unregistered_kf_number(tmp_path, monkeypatch):
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps(["KF-A-001"]), encoding="utf-8")
    monkeypatch.setattr(cn_norm_lint, "DOC_REGISTRY_PATH", str(reg))
    _, report = _lint("引用KF-A-001与KF-B-002文件。")
    r01 = [v for v in report.violations if v.rule_id == "R01"]
    assert len(r01) == 1 and "KF-B-002" in r01[0].suggestion


def test_r02_standard_number_normalized():
    _, report = _lint("依据GB/T42061-2022执行。")
    r02 = [v for v in report.violations if v.rule_id == "R02"]
    assert r02 and "GB/T 42061-2022" in r02[0].suggestion


def test_r02_canonical_form_not_flagged():
    _, report = _lint("依据GB/T 42061-2022执行。")
    assert "R02" not in _rule_ids(report)


def test_t01_term_map_hit(monkeypatch):
    monkeypatch.setattr(cn_norm_lint, "_TERM_CACHE",
                        {"Nmpa": "NMPA", "SO 13485": "ISO 13485"})
    _, report = _lint("由Nmpa实施审批。")
    t01 = [v for v in report.violations if v.rule_id == "T01"]
    assert t01 and "NMPA" in t01[0].suggestion


def test_t01_skips_when_embedded_in_right_form(monkeypatch):
    monkeypatch.setattr(cn_norm_lint, "_TERM_CACHE",
                        {"Nmpa": "NMPA", "SO 13485": "ISO 13485"})
    _, report = _lint("符合ISO 13485要求。")
    assert "T01" not in _rule_ids(report)


# ───────────────────────── 报告结构 ─────────────────────────

def test_report_to_dict_and_summary():
    _, report = _lint("应当校准。")
    d = report.to_dict()
    for key in ("violations", "error_count", "warning_count",
                "exempted_hits", "autofix_count", "stats"):
        assert key in d
    assert d["error_count"] == 1
    v0 = d["violations"][0]
    assert v0["rule_id"] == "M01" and v0["exempted"] is False
    assert "共 1 处违规" in report.summary_lines()[0]
