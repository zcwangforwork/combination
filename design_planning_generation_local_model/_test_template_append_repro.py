"""复现「新模板顶替旧模板」：模拟 agent_upload_template 端点的状态读写逻辑。

连续执行三次 读取→追加→写入，然后读回，验证 templates 是否累积。
使用独立的临时检查点 db，不污染生产 project_store/agent_checkpoints.db。
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def main():
    from app.services.agent_engine import init_agent, get_agent
    from app.services.agent_state import create_initial_state

    db_path = os.path.join(tempfile.gettempdir(), "repro_tpl_checkpoints.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    await init_agent(db_path=db_path)
    agent = get_agent()
    project_id = "repro-thread-001"
    config = {"configurable": {"thread_id": project_id}}

    async def upload_one(name):
        # 与 routes.py agent_upload_template 完全一致的读写逻辑
        try:
            current_state = await agent.aget_state(config)
            state_values = dict(current_state.values) if current_state and current_state.values else dict(create_initial_state())
            src = "aget_state"
        except Exception as e:
            state_values = dict(create_initial_state())
            src = f"EXCEPTION: {type(e).__name__}: {e}"

        templates = list(state_values.get("templates", []) or [])
        print(f"[upload {name}] state source = {src}; existing templates = {[t.get('name') for t in templates]}")
        templates.append({"template_id": name, "name": name})
        await agent.aupdate_state(config, {"templates": templates}, as_node="after_tools")

    await upload_one("tpl-A")
    await upload_one("tpl-B")
    await upload_one("tpl-C")

    final = await agent.aget_state(config)
    final_templates = (final.values or {}).get("templates", [])
    print(f"\nFINAL templates in state: {[t.get('name') for t in final_templates]}")
    assert [t.get("name") for t in final_templates] == ["tpl-A", "tpl-B", "tpl-C"], "REPRODUCED: templates got replaced!"


if __name__ == "__main__":
    asyncio.run(main())
