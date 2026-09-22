# -*- coding: utf-8 -*-
"""extract_word_limit / get_effective_word_limit / get_word_budget_text 单元测试"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from app.services.agent_tools import (
    extract_word_limit, _cn_to_int, set_current_user_messages,
    get_effective_word_limit, get_word_budget_text, get_user_word_budget_text,
)

# ── 中文数字转换 ──
cn_cases = [
    ("五千", 5000), ("一万", 10000), ("十五", 15), ("八百", 800),
    ("两万五", 25000), ("一万二", 12000), ("三千五", 3500), ("一千", 1000),
    ("一万五千", 15000), ("二十万", 200000), ("三百", 300),
]
print("== _cn_to_int ==")
ok = True
for s, want in cn_cases:
    got = _cn_to_int(s)
    flag = "OK " if got == want else "FAIL"
    if got != want: ok = False
    print(f"{flag} {s} -> {got} (want {want})")

# ── 字数要求解析 ──
cases = [
    (["文档不超过5000字"], {"max": 5000, "min": 0}),
    (["字数控制在8000以内"], {"max": 8000, "min": 0}),
    (["五千字左右"], {"max": 5000, "min": 4000}),
    (["至少3000字"], {"max": 0, "min": 3000}),
    (["先写5000字以内，后来想想还是不超过3000字吧"], {"max": 3000, "min": 0}),
    (["不少于8000字，最多12000字"], {"max": 12000, "min": 8000}),
    (["至少8000字，不超过5000字"], {"max": 5000, "min": 0}),   # 矛盾守卫
    (["帮我生成文档"], {"max": 0, "min": 0}),
    (["一万二千字以内"], {"max": 12000, "min": 0}),
    (["三千五百字以下"], {"max": 3500, "min": 0}),
    (["500字以下"], {"max": 500, "min": 0}),
    (["二十字以内"], {"max": 0, "min": 0}),                     # <100 拒绝
    (["大约6000字"], {"max": 6000, "min": 4800}),
    (["写5000字以内", "改成不超过4000字"], {"max": 4000, "min": 0}),  # 跨消息后者覆盖
    (["不超过 7000 个字"], {"max": 7000, "min": 0}),             # 带空格+个字
    (["字数为9000"], {"max": 9000, "min": 7200}),
]
print("\n== extract_word_limit ==")
for texts, want in cases:
    got = extract_word_limit(texts)
    g = {"max": got["max"], "min": got["min"]}
    flag = "OK " if g == want else "FAIL"
    if g != want: ok = False
    print(f"{flag} {texts} -> {g} raw={got['raw']!r} (want {want})")

# ── 收敛目标 + 预算文本 ──
print("\n== get_effective_word_limit / budget text ==")
set_current_user_messages(["继续"])
assert get_effective_word_limit() == 10000, get_effective_word_limit()
assert get_user_word_budget_text() == ""
assert "10000" in get_word_budget_text() and "15000" in get_word_budget_text()
print("OK  无要求 -> 默认 10000，默认预算块含 10000/15000")

set_current_user_messages(["文档不超过5000字"])
assert get_effective_word_limit() == 5000
bt = get_word_budget_text()
assert "5000" in bt and "用户明确要求" in bt and "summarize_document" in bt
print("OK  不超过5000 -> 收敛目标 5000，预算块含用户要求")

set_current_user_messages(["至少15000字"])
assert get_effective_word_limit() == 15000, get_effective_word_limit()
bt = get_word_budget_text()
assert "15000" in bt and "不得低于" in bt
print("OK  至少15000 -> 收敛目标 15000（下限高于默认预算时抬升）")

set_current_user_messages(["至少3000字"])
assert get_effective_word_limit() == 10000  # 下限低于默认预算：仍按默认上限收敛
print("OK  至少3000 -> 收敛目标仍为默认 10000")

print("\n" + ("ALL_PASS" if ok else "HAS_FAILURES"))
