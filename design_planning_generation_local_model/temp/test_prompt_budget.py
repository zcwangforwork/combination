# -*- coding: utf-8 -*-
"""build_system_prompt 字数预算块集成冒烟测试"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from app.services.agent_tools import set_current_user_messages
from app.services.agent_prompt import build_system_prompt

base_state = {
    "messages": [], "doc_type": "design_development_plan",
    "product_name": "贴敷式胰岛素泵", "status": "in_progress",
}

USER_BUDGET_MARK = "全文档字数预算（重要 — 用户明确要求"

# 场景1：无字数要求（concise）→ 默认预算口径
set_current_user_messages(["继续"])
p = build_system_prompt(dict(base_state, writing_style="concise"))
assert "总字数约 10000 字" in p and "15000 字" in p, "默认预算块缺失"
assert USER_BUDGET_MARK not in p, "不应出现用户预算块"
print("OK  concise+无要求 -> 默认预算块（10000/15000）")

# 场景2：用户要求不超过5000字（concise）→ 用户预算块替换默认
set_current_user_messages(["帮我生成设计开发策划书，全文不超过5000字"])
p = build_system_prompt(dict(base_state, writing_style="concise"))
assert USER_BUDGET_MARK in p and "不超过 5000 字" in p, "用户预算块缺失"
assert "总字数约 10000 字" not in p, "默认预算块应被替换"
assert 'target=5000' in p
print("OK  concise+不超过5000字 -> 用户预算块（含 summarize target=5000）")

# 场景3：detailed 风格 + 字数要求 → 追加用户预算块
p = build_system_prompt(dict(base_state, writing_style="detailed"))
assert "严谨详细" in p and USER_BUDGET_MARK in p and "5000" in p
print("OK  detailed+字数要求 -> 追加用户预算块")

# 场景4：detailed 风格无要求 → 不追加预算块（保持原行为）
set_current_user_messages(["开始生成"])
p = build_system_prompt(dict(base_state, writing_style="detailed"))
assert "全文档字数预算" not in p
print("OK  detailed+无要求 -> 无预算块（原行为不变）")

# 场景5：min 要求 → 预算块含补写指引
set_current_user_messages(["至少8000字"])
p = build_system_prompt(dict(base_state, writing_style="concise"))
assert "不得低于 8000 字" in p and "write_chapter" in p
print("OK  至少8000字 -> 预算块含下限补写指引")

print("\nALL_PASS")
