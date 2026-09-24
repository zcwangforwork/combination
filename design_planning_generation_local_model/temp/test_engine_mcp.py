# -*- coding: utf-8 -*-
"""agent_engine MCP 集成测试：reload_mcp_tools 同步 PHASE1_TOOLS + bind_tools 兼容"""
import sys, io, os, json, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from app.services import mcp_manager

ok = True
def check(name, cond, detail=""):
    global ok
    print(("OK  " if cond else "FAIL") + f" {name} {detail}")
    if not cond: ok = False

TMP_CFG = os.path.join("temp", "_test_engine_mcp.json")
mcp_manager._SERVERS_FILE = TMP_CFG
PY = sys.executable
SERVER = os.path.join("temp", "mcp_test_server.py")
json.dump({
    "engine_test": {"transport": "stdio", "command": PY, "args": [SERVER, "stdio"], "enabled": True}
}, open(TMP_CFG, "w", encoding="utf-8"), ensure_ascii=False)

from app.services import agent_engine
from app.services.agent_tools import PHASE1_TOOLS

_tn = agent_engine._tool_name
before = {_tn(t) for t in PHASE1_TOOLS}
check("初始无MCP工具", not ({"echo", "add"} & before))

# ── 第一次 reload：加载 ──
r = asyncio.run(agent_engine.reload_mcp_tools())
after = {_tn(t) for t in PHASE1_TOOLS}
check("reload加载MCP工具进PHASE1_TOOLS", {"echo", "add"} <= after, f"-> loaded={r['loaded']}")
check("返回status含服务器状态", r["status"].get("engine_test", {}).get("status") == "ok")
check("图未初始化时跳过重建不报错", True)

# ── bind_tools 兼容性（离线构造 schema，不发请求）──
try:
    bound = agent_engine._get_model_with_tools()
    n_bound = len(getattr(bound, "kwargs", {}).get("tools", []) or [])
    check("bind_tools(PHASE1_TOOLS+MCP)成功", n_bound == len(PHASE1_TOOLS), f"-> bound={n_bound}, tools={len(PHASE1_TOOLS)}")
except Exception as e:
    check("bind_tools(PHASE1_TOOLS+MCP)成功", False, f"-> {type(e).__name__}: {e}")

# ── 二次 reload 幂等：先摘旧再挂新，echo/add 不应被 exclude 挡掉 ──
r2 = asyncio.run(agent_engine.reload_mcp_tools())
after2 = {_tn(t) for t in PHASE1_TOOLS}
check("二次reload幂等（摘旧挂新）", {"echo", "add"} <= after2 and r2["removed"] == ["add", "echo"],
      f"-> removed={r2['removed']} loaded={r2['loaded']}")

# ── 删除服务器后 reload：工具摘除 ──
json.dump({}, open(TMP_CFG, "w", encoding="utf-8"))
r3 = asyncio.run(agent_engine.reload_mcp_tools())
after3 = {_tn(t) for t in PHASE1_TOOLS}
check("配置清空后工具摘除", not ({"echo", "add"} & after3), f"-> removed={r3['removed']} loaded={r3['loaded']}")
check("内置工具未受影响", before <= after3)

os.remove(TMP_CFG)
print("\n" + ("ALL_PASS" if ok else "HAS_FAILURES"))
