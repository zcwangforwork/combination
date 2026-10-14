"""
test_sop_chapters.py - SOP 程序文件八股六章结构一致性测试（方案模块二 §3.3）

覆盖:
- DOC_CHAPTERS["sop"] 六章齐全且按 目的/范围/职责/工作程序/相关文件/记录 顺序
- 每章 id/name/query 三字段完整
- 与 cn_norm_lint S01 规则的近义词组交叉一致（生成章节骨架可通过 S01 校验），
  防止两处定义漂移
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services import cn_norm_lint
from app.services.minimax import DOC_CHAPTERS

EXPECTED = ["目的", "范围", "职责", "工作程序", "相关文件", "记录"]


def test_sop_has_six_chapters_in_order():
    chapters = DOC_CHAPTERS["sop"]
    names = [c["name"] for c in chapters]
    assert names == EXPECTED


def test_sop_chapter_fields_complete():
    for c in DOC_CHAPTERS["sop"]:
        assert c.get("id") and c.get("name") and c.get("query")


def test_sop_chapters_cover_s01_rule_groups():
    """六章名称须命中 S01 近义词组的全部章名（跨模块一致性）。"""
    canon = [name for name, _ in cn_norm_lint._SOP_REQUIRED_CHAPTERS]
    names = [c["name"] for c in DOC_CHAPTERS["sop"]]
    missing = [c for c in canon if not any(c in n for n in names)]
    assert not missing, f"DOC_CHAPTERS['sop'] 缺少 S01 要求的章: {missing}"


def test_sop_skeleton_passes_s01(tmp_path, monkeypatch):
    """按生成章节骨架拼出的 SOP 应通过 S01 八股六章校验。"""
    monkeypatch.setattr(cn_norm_lint, "CN_LINT_CONFIG_PATH",
                        str(tmp_path / "lint.json"))
    monkeypatch.setattr(cn_norm_lint, "CN_NORM_TERMS_PATH",
                        str(tmp_path / "terms.json"))
    monkeypatch.setattr(cn_norm_lint, "DOC_REGISTRY_PATH",
                        str(tmp_path / "reg.json"))
    monkeypatch.setattr(cn_norm_lint, "_DISABLED_RULES", None)
    monkeypatch.setattr(cn_norm_lint, "_TERM_CACHE", None)
    md = "\n\n".join(f"# {c['name']}\n\n本章内容。" for c in DOC_CHAPTERS["sop"])
    _, report = cn_norm_lint.lint_document(md, doc_type="sop", autofix=False)
    assert not [v for v in report.violations
                if v.rule_id == "S01" and not v.exempted]
