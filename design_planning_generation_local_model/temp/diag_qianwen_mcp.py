# -*- coding: utf-8 -*-
"""千问 EnhancedSearch MCP 诊断：与运行服务完全相同的代码路径（.env + mcp_manager）"""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()
import os
key = os.environ.get("DASHSCOPE_API_KEY", "")
print(f"[1] DASHSCOPE_API_KEY: {'已加载 (' + key[:6] + '...' + key[-4:] + ', len=' + str(len(key)) + ')' if key else '未加载!'}")

from app.services import mcp_manager
print(f"[2] 配置服务器: {list(mcp_manager._load_config().keys())}")

async def main():
    print("[3] load_mcp_tools 开始（直连千问端点，30s 超时）...")
    tools = await mcp_manager.load_mcp_tools()
    print(f"[4] 状态: {mcp_manager.get_server_status()}")
    print(f"[5] 加载工具: {[t.name for t in tools]}")
    for t in tools:
        desc = (t.description or "")[:120].replace("\n", " ")
        args = list((getattr(t, "args", {}) or {}).keys())
        print(f"    - {t.name}({', '.join(args)}) : {desc}")

    # [6] 真实调用第一个搜索工具
    if tools:
        t = tools[0]
        fields = getattr(t, "args", {}) or {}
        cand = next((k for k in ("query", "keyword", "keywords", "search_query", "q", "text", "input", "question") if k in fields), None)
        if cand is None:
            cand = next((k for k, s in fields.items() if isinstance(s, dict) and s.get("type") == "string"), None)
        print(f"\n[6] 用工具 {t.name}({cand}) 实测搜索: 2026 胰岛素泵 新国标")
        try:
            r = await t.ainvoke({cand: "2026 胰岛素泵 新国标"})
            s = str(r)
            print(f"    结果预览({len(s)} chars): {s[:500]}")
        except Exception as e:
            print(f"    调用失败: {type(e).__name__}: {str(e)[:300]}")
    else:
        print("\n[6] 无工具可测——见上方状态信息")

asyncio.run(main())
