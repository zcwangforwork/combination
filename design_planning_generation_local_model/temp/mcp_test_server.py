# -*- coding: utf-8 -*-
"""MCP 测试服务器（mcp SDK FastMCP）：echo + add 两个工具。

用法:
  python temp/mcp_test_server.py stdio          # stdio 传输
  python temp/mcp_test_server.py http [port]    # streamable-http 传输（默认 9123）
"""
import sys

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test-tools", host="127.0.0.1", port=int(sys.argv[2]) if len(sys.argv) > 2 else 9123)


@mcp.tool()
def echo(text: str) -> str:
    """原样返回输入文本（测试用）"""
    return f"echo:{text}"


@mcp.tool()
def add(a: int, b: int) -> int:
    """返回两数之和（测试用）"""
    return a + b


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
