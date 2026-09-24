# -*- coding: utf-8 -*-
"""千问 MCP 深度诊断：展开 ExceptionGroup 根因 + 环境代理检查"""
import sys, io, asyncio, os, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

print("== 环境代理变量 ==")
for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy"):
    v = os.environ.get(k)
    if v:
        print(f"  {k}={v}")
print(f"  .env CLAUDE_HTTP_PROXY={os.environ.get('CLAUDE_HTTP_PROXY', '(未设)')}")
print(f"  .env CLAUDE_HTTPS_PROXY={os.environ.get('CLAUDE_HTTPS_PROXY', '(未设)')}")

key = os.environ.get("DASHSCOPE_API_KEY", "")
print(f"\n== 直连测试 MultiServerMCPClient (key len={len(key)}) ==")

from langchain_mcp_adapters.client import MultiServerMCPClient
from app.services import mcp_manager

async def main():
    # 从配置读连接（与运行服务同源，含 ${VAR} 展开与域名修正）
    cfg = mcp_manager._load_config()
    server_name = next(iter(cfg), None)
    if not server_name:
        print("mcp_servers.json 无配置")
        return []
    conn, missing = mcp_manager._build_connection(cfg[server_name])
    if missing:
        print(f"环境变量未设置: {missing}")
        return []
    print(f"连接配置: server={server_name} url={conn.get('url')}")
    client = MultiServerMCPClient({server_name: conn})
    try:
        tools = await client.get_tools()
        print("连接成功:", [t.name for t in tools])
        return tools
    except BaseException as e:
        # 逐层展开 ExceptionGroup 直到根因
        def unwrap(exc, depth=0):
            print("  " * depth + f"{type(exc).__name__}: {str(exc)[:300]}")
            for sub in getattr(exc, "exceptions", []) or []:
                unwrap(sub, depth + 1)
            if not getattr(exc, "exceptions", None):
                tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
                # 只打最后 5 帧
                for line in tb[-5:]:
                    print("  " * depth + line.rstrip()[:160])
        unwrap(e)
        return []

asyncio.run(main())
