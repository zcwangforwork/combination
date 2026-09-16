"""快速验证"修改上传文档"功能（mock LLM / mock Agent 状态，无需启动服务）

覆盖:
1. modify_attachment 工具: 短文档单遍改写 + 长文档分段改写 + 结果存入旁路
2. agent_engine._after_tools_node: 把修改结果写入 attachment_modifications 状态
3. routes 新端点: 修改结果列表 / 修改版文档下载
"""
import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch


async def test_tool_single_pass():
    """短文档(<=6000字)走单遍改写"""
    import app.services.agent_tools as at

    fake_doc = "## 概述\n这是修改后的文档。\n\n## 参数\n电池寿命 3 年。\n\n@@CHANGES@@\n- 电池寿命改为3年"
    with patch.object(at, "_llm_rewrite", new=AsyncMock(return_value=fake_doc)):
        # 注入附件上下文
        at.set_current_attachments([{
            "file_id": "f1", "filename": "说明书.md",
            "full_text": "## 概述\n这是原文。\n\n## 参数\n电池寿命 2 年。\n",
            "status": "completed",
        }])
        result = await at.modify_attachment.ainvoke({
            "instruction": "把电池寿命改为3年", "file_id": "f1",
        })
    data = json.loads(result)
    assert data["status"] == "ok", data
    assert data["file_id"] == "f1"
    assert data["filename"] == "说明书.md"
    assert "电池寿命改为3年" in data["summary"], data["summary"]
    # 旁路已存完整修改后文档
    pending = at._pending_modified_documents.get("f1")
    assert pending and "修改后的文档" in pending["markdown"], pending
    print("场景1 OK: 短文档单遍改写 + 旁路存储")


async def test_tool_long_doc_sectionwise():
    """长文档(>6000字)走分段改写: 只改受影响章节，其余保留"""
    import app.services.agent_tools as at

    # 构造 3 个章节，每节内容较长凑够 >6000 字
    long_body = "这是正文段落。" * 400  # ~2800字/节
    full_text = "\n\n".join([
        f"# 第一章 概述\n{long_body}",
        f"# 第二章 参数\n{long_body}",
        f"# 第三章 结论\n{long_body}",
    ])
    assert len(full_text) > 6000

    async def fake_rewrite(system_prompt, user_prompt, timeout=180.0):
        if "只输出JSON" in system_prompt:
            # 受影响章节识别: 只改第二章
            return '{"affected": [1]}'
        if "本节原文" in user_prompt:
            # 第二章改写返回标记; 其余不应被调用
            return "# 第二章 参数\n这是修改后的第二章。\n\n@@CHANGES@@\n- 第二章已改"
        return "unexpected"

    with patch.object(at, "_llm_rewrite", new=fake_rewrite):
        at.set_current_attachments([{
            "file_id": "f2", "filename": "长文档.md", "full_text": full_text,
            "status": "completed",
        }])
        result = await at.modify_attachment.ainvoke({
            "instruction": "修改第二章", "file_id": "f2",
        })
    data = json.loads(result)
    assert data["status"] == "ok", data
    pending = at._pending_modified_documents.get("f2")
    md = pending["markdown"]
    # 第一章/第三章保留原文，第二章被替换
    assert "第一章 概述" in md and long_body in md, "第一章应保留原文"
    assert "修改后的第二章" in md, "第二章应被改写"
    assert "第二章 参数\n这是原文" not in md
    assert "第三章 结论" in md, "第三章应保留原文"
    assert "第二章已改" in data["summary"], data["summary"]
    print("场景2 OK: 长文档分段改写, 仅改受影响章节")


async def test_tool_no_attachment():
    """无附件 → 返回 error"""
    import app.services.agent_tools as at
    at.set_current_attachments([])
    result = await at.modify_attachment.ainvoke({"instruction": "x"})
    data = json.loads(result)
    assert data["status"] == "error"
    print("场景3 OK: 无附件返回 error")


async def test_after_tools_node():
    """_after_tools_node 将 modify_attachment 结果写入 attachment_modifications"""
    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
    from app.services import agent_engine as ae

    tool_output = json.dumps({
        "status": "ok", "file_id": "f1", "filename": "说明书.md",
        "modified_chars": 50, "summary": "- 改了A",
    }, ensure_ascii=False)

    state = {
        "messages": [
            HumanMessage(content="改一下"),
            AIMessage(content="", tool_calls=[{
                "id": "call_1", "name": "modify_attachment",
                "args": {"instruction": "x", "file_id": "f1"},
            }]),
            ToolMessage(content=tool_output, tool_call_id="call_1"),
        ],
        "generated_sections": {},
        "attachment_modifications": [],
    }
    with patch("app.services.agent_tools.get_pending_modified_document",
               return_value={"markdown": "# 修改后\n内容", "filename": "说明书.md"}):
        result = await ae._after_tools_node(state)

    mods = result.get("attachment_modifications", [])
    assert len(mods) == 1, result
    assert mods[0]["file_id"] == "f1"
    assert mods[0]["modified_markdown"] == "# 修改后\n内容"
    assert mods[0]["summary"] == "- 改了A"
    assert mods[0]["timestamp"]
    print("场景4 OK: _after_tools_node 写入 attachment_modifications")


async def test_routes_list_and_download():
    """新端点: 修改结果列表 + 修改版文档下载"""
    from app.services import agent_engine as ae
    from app.api import routes as r

    fake_state = MagicMock()
    fake_state.values = {
        "doc_type": "design_development_plan",
        "product_name": "测试产品",
        "attachment_modifications": [{
            "file_id": "f1", "filename": "说明书.md",
            "modified_markdown": "# 修改后\n\n正文内容",
            "summary": "- 改了A", "modified_chars": 20, "timestamp": "2026-08-10T12:00:00",
        }],
    }
    fake_agent = MagicMock()
    fake_agent.aget_state = AsyncMock(return_value=fake_state)
    ae.get_agent = MagicMock(return_value=fake_agent)

    # 列表
    resp = await r.agent_list_modified_documents("proj_test")
    assert resp["success"] is True
    assert resp["modifications"][0]["file_id"] == "f1"
    assert "modified_markdown" not in resp["modifications"][0], "列表不应包含完整Markdown"

    # 下载（mock TemplateService）
    with patch("app.services.template.TemplateService") as MockTS:
        inst = MockTS.return_value
        inst.load_template.return_value = "template"
        inst.fill_template.return_value = "filled"
        inst.document_to_bytes.return_value = b"PK\x03\x04fake-docx"
        resp2 = await r.agent_download_modified_document("proj_test", "f1")
    body = b"".join([chunk async for chunk in resp2.body_iterator])
    assert body == b"PK\x03\x04fake-docx"
    cd = resp2.headers.get("content-disposition", "")
    from urllib.parse import unquote
    assert cd.startswith("attachment; filename*=UTF-8''"), cd
    assert unquote(cd.split("''", 1)[1]) == "说明书_修改版.docx", cd
    print("场景5 OK: 修改结果列表 + 下载端点")


async def main():
    await test_tool_single_pass()
    await test_tool_long_doc_sectionwise()
    await test_tool_no_attachment()
    await test_after_tools_node()
    await test_routes_list_and_download()
    print("\nALL MODIFY-ATTACHMENT TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
