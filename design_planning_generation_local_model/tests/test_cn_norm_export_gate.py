"""
test_cn_norm_export_gate.py - 导出前置中文规范校验闸门三档测试（方案模块一 §2.5）

覆盖:
- _apply_cn_norm_gate 必须是可按位置调用的普通协程函数（内部辅助，
  build_docx 直接调用；若被 @tool 包装会 TypeError 且被外层 except
  吞掉，导致闸门静默失效——回归防护）
- off   : 跳过校验，原样返回
- warn  : 只报告不拦截（Error 存在也放行）
- enforce: 无 Error 放行 / 有 Error 前两轮返回 cn_lint_blocked /
  超轮次走 HITL 中断（accept=降级放行 / reject=中止导出），计数复位
"""
import asyncio
import inspect
import json
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services import agent_tools

BAD_MD = "整机应当完成校准，应该记录结果。"   # M01/M02 Error
GOOD_MD = "整机应完成校准并记录结果。"         # 无 Error 级违规


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    from app.services import cn_norm_lint
    monkeypatch.setattr(agent_tools, "CN_LINT_MODE", "enforce")
    agent_tools._CN_LINT_BLOCK_STATE["rounds"] = 0
    monkeypatch.setattr(cn_norm_lint, "CN_LINT_CONFIG_PATH",
                        str(tmp_path / "lint.json"))
    monkeypatch.setattr(cn_norm_lint, "CN_NORM_TERMS_PATH",
                        str(tmp_path / "terms.json"))
    monkeypatch.setattr(cn_norm_lint, "DOC_REGISTRY_PATH",
                        str(tmp_path / "reg.json"))
    monkeypatch.setattr(cn_norm_lint, "_DISABLED_RULES", None)
    monkeypatch.setattr(cn_norm_lint, "_TERM_CACHE", None)
    yield
    agent_tools._CN_LINT_BLOCK_STATE["rounds"] = 0


def _gate(md, doc_type=""):
    return asyncio.run(agent_tools._apply_cn_norm_gate(md, doc_type))


def test_gate_is_plain_coroutine_function():
    """内部辅助函数不可被 @tool 包装（BaseTool 不可按位置调用）。"""
    assert inspect.iscoroutinefunction(agent_tools._apply_cn_norm_gate)


def test_off_mode_skips_everything(monkeypatch):
    monkeypatch.setattr(agent_tools, "CN_LINT_MODE", "off")
    fixed, msg, rep = _gate(BAD_MD)
    assert msg is None and rep is None
    assert fixed == BAD_MD


def test_warn_mode_reports_without_blocking(monkeypatch):
    monkeypatch.setattr(agent_tools, "CN_LINT_MODE", "warn")
    _, msg, rep = _gate(BAD_MD)
    assert msg is None
    assert rep is not None and rep["error_count"] >= 1


def test_enforce_clean_content_passes():
    _, msg, rep = _gate(GOOD_MD)
    assert msg is None
    assert rep is not None and rep["error_count"] == 0


def test_enforce_blocks_round_1():
    _, msg, rep = _gate(BAD_MD)
    assert msg is not None
    blocked = json.loads(msg)
    assert blocked["status"] == "cn_lint_blocked"
    assert blocked["round"] == 1
    assert blocked["error_count"] >= 1
    assert agent_tools._CN_LINT_BLOCK_STATE["rounds"] == 1
    assert rep is not None


def test_enforce_blocks_round_2():
    agent_tools._CN_LINT_BLOCK_STATE["rounds"] = 1
    _, msg, _ = _gate(BAD_MD)
    blocked = json.loads(msg)
    assert blocked["status"] == "cn_lint_blocked" and blocked["round"] == 2
    assert agent_tools._CN_LINT_BLOCK_STATE["rounds"] == 2


def _patch_interrupt(monkeypatch, decision):
    import langgraph.types
    monkeypatch.setattr(langgraph.types, "interrupt", lambda payload: decision)


def test_enforce_hitl_accept_degrades_to_pass(monkeypatch):
    _patch_interrupt(monkeypatch, "accept")
    agent_tools._CN_LINT_BLOCK_STATE["rounds"] = (
        agent_tools._CN_LINT_MAX_AGENT_ROUNDS)
    _, msg, rep = _gate(BAD_MD)
    assert msg is None                      # 接受带缺陷导出 → 降级放行
    assert rep is not None and rep["error_count"] >= 1
    assert agent_tools._CN_LINT_BLOCK_STATE["rounds"] == 0   # 计数复位


def test_enforce_hitl_reject_aborts_export(monkeypatch):
    _patch_interrupt(monkeypatch, "reject")
    agent_tools._CN_LINT_BLOCK_STATE["rounds"] = (
        agent_tools._CN_LINT_MAX_AGENT_ROUNDS)
    _, msg, _ = _gate(BAD_MD)
    assert msg is not None
    rejected = json.loads(msg)
    assert rejected["status"] == "cn_lint_rejected"
    assert agent_tools._CN_LINT_BLOCK_STATE["rounds"] == 0
