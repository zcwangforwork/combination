# -*- coding: utf-8 -*-
"""搜索路由测试：search_priority 优先级工具 + 兜底选工具 + 提示词动态规则"""
import sys, io, os, json, asyncio, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from app.services import mcp_manager

ok = True
def check(name, cond, detail=""):
    global ok
    print(("OK  " if cond else "FAIL") + f" {name} {detail}")
    if not cond: ok = False

TMP_CFG = os.path.join("temp", "_test_search_routing.json")
mcp_manager._SERVERS_FILE = TMP_CFG
PY = sys.executable
SERVER = os.path.join("temp", "mcp_test_server.py")

# 无优先服务器时
json.dump({"plain": {"transport": "stdio", "command": PY, "args": [SERVER, "stdio"]}},
          open(TMP_CFG, "w", encoding="utf-8"))
asyncio.run(mcp_manager.load_mcp_tools())
check("无search_priority时优先列表为空", mcp_manager.get_priority_search_tools() == [])

# search_priority 服务器（用测试 stdio 服务器模拟千问：echo 只有 text 字符串参数，add 只有 int 参数）
json.dump({
    "prio_search": {"transport": "stdio", "command": PY, "args": [SERVER, "stdio"],
                    "search_priority": True, "enabled": True},
}, open(TMP_CFG, "w", encoding="utf-8"))
tools = asyncio.run(mcp_manager.load_mcp_tools())
prio = mcp_manager.get_priority_search_tools()
check("search_priority服务器工具入选", {t["name"] for t in prio} == {"echo", "add"},
      f"-> {[t['name'] for t in prio]}")
check("search_priority字段被剥离不进连接配置", "search_priority" not in mcp_manager._build_connection(
    json.load(open(TMP_CFG, encoding="utf-8"))["prio_search"])[0])

# 禁用后不入选
json.dump({
    "prio_search": {"transport": "stdio", "command": PY, "args": [SERVER, "stdio"],
                    "search_priority": True, "enabled": False},
}, open(TMP_CFG, "w", encoding="utf-8"))
check("禁用服务器不入选", mcp_manager.get_priority_search_tools() == [])
json.dump({
    "prio_search": {"transport": "stdio", "command": PY, "args": [SERVER, "stdio"],
                    "search_priority": True, "enabled": True},
}, open(TMP_CFG, "w", encoding="utf-8"))
asyncio.run(mcp_manager.load_mcp_tools())

# ── 兜底选工具（参数名自适应映射）──
from app.services import agent_engine
name, args = agent_engine._pick_forced_search_tool("最新胰岛素泵标准")
# echo(text:str)/add(a:int,b:int)：add 无字符串参数跳过 → echo + text 映射
check("兜底优先选MCP工具且参数自适应", name in ("echo", "add") and len(args) == 1,
      f"-> {name}({args})")
if name == "echo":
    check("查询词映射到text参数", args.get("text") == "最新胰岛素泵标准")

# 无优先工具时回退 web_search
json.dump({}, open(TMP_CFG, "w", encoding="utf-8"))
asyncio.run(mcp_manager.load_mcp_tools())
name2, args2 = agent_engine._pick_forced_search_tool("天气")
check("无MCP优先工具时回退web_search", name2 == "web_search" and args2 == {"query": "天气"},
      f"-> {name2}({args2})")

# ── 提示词动态规则 ──
from app.services.agent_prompt import build_system_prompt
from app.services.agent_tools import set_current_user_messages
set_current_user_messages(["继续"])
base_state = {"messages": [], "doc_type": "design_development_plan",
              "product_name": "贴敷式胰岛素泵", "status": "in_progress", "writing_style": "concise"}

p = build_system_prompt(base_state)
check("未挂载优先搜索时提示词无优先级规则", "联网搜索优先级（动态规则" not in p)

# 重新挂载优先工具 → 提示词应含动态规则
json.dump({
    "qianwen_enhanced_search": {"transport": "stdio", "command": PY, "args": [SERVER, "stdio"],
                                "search_priority": True, "enabled": True},
}, open(TMP_CFG, "w", encoding="utf-8"))
asyncio.run(mcp_manager.load_mcp_tools())
p2 = build_system_prompt(base_state)
check("挂载后提示词含搜索优先级规则", "联网搜索优先级（动态规则" in p2 and "qianwen_enhanced_search" in p2)
check("规则含回退指引", "回退调用内置 web_search" in p2)

os.remove(TMP_CFG)
print("\n" + ("ALL_PASS" if ok else "HAS_FAILURES"))
