"""
test_doc_control.py - 受控文件形态底座测试（方案模块四 §5.1/§5.2 + §4.6）

覆盖:
- bump_version: minor / major / none / 非法版本号兜底
- classify_revision: 用户显式升版 major / 错字类 none / 参数类 / 法规类 / 默认 minor
  及来源枚举（用户指令/审校修复/法规变更/参数变更）
- summarize_revision: 指令前缀剥离、超长截断、空指令兜底
- build_revision_entry: 五字段结构，修订人/生效日期留空（签署时手填）
- get_reg_basis: gmp2014/gmp2025 强制指定 + auto 按施行日（2026-11-01）切换
  与前瞻性采用标注
- reg_basis_cover_line: 封面编制依据行（法规名+公告号+GB/T 42061 常挂）
"""
import sys
from datetime import date
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services import doc_control


@pytest.fixture(autouse=True)
def _auto_policy(monkeypatch):
    """REG_BASIS_DEFAULT 为 import 时读 env 的模块常量，固定为 auto 保证确定性。"""
    monkeypatch.setattr(doc_control, "REG_BASIS_DEFAULT", "auto")


# ───────────────────────── 版本号推进 ─────────────────────────

def test_bump_version_minor():
    assert doc_control.bump_version("V1.0", "minor") == "V1.1"
    assert doc_control.bump_version("V2.9", "minor") == "V2.10"


def test_bump_version_major():
    assert doc_control.bump_version("V1.7", "major") == "V2.0"
    assert doc_control.bump_version("V3.2", "major") == "V4.0"


def test_bump_version_none_keeps():
    assert doc_control.bump_version("V1.3", "none") == "V1.3"


def test_bump_version_invalid_falls_back_to_v1_0():
    assert doc_control.bump_version("垃圾", "minor") == "V1.1"
    assert doc_control.bump_version("", "major") == "V2.0"
    assert doc_control.bump_version(None, "none") == "V1.0"


# ───────────────────────── 升版动作判定 ─────────────────────────

def test_classify_empty_instruction():
    assert doc_control.classify_revision("") == ("none", doc_control.REV_SOURCE_REVIEW)


def test_classify_major_by_user_keyword():
    action, source = doc_control.classify_revision("修改关键参数输注精度")
    assert action == "major" and source == doc_control.REV_SOURCE_USER


def test_classify_none_for_typo():
    action, source = doc_control.classify_revision("更正第3章的错字")
    assert action == "none" and source == doc_control.REV_SOURCE_REVIEW


def test_classify_minor_parameter():
    action, source = doc_control.classify_revision("调整流速参数上限")
    assert action == "minor" and source == doc_control.REV_SOURCE_PARAMETER


def test_classify_minor_regulation():
    action, source = doc_control.classify_revision("按107号公告更新法规依据")
    assert action == "minor" and source == doc_control.REV_SOURCE_REGULATION


def test_classify_default_minor_user():
    action, source = doc_control.classify_revision("把阶段从5个改为7个")
    assert action == "minor" and source == doc_control.REV_SOURCE_USER


# ───────────────────────── 修订记录条目 ─────────────────────────

def test_summarize_revision_strips_prefix():
    assert doc_control.summarize_revision("请修改：把阶段从5个改为7个") == \
        "把阶段从5个改为7个"


def test_summarize_revision_truncates():
    assert doc_control.summarize_revision("很长很长很长很长很长很长很长很长很长很长很长",
                                          limit=5) == "很长很长很"


def test_summarize_revision_empty():
    assert doc_control.summarize_revision("") == "内容修订"


def test_build_revision_entry_shape():
    ent = doc_control.build_revision_entry("V1.1", "用户指令", "修改流速参数")
    assert ent == {"version": "V1.1", "source": "用户指令",
                   "summary": "修改流速参数", "revisor": "", "effective_date": ""}
    # 空 summary 兜底
    ent2 = doc_control.build_revision_entry("V1.2", "审校修复", "")
    assert ent2["summary"] == "内容修订"


def test_build_revision_entry_integrates_with_bump_and_classify():
    """典型链路：classify → bump → summarize → entry。"""
    action, source = doc_control.classify_revision("调整流速参数上限")
    version = doc_control.bump_version("V1.0", action)
    ent = doc_control.build_revision_entry(
        version, source, doc_control.summarize_revision("调整流速参数上限"))
    assert ent["version"] == "V1.1" and ent["source"] == "参数变更"


# ───────────────────────── 编制依据双轨判定 ─────────────────────────

def test_get_reg_basis_forced_gmp2014():
    b = doc_control.get_reg_basis(policy="gmp2014")
    assert b["key"] == "gmp2014" and b["status"] == "现行"


def test_get_reg_basis_forced_gmp2025_marks_unenforced():
    b = doc_control.get_reg_basis(policy="gmp2025")
    assert b["key"] == "gmp2025"
    assert "未施行" in b["status"]
    assert b["cover_line_note"] == "（2026-11-01 施行）"


def test_get_reg_basis_auto_before_effective_date():
    b = doc_control.get_reg_basis(today=date(2026, 10, 12))
    assert b["key"] == "gmp2014" and b["status"] == "现行"


def test_get_reg_basis_auto_on_effective_date():
    b = doc_control.get_reg_basis(today=date(2026, 11, 1))
    assert b["key"] == "gmp2025" and b["status"] == "现行"
    assert b["cover_line_note"] == ""   # 已施行，无前瞻性标注


def test_reg_basis_cover_line_contains_stable_parts():
    line = doc_control.reg_basis_cover_line(today=date(2026, 10, 12))
    assert "医疗器械生产质量管理规范" in line
    assert "GB/T 42061-2022" in line
