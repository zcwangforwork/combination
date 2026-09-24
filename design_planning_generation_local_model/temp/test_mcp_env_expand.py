# -*- coding: utf-8 -*-
"""mcp_manager ${VAR} 环境变量展开 + 千问种子配置 测试"""
import sys, io, os, json, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from app.services import mcp_manager

ok = True
def check(name, cond, detail=""):
    global ok
    print(("OK  " if cond else "FAIL") + f" {name} {detail}")
    if not cond: ok = False

# ── _build_connection 展开单元测试 ──
os.environ["TEST_MCP_KEY"] = "sk-secret123"
conn, missing = mcp_manager._build_connection({
    "transport": "streamable_http",
    "url": "https://example.com/mcp",
    "headers": {"Authorization": "Bearer ${TEST_MCP_KEY}", "X-Plain": "v"},
    "enabled": True, "description": "meta应被剥离",
})
check("已设置变量正确展开", conn["headers"]["Authorization"] == "Bearer sk-secret123", f"-> {conn['headers']}")
check("无变量header原样保留", conn["headers"]["X-Plain"] == "v")
check("管理元数据被剥离", "enabled" not in conn and "description" not in conn)
check("无缺失变量", not missing)

conn2, missing2 = mcp_manager._build_connection({
    "command": "python", "args": ["s.py"],
    "env": {"KEY": "${NOT_SET_VAR_XY}"},
})
check("缺失变量被记录", missing2 == {"NOT_SET_VAR_XY"}, f"-> {missing2}")
check("缺失变量替换为空", conn2["env"]["KEY"] == "")
del os.environ["TEST_MCP_KEY"]

# ── 缺失变量 → 加载跳过（无网络调用，明确状态）──
TMP_CFG = os.path.join("temp", "_test_mcp_env.json")
mcp_manager._SERVERS_FILE = TMP_CFG
json.dump({"needs_key": {"transport": "streamable_http", "url": "https://example.com/mcp",
                         "headers": {"Authorization": "Bearer ${NOT_SET_VAR_XY}"}}},
          open(TMP_CFG, "w", encoding="utf-8"))
tools = asyncio.run(mcp_manager.load_mcp_tools())
st = mcp_manager.get_server_status()
check("缺变量服务器被跳过", st["needs_key"]["status"] == "error" and "NOT_SET_VAR_XY" in st["needs_key"]["message"],
      f"-> {st['needs_key']['message']}")
check("无工具加载", tools == [])
os.remove(TMP_CFG)

# ── 千问种子配置（真实文件，只读验证）──
REAL_CFG = os.path.join("app", "data", "mcp_servers.json")
mcp_manager._SERVERS_FILE = REAL_CFG
cfg = mcp_manager._load_config()
check("种子配置存在且启用", "qianwen_enhanced_search" in cfg and cfg["qianwen_enhanced_search"].get("enabled") is True)
check("端点URL正确", cfg["qianwen_enhanced_search"]["url"] == "https://maas.qianwenaiapi.com/api/v1/mcps/EnhancedSearch/mcp")
check("鉴权header引用env", cfg["qianwen_enhanced_search"]["headers"]["Authorization"] == "Bearer ${DASHSCOPE_API_KEY}")

# 无 DASHSCOPE_API_KEY 时加载 → 明确提示（当前测试进程未设该变量）
os.environ.pop("DASHSCOPE_API_KEY", None)
tools = asyncio.run(mcp_manager.load_mcp_tools())
st = mcp_manager.get_server_status()
check("未配置密钥时优雅跳过", st["qianwen_enhanced_search"]["status"] == "error"
      and "DASHSCOPE_API_KEY" in st["qianwen_enhanced_search"]["message"],
      f"-> {st['qianwen_enhanced_search']['message']}")

print("\n" + ("ALL_PASS" if ok else "HAS_FAILURES"))
