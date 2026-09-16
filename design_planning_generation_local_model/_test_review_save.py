"""快速验证审阅页保存文档修改端点逻辑（mock Agent 状态，无需启动服务）"""
import asyncio
from unittest.mock import AsyncMock, MagicMock


async def main():
    import app.services.agent_engine as ae_mod
    from app.api.routes import agent_update_document, DocumentUpdateRequest, SectionContent

    # mock get_agent 返回带 aget_state / aupdate_state 的假 agent
    fake_state = MagicMock()
    fake_state.values = {
        "generated_sections": {"第一章": "旧内容1", "第二章": "旧内容2"},
        "product_name": "测试产品",
    }
    fake_agent = MagicMock()
    fake_agent.aget_state = AsyncMock(return_value=fake_state)
    fake_agent.aupdate_state = AsyncMock()

    ae_mod.get_agent = MagicMock(return_value=fake_agent)

    # 场景1: 修改已有章节 + 新增章节
    req = DocumentUpdateRequest(sections=[
        SectionContent(title="第一章", content="## 修改后的第一章\n新内容"),
        SectionContent(title="第二章", content="第二章内容"),
        SectionContent(title="第三章", content="新增章节内容"),
    ])
    result = await agent_update_document("proj_test", req)
    assert result["success"] is True
    assert result["sections_updated"] == 3

    # 验证 aupdate_state 写入的内容
    call_args = fake_agent.aupdate_state.call_args
    config, payload = call_args[0]
    assert payload == {"generated_sections": {
        "第一章": "## 修改后的第一章\n新内容",
        "第二章": "第二章内容",
        "第三章": "新增章节内容",
    }}
    print("场景1 OK: 修改+新增章节, sections_updated=3")

    # 场景2: 空 title 章节被跳过
    fake_agent.aupdate_state.reset_mock()
    req2 = DocumentUpdateRequest(sections=[
        SectionContent(title="  ", content="空标题应跳过"),
        SectionContent(title="第一章", content="有效内容"),
    ])
    result2 = await agent_update_document("proj_test", req2)
    assert result2["sections_updated"] == 1
    payload2 = fake_agent.aupdate_state.call_args[0][1]
    assert list(payload2["generated_sections"].keys()) == ["第一章"]
    print("场景2 OK: 空标题跳过")

    # 场景3: 全部为空 → 400
    req3 = DocumentUpdateRequest(sections=[
        SectionContent(title="", content="x"),
        SectionContent(title=" ", content="y"),
    ])
    try:
        await agent_update_document("proj_test", req3)
        raise AssertionError("应当抛出 HTTP 400")
    except Exception as e:
        assert getattr(e, "status_code", None) == 400, f"期望400, 实际 {e}"
        print("场景3 OK: 空章节全部跳过 → 400")

    # 场景4: 项目不存在 → 404
    ae_mod.get_agent = MagicMock(return_value=MagicMock(aget_state=AsyncMock(return_value=None)))
    req4 = DocumentUpdateRequest(sections=[SectionContent(title="第一章", content="内容")])
    try:
        await agent_update_document("proj_test", req4)
        raise AssertionError("应当抛出 HTTP 404")
    except Exception as e:
        assert getattr(e, "status_code", None) == 404, f"期望404, 实际 {e}"
        print("场景4 OK: 项目不存在 → 404")

    print("\nALL TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
