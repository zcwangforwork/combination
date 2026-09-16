import sys, io
sys.stdout.reconfigure(encoding="utf-8")
out = io.StringIO()

import os
os.chdir(r"E:\nrf_sample_codes\working_team_work\public\project\git_project\design_plan_generation_local_model\design_planning_generation_local_model")

from app.services.agent_tools import (
    _is_general_query, _looks_like_realtime_refusal, _user_asks_realtime,
)

cases = [
    ("今天天气怎么样", True),
    ("深圳市今天的天气怎么样", True),
    ("上海明天会下雨吗", True),
    ("贴敷式胰岛素泵 风险分析 法规依据", False),
    ("ISO 13485 最新版本要求", False),
    ("GB 9706.224 适用标准", False),
    ("概述", False),
    ("设计输入", False),
]
print("=== _is_general_query ===")
allok = True
for q, exp in cases:
    got = _is_general_query(q)
    ok = got == exp
    allok = allok and ok
    print(f"  {'OK ' if ok else 'FAIL'} {q!r} -> general={got} (expected={exp})")

print("=== refusal/real-time helpers ===")
print("  refusal('我目前无法获取实时的气象数据'):", _looks_like_realtime_refusal("我目前无法获取实时的气象数据"))
print("  refusal('抱歉，我这边无法获取实时的天气数据'):", _looks_like_realtime_refusal("抱歉，我这边无法获取实时的天气数据"))
print("  refusal('这是设计开发策划书第3章'):", _looks_like_realtime_refusal("这是设计开发策划书第3章"))
print("  realtime('今天天气怎么样'):", _user_asks_realtime("今天天气怎么样"))
print("  realtime('帮我生成第3章'):", _user_asks_realtime("帮我生成第3章"))

print("=== SyncWebSearchService().search_general('深圳市今天天气怎么样') ===")
from app.services.web_search import SyncWebSearchService
svc = SyncWebSearchService()
print("  backends ddg_available=%s playwright_available=%s" % (svc.async_service.ddg_available, svc.async_service.playwright_available))
text, files = svc.search_general("深圳市今天天气怎么样", max_results=3, enable_deep_scrape=True)
print("  len=%d files=%s" % (len(text), files))
print("  ---")
print(text[:1200])
print("  ---")

sys.stdout.write(out.getvalue())
