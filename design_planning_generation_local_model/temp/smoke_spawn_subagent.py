# -*- coding: utf-8 -*-
"""端到端冒烟：真实派生一个动态子代理（走 Ollama），验证完整链路"""
import sys, json, asyncio
sys.path.insert(0, '.')

async def main():
    from app.services.agent_tools import spawn_subagent
    out = json.loads(await spawn_subagent.ainvoke({
        "role_name": "标准查证员",
        "task_description": (
            "查证：ISO 13485 对设计策划（design planning）的核心条款要求是什么？"
            "用 search_kb 检索 1-2 次后，用不超过150字回答，必须标注条款号。"
        ),
        "role_instructions": (
            "你是医疗器械质量体系标准查证员。\n"
            "领域知识：ISO 13485 是医疗器械质量管理体系标准。\n"
            "工作流程：先调用 search_kb 检索，再基于检索结果作答。\n"
            "输出格式：条款号 + 一句话要求，不超过150字。"
        ),
        "allowed_tools": "search_kb",
    }))
    print("status:", out["status"])
    print("role:", out.get("role"), "| tools:", out.get("tools"), "| elapsed_s:", out.get("elapsed_s"))
    print("truncated:", out.get("truncated"))
    print("result:", str(out.get("result", out.get("message")))[:400])

asyncio.run(main())
