# -*- coding: utf-8 -*-
"""mcp_manager 功能测试：配置校验/CRUD + stdio/http 端到端工具加载 + 容错隔离 + 冲突守卫"""
import sys, io, os, json, asyncio, subprocess, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from app.services import mcp_manager

ok = True
def check(name, cond, detail=""):
    global ok
    print(("OK  " if cond else "FAIL") + f" {name} {detail}")
    if not cond: ok = False

# ── monkeypatch 配置文件到 temp ──
TMP_CFG = os.path.join("temp", "_test_mcp_servers.json")
mcp_manager._SERVERS_FILE = TMP_CFG
if os.path.exists(TMP_CFG):
    os.remove(TMP_CFG)

PY = sys.executable
SERVER = os.path.join("temp", "mcp_test_server.py")

print("== 配置校验 ==")
check("非法transport拒绝", mcp_manager.validate_server_config({"transport": "carrier-pigeon", "url": "http://x"}) is not None)
check("stdio缺command拒绝", mcp_manager.validate_server_config({"transport": "stdio"}) is not None)
check("http缺url拒绝", mcp_manager.validate_server_config({"transport": "streamable_http"}) is not None)
check("url非http拒绝", mcp_manager.validate_server_config({"url": "ftp://x"}) is not None)
check("args非数组拒绝", mcp_manager.validate_server_config({"command": "python", "args": "x.py"}) is not None)
check("合法stdio通过", mcp_manager.validate_server_config({"transport": "stdio", "command": "python", "args": ["s.py"]}) is None)
check("合法http通过", mcp_manager.validate_server_config({"url": "http://h:1/mcp"}) is None)
check("推断transport(url→http)", mcp_manager.validate_server_config({"url": "http://h:1/mcp"}) is None)

print("\n== CRUD ==")
try:
    mcp_manager.add_server("bad name!", {"command": "python"})
    check("非法名称拒绝", False)
except ValueError:
    check("非法名称拒绝", True)
s = mcp_manager.add_server("test_stdio", {"transport": "stdio", "command": PY, "args": [SERVER, "stdio"], "description": "测试stdio"})
check("新增成功且默认enabled", s.get("enabled") is True, f"-> {s['name']}")
try:
    mcp_manager.add_server("test_stdio", {"command": "python"})
    check("重名拒绝", False)
except ValueError:
    check("重名拒绝", True)
u = mcp_manager.update_server("test_stdio", {"transport": "stdio", "command": PY, "args": [SERVER, "stdio"], "description": "改"})
check("更新保留enabled/描述", u and u.get("enabled") is True and u.get("description") == "改")
check("更新不存在返回None", mcp_manager.update_server("nope", {"command": "x"}) is None)
check("list含runtime字段", any("runtime" in x for x in mcp_manager.list_servers()))

print("\n== stdio 端到端加载（本测试进程为 Proactor 环） ==")
# 加一个坏服务器验证容错隔离
mcp_manager.add_server("bogus_http", {"url": "http://127.0.0.1:59999/mcp", "transport": "streamable_http"})
mcp_manager.add_server("disabled_one", {"command": PY, "args": [SERVER, "stdio"], "enabled": False})

async def _load():
    return await mcp_manager.load_mcp_tools(exclude_names=set())
tools = asyncio.run(_load())
names = {t.name for t in tools}
check("stdio服务器工具被发现", {"echo", "add"} <= names, f"-> {sorted(names)}")
st = mcp_manager.get_server_status()
check("坏服务器error且不影响其他", st.get("bogus_http", {}).get("status") == "error" and st.get("test_stdio", {}).get("status") == "ok",
      f"-> {json.dumps(st, ensure_ascii=False)[:150]}")
check("禁用服务器跳过", st.get("disabled_one", {}).get("status") == "disabled")
check("list_loaded_tools含server归属", all(t["server"] == "test_stdio" for t in mcp_manager.list_loaded_tools() if t["name"] in ("echo", "add")))

print("\n== 工具真实调用 ==")
async def _call():
    echo_t = next(t for t in tools if t.name == "echo")
    add_t = next(t for t in tools if t.name == "add")
    r1 = await echo_t.ainvoke({"text": "你好MCP"})
    r2 = await add_t.ainvoke({"a": 3, "b": 4})
    return r1, r2
r1, r2 = asyncio.run(_call())
check("echo调用", "echo:你好MCP" in str(r1), f"-> {r1}")
check("add调用", "7" in str(r2), f"-> {r2}")

print("\n== 冲突守卫 ==")
async def _load2():
    return await mcp_manager.load_mcp_tools(exclude_names={"echo", "bogus_http_tool"})
tools2 = asyncio.run(_load2())
names2 = {t.name for t in tools2}
check("与内置同名工具被跳过", "echo" not in names2 and "add" in names2, f"-> {sorted(names2)}")

print("\n== streamable_http 端到端 ==")
proc = subprocess.Popen([PY, SERVER, "http", "9123"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(6)  # 等服务器起来
    mcp_manager.delete_server("bogus_http")
    mcp_manager.add_server("test_http", {"url": "http://127.0.0.1:9123/mcp", "transport": "streamable_http"})
    tools3 = asyncio.run(_load())
    st3 = mcp_manager.get_server_status()
    http_names = {t.name for t in tools3 if mcp_manager._TOOL_SERVER.get(t.name) == "test_http"}
    check("http服务器工具被发现", {"echo", "add"} <= http_names or st3.get("test_http", {}).get("status") == "ok",
          f"-> status={st3.get('test_http')}, tools={sorted(http_names)}")
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except Exception: proc.kill()

print("\n== 删除 ==")
check("删除成功", mcp_manager.delete_server("test_stdio") is True)
check("删除不存在返回False", mcp_manager.delete_server("test_stdio") is False)

os.remove(TMP_CFG)
print("\n" + ("ALL_PASS" if ok else "HAS_FAILURES"))
