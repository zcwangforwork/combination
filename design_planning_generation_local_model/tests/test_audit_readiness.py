"""
test_audit_readiness.py - 审核就绪度自查工具测试（方案模块六）

覆盖:
- 前置条件: 无文档内容 / 清单文件不存在时的提示
- doc_type 过滤: "*" 通配与指定类型过滤（不适用类型不出现）
- 关键词命中判定: 全命中=满足 / 部分命中=部分满足（列出缺失关键词）/
  全未命中=缺失 / 未定义关键词=不适用（人工判定）
- 关键项 ★ 标记与常见缺陷提示
- 草稿清单状态脚注（draft_pending_ra_review 提示 RA 双人两源核对）
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services import agent_tools


def _run_check(md: str, doc_type: str = "") -> str:
    async def _inner():
        agent_tools._current_generated_markdown.set(md)
        agent_tools._current_doc_type.set(doc_type)
        return await agent_tools.check_audit_readiness.ainvoke({})
    return asyncio.run(_inner())


CHECKLIST = {
    "status": "draft_pending_ra_review",
    "items": [
        {"item_id": "AUD-X1", "clause": "【示例占位】条款A",
         "requirement": "风险闭环要求", "check_method": "查文档",
         "evidence_form": "记录", "common_defects": "剩余风险无评价结论",
         "critical": True, "keywords": ["风险可接受准则", "剩余风险"],
         "applicable_doc_types": ["*"]},
        {"item_id": "AUD-X2", "clause": "", "requirement": "软件等级要求",
         "check_method": "", "evidence_form": "", "common_defects": "",
         "critical": False, "keywords": ["软件安全等级"],
         "applicable_doc_types": ["software_requirements_spec"]},
        {"item_id": "AUD-X3", "clause": "", "requirement": "人工判定项",
         "check_method": "", "evidence_form": "", "common_defects": "",
         "critical": False, "keywords": [],
         "applicable_doc_types": ["*"]},
    ],
}


@pytest.fixture
def checklist_file(tmp_path, monkeypatch):
    p = tmp_path / "audit_checklist.json"
    p.write_text(json.dumps(CHECKLIST, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("AUDIT_CHECKLIST_PATH", str(p))
    return p


def test_no_content_message():
    out = _run_check("")
    assert "请先生成文档" in out


def test_missing_checklist_message(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_CHECKLIST_PATH",
                       str(tmp_path / "not_exist.json"))
    out = _run_check("正文内容。")
    assert "不存在" in out


def test_doc_type_filter_and_partial_hit(checklist_file):
    out = _run_check("本文档明确风险可接受准则的评分规则。",
                     doc_type="design_development_plan")
    assert "AUD-X1" in out and "AUD-X3" in out
    assert "AUD-X2" not in out            # doc_type 不匹配被过滤
    assert "部分满足" in out and "缺：剩余风险" in out
    assert "不适用" in out                 # X3 无关键词 → 人工判定
    assert "★AUD-X1" in out               # 关键项标记
    assert "剩余风险无评价结论" in out      # 关键项常见缺陷提示


def test_full_hit_marks_satisfied(checklist_file):
    out = _run_check("风险可接受准则见第3章，剩余风险评价见第5章。",
                     doc_type="design_development_plan")
    assert "满足 1" in out
    assert "缺失 0" in out


def test_no_hit_marks_missing(checklist_file):
    out = _run_check("本文档描述产品结构组成。",
                     doc_type="design_development_plan")
    assert "缺失" in out


def test_draft_status_footer(checklist_file):
    out = _run_check("风险可接受准则与剩余风险均覆盖。",
                     doc_type="design_development_plan")
    assert "draft_pending_ra_review" in out
    assert "双人两源核对" in out
