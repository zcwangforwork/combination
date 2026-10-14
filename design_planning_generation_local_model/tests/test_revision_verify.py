"""修改符合性自检测试：_verify_revision_once / _verify_revision_compliance

覆盖：
1. 首轮通过：内容不变、passed=True、无修复调用
2. 首轮未过（有额外更改）→ 带反馈修复 → 次轮通过：内容替换、repaired=True
3. 审查 JSON 解析失败：返回原内容、passed=None、不阻塞
4. 合规底线维度（compliance_violations）：单独触发修复，反馈含合规底线部分
"""
import asyncio
import json
from unittest.mock import patch

from app.services import agent_tools


def _pass_json():
    return json.dumps({"instruction_followed": True, "missing_points": [],
                       "has_unauthorized_changes": False, "unauthorized_changes": []},
                      ensure_ascii=False)


def _fail_json():
    return json.dumps({"instruction_followed": True, "missing_points": [],
                       "has_unauthorized_changes": True,
                       "unauthorized_changes": ["顺手改写了未涉及的 2.3 节措辞"]},
                      ensure_ascii=False)


def test_verify_first_round_pass():
    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value=_pass_json()) as m:
            content, report = await agent_tools._verify_revision_compliance(
                "把阶段改为7个", "原文", "修改后", "sys", "user")
            return content, report, m.call_count

    content, report, calls = asyncio.run(_run())
    assert content == "修改后"
    assert report["passed"] is True and report["rounds"] == 1
    assert report["repaired"] is False and calls == 1


def test_verify_fail_then_repair_then_pass():
    verify_results = [_fail_json(), _pass_json()]
    repair_outputs = []

    async def fake_gen(system_prompt="", user_prompt="", temperature=0.3,
                       max_tokens=16384):
        # 修复轮：确认审查反馈被拼进 user_prompt
        repair_outputs.append(user_prompt)
        return "修复后的内容"

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=lambda *a, **kw: verify_results.pop(0)), \
             patch.object(agent_tools, "_stream_llm_to_sink", new=fake_gen):
            content, report = await agent_tools._verify_revision_compliance(
                "把阶段改为7个", "原文", "修改后", "sys", "user")
            return content, report

    content, report = asyncio.run(_run())
    assert content == "修复后的内容"
    assert report["passed"] is True and report["rounds"] == 2
    assert report["repaired"] is True
    assert "超出了用户指令范围" in repair_outputs[0] and "2.3 节" in repair_outputs[0], \
        "审查反馈应拼入修复轮提示词"


def test_verify_unparseable_returns_original():
    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value="乱输出不是JSON"):
            content, report = await agent_tools._verify_revision_compliance(
                "指令", "原文", "修改后", "sys", "user")
            return content, report

    content, report = asyncio.run(_run())
    assert content == "修改后"
    assert report["passed"] is None  # 验证不可用，不阻塞


def _compliance_fail_json():
    return json.dumps({"instruction_followed": True, "missing_points": [],
                       "has_unauthorized_changes": False,
                       "unauthorized_changes": [],
                       "compliance_violations": ["第28条 被改为第29条"]},
                      ensure_ascii=False)


def test_verify_compliance_violation_alone_triggers_repair():
    """合规底线违规单独触发修复轮：即使指令已落实且无额外更改。"""
    verify_results = [_compliance_fail_json(), _pass_json()]
    repair_outputs = []

    async def fake_gen(system_prompt="", user_prompt="", temperature=0.3,
                       max_tokens=16384):
        repair_outputs.append(user_prompt)
        return "合规修复后的内容"

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   side_effect=lambda *a, **kw: verify_results.pop(0)), \
             patch.object(agent_tools, "_stream_llm_to_sink", new=fake_gen):
            content, report = await agent_tools._verify_revision_compliance(
                "指令", "原文", "修改后", "sys", "user")
            return content, report

    content, report = asyncio.run(_run())
    assert content == "合规修复后的内容"
    assert report["passed"] is True and report["rounds"] == 2
    assert report["repaired"] is True
    assert "合规底线" in repair_outputs[0] and "第28条" in repair_outputs[0], \
        "合规违规反馈应拼入修复轮提示词"


def test_verify_compliance_fail_report_fields():
    """多轮修复仍不通过时，报告含 compliance_violations 且 passed=False。"""
    async def fake_gen(**kw):
        return ""   # 修复轮返回空 → 终止循环（不触发真实 LLM 调用）

    async def _run():
        with patch("app.services.minimax._call_minimax_api_raw",
                   return_value=_compliance_fail_json()), \
             patch.object(agent_tools, "_stream_llm_to_sink", new=fake_gen):
            content, report = await agent_tools._verify_revision_compliance(
                "指令", "原文", "修改后", "sys", "user")
            return content, report

    content, report = asyncio.run(_run())
    assert content == "修改后"
    assert report["passed"] is False
    assert report["compliance_violations"] == ["第28条 被改为第29条"]
