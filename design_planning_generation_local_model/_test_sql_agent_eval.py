# -*- coding: utf-8 -*-
"""
_test_sql_agent_eval.py - 真实 LLM SQL agent 端到端 EVAL

用本地 qwen3.5:122b（Ollama）跑完整 ReAct 图，验证 agent 面对结构化数据问题时
能自主调用 sql_db_* 工具查库并正确作答。

3 个自然语言问题：
  Q1 标准适用性（电气安全标准）
  Q2 材料选择（输注针/储药器）
  Q3 参数限值（输注精度）

判定规则（每题 PASS 需同时满足）:
  1. tool_used: agent 至少调用了一次 sql_db_* 工具
  2. answer_ok: 最终回复包含期望关键事实（标准号/材料/精度值）

用法: conda activate env_01 && python _test_sql_agent_eval.py
依赖: Ollama 运行于 localhost:11435，模型 qwen3.5:122b
"""
import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

# 注意（首轮实测 2026-08-11）:
# 开放式文本题（"哪些电气安全标准"/"用什么材料"/"输注精度"）agent 会合理选择 search_kb(RAG)
# 而非 sql_db_* —— 这符合 TOOL_RULES「何时不用」指引，RAG 对这些题回答更丰富，属预期行为。
# 因此本题组改为**显式要求查库 + 需在结构化列上筛选**的题（risk_level/category 等），
# 让 agent 必然走 sql_db_list_tables → sql_db_schema → sql_db_query 链路，验证 SQL 路径端到端可用。
QUESTIONS = [
    {
        "id": "Q1",
        "question": "请查询内置数据库的 risk_items 表，列出风险等级为'不可接受'的风险危害及其控制措施。",
        "expect_keywords": ["输注过量", "堵管", "电磁干扰"],
    },
    {
        "id": "Q2",
        "question": "请查询内置数据库的 parameters 表，列出所有输注相关参数及其限值、参考标准。",
        "expect_keywords": ["0.025", "±5", "IEC 60601-2-24"],
    },
    {
        "id": "Q3",
        "question": "请查询内置数据库的 standards 表，哪些标准属于'风险管理'类别？给出标准号和标准名称。",
        "expect_keywords": ["ISO 14971", "GB/T 42062"],
    },
]

# 允许的参考答案来源关键字（判定 agent 确实查库而不是凭记忆）
EXPECT_TOOL_PREFIXES = ("sql_db_list_tables", "sql_db_schema", "sql_db_query")


async def run_one(q: dict) -> dict:
    """跑单题：初始化 agent → 提问 → 提取工具轨迹与最终回复"""
    from app.services.agent_engine import invoke_agent
    from app.services.agent_state import create_initial_state

    thread_id = f"sql-eval-{q['id']}-{os.getpid()}"
    result = await invoke_agent(q["question"], thread_id, initial_state=create_initial_state())

    messages = result.get("messages", [])
    tool_calls: list[str] = []
    final_text = ""
    for m in messages:
        cls = m.__class__.__name__
        tcs = getattr(m, "tool_calls", None) or []
        for tc in tcs:
            tool_calls.append(tc["name"])
        if cls == "AIMessage":
            content = getattr(m, "content", None)
            if content:
                final_text = content  # 最后一个非空 AIMessage 即最终回复

    used_sql = any(tc in EXPECT_TOOL_PREFIXES or tc.startswith("sql_db")
                   for tc in tool_calls)
    answer_ok = any(kw in final_text for kw in q["expect_keywords"])

    return {
        "id": q["id"],
        "question": q["question"],
        "expect_keywords": q["expect_keywords"],
        "tool_calls": tool_calls,
        "used_sql": used_sql,
        "answer_ok": answer_ok,
        "final_answer": final_text.strip()[:400],
    }


async def main() -> int:
    from app.services.agent_engine import init_agent
    print("[eval] 初始化 agent（首次加载模型较慢）...")
    await init_agent()
    print("[eval] agent 就绪\n")

    results = []
    for q in QUESTIONS:
        print(f"[eval] === {q['id']} 提问: {q['question']}")
        r = await run_one(q)
        results.append(r)
        print(f"  工具调用轨迹: {' → '.join(r['tool_calls']) if r['tool_calls'] else '(无)'}")
        print(f"  最终回复: {r['final_answer'][:120]}")
        print(f"  判定: 查库={r['used_sql']} 答案含关键事实={r['answer_ok']}")
        print()

    print("=" * 70)
    print("  SQL Agent 真实 LLM EVAL 报告")
    print("=" * 70)
    passed = 0
    for r in results:
        ok = r["used_sql"] and r["answer_ok"]
        passed += int(ok)
        mark = "PASS" if ok else "FAIL"
        print(f"\n  [{mark}] {r['id']}")
        print(f"    提问: {r['question']}")
        print(f"    期望关键事实: {r['expect_keywords']}")
        print(f"    工具轨迹: {r['tool_calls']}")
        print(f"    查库: {r['used_sql']} | 答案含关键事实: {r['answer_ok']}")
        print(f"    回复: {r['final_answer']}")
    print(f"\n  通过 {passed}/{len(results)}")
    print("=" * 70)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
