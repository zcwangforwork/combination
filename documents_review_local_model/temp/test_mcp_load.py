# -*- coding: utf-8 -*-
"""真实链路验证：连接千问 EnhancedSearch/WebFetch MCP，枚举发现的工具。
不启动服务，仅验证 mcp_manager 加载路径（配置 + .env 密钥 + adapter + 工具发现）。
"""
import asyncio
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "../backend")

from dotenv import load_dotenv
load_dotenv("../backend/.env")  # 与 run.py 同源：DASHSCOPE_API_KEY

import mcp_manager


async def main():
    tools = await mcp_manager.load_mcp_tools(exclude_names={
        "parse_document", "rag_search", "check_regulation",
        "assess_completeness", "audit_section"})
    print("加载工具数:", len(tools))
    print(json.dumps(mcp_manager.list_loaded_tools(), ensure_ascii=False, indent=2))
    print("状态:", json.dumps(mcp_manager.get_server_status(), ensure_ascii=False, indent=2))

asyncio.run(main())
