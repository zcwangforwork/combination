"""
API Routes - 文档生成接口（异步任务模式）+ 附件上传接口
"""

import uuid
import asyncio
import threading
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.services.generator import DocumentGenerator
from app.services.doc_types import DOC_TYPE_LABELS, DOC_CATEGORIES, SUPPORTED_UPLOAD_FORMATS, MAX_UPLOAD_SIZE_BYTES
from app.services.attachment_service import (
    validate_upload, submit_extract_task, get_extract_status
)
from app.services.conversation import conversation_manager
import io
import json
import os
import re
import time
import zipfile
from typing import Optional, List
from urllib.parse import quote

router = APIRouter()


class GenerateRequest(BaseModel):
    """文档生成请求"""
    doc_type: str = Field(..., description="文档类型")
    product_name: str = Field(..., description="产品名称")
    product_type: str = Field(default="", description="产品类型，如：有源医疗器械")
    product_params: str = Field("", description="产品参数详情")
    file_ids: Optional[List[str]] = Field(None, description="已入库附件的file_id列表")
    attachment_content: Optional[str] = Field(None, description="临时附件的提取文本内容")


class SectionContent(BaseModel):
    """审阅页文档章节内容（title 为章节名，content 为 Markdown 文本）"""
    title: str = Field(..., description="章节标题")
    content: str = Field("", description="章节 Markdown 内容")


class DocumentUpdateRequest(BaseModel):
    """审阅页保存文档修改请求（整体替换 generated_sections）"""
    sections: List[SectionContent] = Field(..., description="修改后的章节列表（保留原顺序）")


# 内存中的任务存储
tasks = {}  # task_id -> {status, progress, message, file_bytes, filename, created_at}


def _run_generation(task_id: str, doc_type: str, product_name: str, product_type: str, product_params: str, file_ids: Optional[List[str]] = None, attachment_content: Optional[str] = None):
    """在后台线程中执行文档生成"""
    try:
        tasks[task_id]["status"] = "generating"
        tasks[task_id]["progress"] = 5
        tasks[task_id]["message"] = "正在生成文档结构大纲..."

        # 进度回调：根据阶段更新任务状态
        def on_progress(phase, current, total, message):
            if phase == "outline":
                progress = 10
            elif phase == "rag":
                # RAG阶段占 10-30%
                progress = 10 + int(20 * current / max(total, 1))
            elif phase == "generate":
                # 生成阶段占 30-95%
                progress = 30 + int(65 * current / max(total, 1))
            else:
                progress = 10
            tasks[task_id]["progress"] = min(progress, 95)
            tasks[task_id]["message"] = message

        generator = DocumentGenerator(progress_callback=on_progress)

        # 同步生成文档（在线程中运行，不阻塞事件循环）
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            file_bytes = loop.run_until_complete(
                generator.generate(
                    doc_type=doc_type,
                    product_name=product_name,
                    product_type=product_type,
                    product_params=product_params,
                    file_ids=file_ids,
                    attachment_content=attachment_content
                )
            )
        finally:
            loop.close()

        # 生成文件名
        label = DOC_TYPE_LABELS.get(doc_type, doc_type)
        filename = f"{product_name}_{label}.docx"

        # 创建会话，保存生成的内容供后续修订
        session_id = conversation_manager.create_session(
            doc_type=doc_type,
            product_name=product_name,
            product_type=product_type,
            product_params=product_params,
            doc_content=generator.last_generated_content
        )

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "文档生成完成！"
        tasks[task_id]["file_bytes"] = file_bytes
        tasks[task_id]["filename"] = filename
        tasks[task_id]["search_log"] = generator.search_log
        tasks[task_id]["timing_log"] = generator.timing_log
        tasks[task_id]["session_id"] = session_id
        tasks[task_id]["doc_content"] = generator.last_generated_content

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["progress"] = 0
        tasks[task_id]["message"] = f"生成失败: {str(e)}"


@router.post("/generate")
async def generate_document(request: GenerateRequest):
    """
    提交文档生成任务（异步）

    立即返回任务ID，文档在后台生成，前端通过 /api/status/{task_id} 轮询进度
    """
    # 验证必填字段
    if not request.product_name.strip():
        raise HTTPException(status_code=400, detail="产品名称不能为空")

    # 创建任务
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "message": "任务已创建，等待生成...",
        "file_bytes": None,
        "filename": "",
        "created_at": time.time()
    }

    # 启动后台线程
    thread = threading.Thread(
        target=_run_generation,
        args=(task_id, request.doc_type, request.product_name, request.product_type, request.product_params, request.file_ids, request.attachment_content),
        daemon=True
    )
    thread.start()

    return {"task_id": task_id, "status": "pending", "message": "任务已提交"}


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """查询任务状态"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = tasks[task_id]
    result = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "message": task["message"],
        "filename": task.get("filename", ""),
        "search_log": task.get("search_log", []),
        "timing_log": task.get("timing_log", {})
    }
    # 生成完成时返回 session_id 供前端进入修订模式
    if task["status"] == "completed" and task.get("session_id"):
        result["session_id"] = task["session_id"]
    return result


@router.get("/download/{task_id}")
async def download_document(task_id: str):
    """下载生成的文档"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = tasks[task_id]

    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="文档尚未生成完成")

    if not task["file_bytes"]:
        raise HTTPException(status_code=500, detail="文档数据为空")

    encoded_filename = quote(task["filename"])

    return StreamingResponse(
        io.BytesIO(task["file_bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


# ==================== 数字员工交互式修订接口 ====================

class ReviseRequest(BaseModel):
    """文档修订请求"""
    session_id: str = Field(..., description="会话ID（从首次生成返回）")
    feedback: str = Field(..., description="用户修改意见")


@router.post("/revise")
async def revise_document(request: ReviseRequest):
    """
    基于用户反馈修订文档（数字员工交互模式）

    提交修改意见，返回修订后的文档
    """
    session = conversation_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    if not request.feedback.strip():
        raise HTTPException(status_code=400, detail="反馈意见不能为空")

    # 记录反馈并创建版本快照
    version_label = conversation_manager.add_feedback(request.session_id, request.feedback)

    # 在后台执行修订
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        "status": "revising",
        "progress": 0,
        "message": "正在根据反馈修订文档...",
        "file_bytes": None,
        "filename": "",
        "session_id": request.session_id,
        "created_at": time.time()
    }

    thread = threading.Thread(
        target=_run_revision,
        args=(task_id, request.session_id, request.feedback),
        daemon=True
    )
    thread.start()

    return {"task_id": task_id, "status": "revising", "message": "修订任务已提交", "version": version_label}


def _run_revision(task_id: str, session_id: str, feedback: str):
    """在后台线程中执行文档修订"""
    try:
        tasks[task_id]["status"] = "revising"
        tasks[task_id]["progress"] = 20
        tasks[task_id]["message"] = "正在根据反馈修订文档..."

        session = conversation_manager.get_session(session_id)
        if not session:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["message"] = "会话不存在"
            return

        generator = DocumentGenerator()

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            file_bytes = loop.run_until_complete(
                generator.revise(
                    current_content=session.current_content,
                    feedback=feedback,
                    doc_type=session.doc_type,
                    product_name=session.product_name,
                    product_type=session.product_type,
                    product_params=session.product_params
                )
            )
        finally:
            loop.close()

        # 更新会话中的文档内容
        conversation_manager.update_content(session_id, generator.last_generated_content)

        # 将差异数据写入版本快照，供前端展示修订对比
        if generator.last_diff_data:
            conversation_manager.set_version_diff(session_id, generator.last_diff_data)

        label = DOC_TYPE_LABELS.get(session.doc_type, session.doc_type)
        filename = f"{session.product_name}_{label}_修订版.docx"

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "文档修订完成！"
        tasks[task_id]["file_bytes"] = file_bytes
        tasks[task_id]["filename"] = filename

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["progress"] = 0
        tasks[task_id]["message"] = f"修订失败: {str(e)}"


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取数字员工会话状态"""
    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return session.to_dict()


@router.get("/session/{session_id}/download")
async def download_session_document(session_id: str):
    """
    下载会话当前的文档版本

    根据会话中的最新内容重新生成 Word 文件并返回
    """
    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    from app.services.template import TemplateService
    template_service = TemplateService()

    doc = template_service.load_template(session.doc_type)
    doc = template_service.fill_template(
        doc=doc,
        content=session.current_content,
        product_name=session.product_name,
        doc_type=session.doc_type
    )
    file_bytes = template_service.document_to_bytes(doc)

    label = DOC_TYPE_LABELS.get(session.doc_type, session.doc_type)
    v = session.version_count
    filename = f"{session.product_name}_{label}_v{v}.docx"
    encoded_filename = quote(filename)

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/doc-types")
async def get_doc_types():
    """获取支持的文档类型列表 — 贴敷式胰岛素泵全生命周期94+种文档"""
    types = []
    for cat_key, cat_info in DOC_CATEGORIES.items():
        for doc_type in cat_info["types"]:
            label = DOC_TYPE_LABELS.get(doc_type, doc_type)
            types.append({
                "value": doc_type,
                "label": label,
                "category": cat_info["name"],
                "category_key": cat_key,
                "description": cat_info["description"]
            })
    return {
        "types": types,
        "categories": [
            {
                "key": cat_key,
                "name": cat_info["name"],
                "description": cat_info["description"],
                "icon": cat_info["icon"],
                "count": len(cat_info["types"])
            }
            for cat_key, cat_info in DOC_CATEGORIES.items()
        ]
    }


# ==================== 附件上传接口 ====================

@router.post("/upload")
async def upload_attachment(
    file: UploadFile = File(..., description="附件文件 (.docx/.pdf/.txt 等，启用 MinerU 后扩展支持 .doc/.ppt/.pptx/.xls/.xlsx/图片/.html)"),
    persist: bool = Form(False, description="是否存入知识库供后续复用")
):
    """
    上传附件文档，提交后台提取任务

    返回 file_id，前端通过 GET /api/extract-status/{file_id} 轮询提取进度
    """
    # 验证格式和大小
    file_content = await file.read()
    is_valid, error_msg = validate_upload(file.filename, len(file_content))
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # 提交后台提取任务
    task_id = submit_extract_task(
        file_content=file_content,
        filename=file.filename,
        persist=persist,
        doc_type="unknown"
    )

    return {
        "file_id": task_id,
        "filename": file.filename,
        "status": "pending",
        "message": "文件已接收，正在后台提取文本..."
    }


@router.get("/extract-status/{file_id}")
async def get_extract_task_status(file_id: str):
    """查询附件提取任务状态"""
    status = get_extract_status(file_id)
    if status is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return status


@router.get("/kb/files")
async def list_kb_files():
    """列出上传知识库（qms_doc_uploads）中的所有文件及其统计信息"""
    try:
        from app.services.rag.vector_store import VectorStore
        store = VectorStore(collection_name="uploads")
        files = store.list_uploaded_files()
        return {
            "status": "ok",
            "count": len(files),
            "files": files,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询知识库文件列表失败: {str(e)}")


class KbFileDeleteRequest(BaseModel):
    """删除知识库文件请求"""
    source_file: str = Field(..., description="要删除的文件在知识库中的 source_file 标识")


class KbToAttachmentRequest(BaseModel):
    """将知识库文件加入当前会话附件的请求"""
    source_file: str = Field(..., description="知识库文件的 source_file 标识（用于读回全文）")
    file_id: str = Field(default="", description="知识库文件的 file_id，作为新附件 file_id；缺省时回退为 source_file")
    filename: str = Field(default="", description="附件展示名；缺省时取 source_file 的文件名")


class KbChatRequest(BaseModel):
    """知识库问答请求"""
    question: str = Field(..., description="用户对知识库文件提出的问题")


@router.post("/kb/chat")
async def kb_chat(payload: KbChatRequest):
    """知识库问答：检索 uploads 知识库相关片段，用本地 LLM 基于检索结果回答。

    非流式返回 {answer, sources}，sources 为命中的来源文件及片段摘要，
    供前端展示引用。
    """
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="缺少 question 参数")

    from app.services.rag.vector_store import VectorStore
    from app.services.minimax import _call_minimax_api_raw

    # 1) 检索 uploads 知识库（与 search_kb 的 uploads 检索一致）
    try:
        store = VectorStore(collection_name="uploads")
        count = store.collection.count()
        if count == 0:
            return {"answer": "知识库中暂无文件，请先上传文件后再提问。", "sources": []}
        query_embedding = store.embedder.encode_single(question)
        top_k = 6
        raw = store.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        if not raw or not raw.get("ids") or not raw["ids"][0]:
            return {"answer": "未在知识库中检索到相关内容，请换一种问法或补充相关文件。", "sources": []}

        results = []
        for i in range(len(raw["ids"][0])):
            distance = raw["distances"][0][i]
            similarity = max(0.0, 1.0 - distance / 2.0)
            meta = raw["metadatas"][0][i] or {}
            results.append({
                "text": raw["documents"][0][i],
                "source_file": meta.get("source_file", "用户上传文件"),
                "score": round(similarity, 3),
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"知识库检索失败: {str(e)}")

    # 2) 组装上下文 + LLM 回答
    context_parts = []
    for i, r in enumerate(results, 1):
        context_parts.append(f"[片段{i}·来源 {r['source_file']}·相关度 {r['score']}]\n{r['text']}")
    context = "\n\n".join(context_parts)

    system_prompt = (
        "你是知识库问答助手。请基于用户提供的知识库检索片段回答用户问题，"
        "回答准确、精炼，并注明结论来自哪个文件。"
        "若检索片段不足以回答，请明确说明'知识库中暂未找到足够信息'，不要编造。"
        "用中文回答。"
    )
    user_prompt = f"用户问题：{question}\n\n知识库检索到的相关片段：\n{context}\n\n请基于以上片段回答。"

    try:
        answer = _call_minimax_api_raw(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
            timeout=(30, 120),
        )
        answer = (answer or "").strip() or "知识库问答生成失败，请稍后重试。"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"知识库问答生成失败: {str(e)}")

    # 去重来源文件（按原顺序保留）
    seen = set()
    sources = []
    for r in results:
        if r["source_file"] not in seen:
            seen.add(r["source_file"])
            sources.append({"source_file": r["source_file"], "score": r["score"]})

    return {"answer": answer, "sources": sources}


@router.post("/kb/files/delete")
async def delete_kb_file(payload: KbFileDeleteRequest):
    """从上传知识库（qms_doc_uploads）删除指定文件的所有分块。

    删除键为 source_file（每个 chunk 的 metadata.source_file，list 接口已返回该字段）。
    删除后使对应 collection 的 BM25 缓存失效，确保检索不再命中已删文件。
    """
    source_file = (payload.source_file or "").strip()
    if not source_file:
        raise HTTPException(status_code=400, detail="缺少 source_file 参数")
    try:
        from app.services.rag.vector_store import VectorStore
        store = VectorStore(collection_name="uploads")
        store.delete_by_source(source_file)
        VectorStore.invalidate_bm25_cache("qms_doc_uploads")
        return {"status": "ok", "deleted": source_file}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除知识库文件失败: {str(e)}")


@router.get("/debug/env")
async def debug_env():
    """调试端点 - 检查环境变量"""
    api_key = os.getenv("MINIMAX_API_KEY", "")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen3.5:122b")
    ollama_embed = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    return {
        "api_key_set": bool(api_key),
        "ollama_base_url": ollama_url,
        "ollama_model": ollama_model,
        "ollama_embed_model": ollama_embed,
        "env_file_loaded": os.path.exists(".env"),
        "cwd": os.getcwd()
    }


@router.get("/debug/test-api")
async def test_api():
    """测试 MiniMax API 调用"""
    from app.services.minimax import MiniMaxService
    service = MiniMaxService()
    try:
        result = service.generate_content(
            doc_type="risk_management_report",
            product_name="测试产品",
            product_type="有源医疗器械",
            product_params="测试参数"
        )
        return {"success": True, "result": result[:500] if result else "empty"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# Agent API — 设计策划文档写作Agent (LangGraph)
# ═══════════════════════════════════════════════════════════════

from fastapi.responses import StreamingResponse
import json


# ── 后台生成流（执行与 SSE 连接解耦）公共辅助 ──
# 生成任务在后台 asyncio task 中执行（app/services/agent_streams.py），
# SSE 响应只订阅转发事件：客户端断开（切换聊天任务/刷新页面）不再中断生成，
# 切回后可通过 GET /stream 重连续播。

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _count_history_messages(state_values: dict) -> int:
    """统计状态中 /history 端点会展示的消息条数（有文本的 Human/AI 消息）。

    后台流的 meta.history_count 记录「本轮生成开始前」的历史条数，
    前端重连续播时据此只渲染本轮之前的历史，避免与回放事件重复。
    """
    from langchain_core.messages import HumanMessage, AIMessage
    count = 0
    for msg in (state_values or {}).get("messages", []) or []:
        if isinstance(msg, (HumanMessage, AIMessage)):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content and content.strip():
                count += 1
    return count


def _sse_error_response(message: str):
    """构造只含一条 error 事件即结束的 SSE 响应。"""
    async def _stream():
        yield f"data: {json.dumps({'type': 'error', 'message': message}, ensure_ascii=False)}\n\n"
    return StreamingResponse(_stream(), media_type="text/event-stream", headers=dict(_SSE_HEADERS))


def _sse_busy_response():
    """该项目已有进行中生成时的 SSE 响应（防止重复提交）。"""
    return _sse_error_response("该任务已有正在进行的生成，请等待完成，或切回该任务查看实时进度")


def _sse_subscribe_response(stream, from_seq: int = 0):
    """构造订阅后台生成流的 SSE 响应。

    客户端断开仅结束本次订阅（生成器被取消），后台生成任务不受影响。
    """
    from app.services import agent_streams

    async def event_stream():
        try:
            async for event in agent_streams.subscribe_stream(stream, from_seq=from_seq):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=dict(_SSE_HEADERS),
    )


@router.post("/agent/projects/{project_id}/messages")
async def agent_send_message(
    project_id: str,
    message: str = Form(...),
):
    """发送消息到Agent，返回SSE事件流

    生成在后台任务中执行（与本连接解耦）：切换聊天任务/刷新页面不会中断
    生成，切回后可通过 GET /stream/status + GET /stream 重连续播。

    事件类型:
    - token: LLM逐token输出 → 前端打字机效果
    - tool_start: 工具调用开始 → 前端展示图标
    - tool_end: 工具调用结束 → 前端展示结果预览
    - waiting_approval: HITL暂停 → 前端展示确认按钮
    - done: 流结束
    - error: 异常，或该项目已有进行中的生成
    """
    from app.services.agent_engine import stream_agent_events, get_agent
    from app.services.agent_state import create_initial_state
    from app.services import agent_streams

    if agent_streams.get_active_stream(project_id):
        return _sse_busy_response()

    # 仅首次消息传入初始状态。已有 checkpoint 时不传 initial_state，
    # 让 LangGraph 从 checkpoint 恢复，避免 create_initial_state() 覆盖附件等已有状态
    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}
    try:
        existing = await agent.aget_state(config)
    except Exception as e:
        return _sse_error_response(f"读取Agent状态失败: {e}")
    has_checkpoint = existing is not None and bool(existing.values)
    initial_state = create_initial_state() if not has_checkpoint else None
    history_count = _count_history_messages(existing.values if has_checkpoint else {})

    stream = agent_streams.start_stream(
        project_id,
        kind="message",
        source_factory=lambda: stream_agent_events(
            user_message=message,
            thread_id=project_id,
            initial_state=initial_state,
        ),
        meta={"history_count": history_count, "user_message": message},
    )
    return _sse_subscribe_response(stream, from_seq=0)


@router.get("/agent/projects/{project_id}/stream/status")
async def agent_stream_status(project_id: str):
    """查询项目后台生成流状态（前端页面加载/切回任务时决定是否重连续播）

    返回:
    - exists: 是否存在流记录（进行中的或刚结束尚未过期的）
    - active: 是否正在生成中
    - kind: 流类型 message | resume | auto-generate
    - status: running | done | error | cancelled
    - seq: 下一条事件的序号（已产生的事件总数）
    - history_count: 本轮生成开始前的历史消息条数（重连时前端只渲染此前的历史）
    - user_message: 本轮用户消息文本（重连时前端补渲染用户气泡；resume 为空）
    """
    from app.services import agent_streams
    return agent_streams.get_status(project_id)


@router.get("/agent/projects/{project_id}/stream")
async def agent_stream_reconnect(project_id: str, from_seq: int = 0):
    """重连项目后台生成流：回放已缓冲事件并继续实时订阅

    用于切换聊天任务后切回、或刷新页面时恢复正在进行的生成过程展示。
    客户端断开仅结束本次订阅，后台生成不受影响。
    无流记录时返回单条 done 事件（reason=no_stream）即结束。
    """
    from app.services import agent_streams

    stream = agent_streams.get_stream(project_id)
    if stream is None:
        async def no_stream():
            yield f"data: {json.dumps({'type': 'done', 'reason': 'no_stream'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(no_stream(), media_type="text/event-stream", headers=dict(_SSE_HEADERS))

    return _sse_subscribe_response(stream, from_seq=from_seq)


@router.post("/agent/projects/{project_id}/stream/cancel")
async def agent_stream_cancel(project_id: str):
    """取消项目进行中的后台生成任务

    用于确实需要中断生成的场景（如撤回消息）。普通的切换任务/断开连接
    不会也不应调用本接口。
    """
    from app.services import agent_streams
    cancelled = await agent_streams.cancel_stream(project_id)
    return {"success": True, "cancelled": cancelled}


@router.post("/agent/projects/{project_id}/mode")
async def agent_set_generation_mode(
    project_id: str,
    style: str = Form(...),
):
    """设置文档语言风格（文档风格选择）

    仅影响文档内容生成（write_chapter/generate_section/modify_attachment/update_outline），
    不改变聊天回复风格。风格按项目持久化到 Agent 状态，下一轮生成自动生效。

    Args:
        project_id: 项目ID
        style: 文档语言风格, "concise"=精炼简洁 | "detailed"=严谨详细
    """
    if style not in ("concise", "detailed"):
        raise HTTPException(status_code=400, detail=f"无效的文档风格: {style}（可选 concise/detailed）")

    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        existing = await agent.aget_state(config)
        has_checkpoint = existing is not None and bool(existing.values)
        if has_checkpoint:
            await agent.aupdate_state(config, {"writing_style": style}, as_node="after_tools")
        else:
            # 新线程无 checkpoint：用初始状态合并风格后整体 seed，避免 aupdate_state 报错
            init = dict(create_initial_state())
            init["writing_style"] = style
            await agent.aupdate_state(config, init, as_node="after_tools")
        return {"success": True, "writing_style": style}
    except Exception as e:
        import traceback as _tb
        print(f"[agent_set_generation_mode] 设置失败:\n{_tb.format_exc()}")
        raise HTTPException(status_code=500, detail=f"设置文档风格失败: {str(e)}")


@router.post("/agent/projects/{project_id}/resume")
async def agent_resume(
    project_id: str,
    decision: str = Form(...),
):
    """HITL暂停后恢复Agent执行

    恢复执行同样在后台任务中运行（与 SSE 连接解耦），切换任务不中断生成。

    Args:
        project_id: 项目ID
        decision: 用户决定
            - "approve" — 确认生成
            - "reject" — 跳过不生成
            - "edit:修改后的指令" — 用修改后的指令重新生成
    """
    from app.services.agent_engine import resume_agent, get_agent
    from app.services import agent_streams

    if agent_streams.get_active_stream(project_id):
        return _sse_busy_response()

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}
    try:
        existing = await agent.aget_state(config)
    except Exception as e:
        return _sse_error_response(f"读取Agent状态失败: {e}")
    history_count = _count_history_messages(existing.values if existing and existing.values else {})

    stream = agent_streams.start_stream(
        project_id,
        kind="resume",
        source_factory=lambda: resume_agent(
            thread_id=project_id,
            decision=decision,
        ),
        meta={"history_count": history_count, "user_message": ""},
    )
    return _sse_subscribe_response(stream, from_seq=0)


@router.post("/agent/projects/{project_id}/summarize")
async def agent_summarize(
    project_id: str,
    mode: str = Form(..., description='精简模式: "words" 字数模式 | "ratio" 比例模式'),
    target: float = Form(..., description="目标值: words 模式为字数(int); ratio 模式为压缩比例(0.1-1.0)"),
    section_name: str = Form("", description="指定章节名，为空时精简全部章节"),
    doc_type: str = Form("", description="文档类型，为空时从state自动读取"),
):
    """对已生成文档的小节内容进行精简，用精简后内容替换原小节。

    独立API手动触发，不经过Agent对话循环，直接调用工具函数并更新state。

    事件类型 (SSE):
    - start: 精简开始，包含总章节数
    - section_start: 单章节开始处理
    - section_done: 单章节处理完成，包含字数对比
    - done: 全部完成
    - error: 异常
    """
    import json
    from app.services.agent_engine import get_agent
    from app.services.agent_tools import (
        set_current_doc_context,
        summarize_section,
        get_pending_chapter_content,
    )

    async def event_stream():
        try:
            # 参数校验
            if mode not in ("words", "ratio"):
                yield f"data: {json.dumps({'type': 'error', 'message': f'mode 必须为 words 或 ratio, 当前为 {mode}'}, ensure_ascii=False)}\n\n"
                return

            if mode == "ratio":
                if not (0.1 <= float(target) <= 1.0):
                    yield f"data: {json.dumps({'type': 'error', 'message': f'ratio 模式下 target 应在 0.1~1.0 之间, 当前为 {target}'}, ensure_ascii=False)}\n\n"
                    return
            else:
                if int(target) < 100:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'words 模式下 target 应不小于 100, 当前为 {target}'}, ensure_ascii=False)}\n\n"
                    return

            agent = get_agent()
            config = {"configurable": {"thread_id": project_id}}

            existing = await agent.aget_state(config)
            if not existing or not existing.values:
                yield f"data: {json.dumps({'type': 'error', 'message': '项目不存在或尚未开始, 请先生成文档'}, ensure_ascii=False)}\n\n"
                return

            state = existing.values
            generated_sections = state.get("generated_sections", {}) or {}
            if not generated_sections:
                yield f"data: {json.dumps({'type': 'error', 'message': '尚未生成任何章节, 请先生成文档'}, ensure_ascii=False)}\n\n"
                return

            actual_doc_type = doc_type or state.get("doc_type", "design_development_plan")
            product_name = state.get("product_name", "贴敷式胰岛素泵")

            # 确定要精简的章节列表
            if section_name:
                if section_name not in generated_sections:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'章节「{section_name}」不存在, 可用章节: {list(generated_sections.keys())}'}, ensure_ascii=False)}\n\n"
                    return
                target_sections = [section_name]
            else:
                target_sections = list(generated_sections.keys())

            # 字数模式下按章节数均分预算
            if mode == "words":
                total_target = int(target)
                per_section_target = max(int(total_target / len(target_sections)), 200)
            else:
                per_section_target = float(target)

            start_event = {
                'type': 'start',
                'mode': mode,
                'target': target,
                'per_section_target': per_section_target,
                'total_sections': len(target_sections),
                'section_names': target_sections,
            }
            yield f"data: {json.dumps(start_event, ensure_ascii=False)}\n\n"

            # 顺序处理各章节（避免并发触发API限流）
            new_sections = dict(generated_sections)
            total_orig = 0
            total_new = 0
            success_count = 0

            for i, name in enumerate(target_sections):
                section_start_event = {
                    'type': 'section_start',
                    'section_name': name,
                    'index': i + 1,
                    'total': len(target_sections),
                }
                yield f"data: {json.dumps(section_start_event, ensure_ascii=False)}\n\n"

                # 每次循环前同步 _current_generated_markdown（包含已精简章节的最新内容）
                parts = []
                for n, c in new_sections.items():
                    parts.append(f"# {n}\n\n{c}\n\n")
                full_md = "\n".join(parts)
                set_current_doc_context(
                    actual_doc_type,
                    product_name,
                    full_md,
                    product_classification=state.get("product_classification", ""),
                    product_intended_use=state.get("product_intended_use", ""),
                    confirmed_standards=state.get("confirmed_standards", []),
                )

                # 调用 summarize_section 工具
                result_str = await summarize_section.ainvoke({
                    "section_name": name,
                    "mode": mode,
                    "target": per_section_target,
                    "doc_type": actual_doc_type,
                })

                try:
                    data = json.loads(result_str)
                except json.JSONDecodeError:
                    data = {"status": "error", "message": "工具返回非JSON"}

                # 从旁路读取精简后完整内容
                pending = get_pending_chapter_content(name)
                new_content = pending.get("full_content", "")

                section_orig = data.get("orig_total_chars", 0)
                section_new = data.get("new_total_chars", 0)
                total_orig += section_orig
                total_new += section_new

                if data.get("status") == "ok" and new_content:
                    new_sections[name] = new_content
                    success_count += 1
                    # 每章完成后立即更新state（让前端可以实时查看）
                    await agent.aupdate_state(config, {"generated_sections": new_sections})

                section_done_event = {
                    'type': 'section_done',
                    'section_name': name,
                    'index': i + 1,
                    'status': data.get("status", "error"),
                    'orig_chars': section_orig,
                    'new_chars': section_new,
                    'subsections_count': data.get("subsections_count", 0),
                    'success_count': data.get("success_count", 0),
                    'failed_count': data.get("failed_count", 0),
                    'message': data.get("message", "") if data.get("status") != "ok" else "",
                }
                yield f"data: {json.dumps(section_done_event, ensure_ascii=False)}\n\n"

            # 最终再更新一次state（确保所有章节都写入）
            await agent.aupdate_state(config, {"generated_sections": new_sections})

            done_event = {
                'type': 'done',
                'total_sections': len(target_sections),
                'success_count': success_count,
                'failed_count': len(target_sections) - success_count,
                'total_orig_chars': total_orig,
                'total_new_chars': total_new,
                'compression_ratio': round(total_new / total_orig, 3) if total_orig else 0,
            }
            yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'精简异常: {str(e)}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agent/projects/{project_id}/auto-generate")
async def agent_auto_generate(
    project_id: str,
    product_name: str = Form(...),
    product_classification: str = Form("III类有源医疗器械"),
    product_intended_use: str = Form("用于糖尿病患者持续皮下输注胰岛素"),
    doc_type: str = Form("design_development_plan", description="设计策划阶段文档类型"),
):
    """一键自动生成: Agent按SOP全流程自动执行，无需用户逐步确认

    Agent会依次完成: 产品画像 → 标准/资料检索 → 策划内容采集 → 章节生成 → 导出.docx
    全程通过SSE推送进度，前端实时展示。

    支持 doc_type 参数指定要生成的文档类型，默认为 design_development_plan（项目开发计划书）。
    设计策划阶段支持的文档类型参见 DOC_CATEGORIES['design_planning']['types']。
    """
    from app.services.agent_engine import stream_agent_events, get_agent
    from app.services.agent_state import create_initial_state
    from app.services.doc_types import DOC_TYPE_LABELS

    doc_label = DOC_TYPE_LABELS.get(doc_type, doc_type)

    # 构建一键生成指令 — 根据文档类型定制
    auto_prompt = f"""请按SOP流程自动完成《{doc_label}》文档的编写。全程无需等待用户确认，直接执行所有步骤。

产品信息:
- 产品名称: {product_name}
- 医疗器械分类: {product_classification}
- 预期用途: {product_intended_use}
- 目标文档类型: {doc_label}

请严格按以下顺序自动执行:

步骤1 — 记录以上产品画像信息
步骤2 — 调用 search_kb 检索贴敷式胰岛素泵与{doc_label}相关的策划依据和参考文档，列出后自动确认
步骤3 — 根据{doc_label}的文档特点，搜集所需策划内容并自动确认
步骤4 — 逐章调用 generate_section 生成{doc_label}的所有章节内容
步骤5 — 全部生成后调用 build_docx 导出Word文档

全程自动执行，不要询问用户，不要等待确认。"""

    # 一键生成同样在后台任务中运行（与 SSE 连接解耦），切换任务不中断生成
    from app.services import agent_streams

    if agent_streams.get_active_stream(project_id):
        return _sse_busy_response()

    initial_state = create_initial_state()
    # 预填产品信息，设置自动模式
    initial_state["product_name"] = product_name
    initial_state["product_classification"] = product_classification
    initial_state["product_intended_use"] = product_intended_use
    initial_state["product_status"] = "confirmed"
    initial_state["auto_mode"] = True
    initial_state["doc_type"] = doc_type

    # 保留已有附件（如果用户先上传了附件再一键生成）
    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}
    history_count = 0
    try:
        existing = await agent.aget_state(config)
        if existing and existing.values:
            existing_atts = existing.values.get("attachments", []) or []
            if existing_atts:
                initial_state["attachments"] = existing_atts
            history_count = _count_history_messages(existing.values)
    except Exception:
        pass

    stream = agent_streams.start_stream(
        project_id,
        kind="auto-generate",
        source_factory=lambda: stream_agent_events(
            user_message=auto_prompt,
            thread_id=project_id,
            initial_state=initial_state,
        ),
        meta={"history_count": history_count, "user_message": ""},
    )
    return _sse_subscribe_response(stream, from_seq=0)


@router.post("/agent/projects/{project_id}/batch-generate")
async def agent_batch_generate(
    project_id: str,
    product_name: str = Form(...),
    product_classification: str = Form("III类有源医疗器械"),
    product_intended_use: str = Form("用于糖尿病患者持续皮下输注胰岛素"),
):
    """批量生成设计策划阶段全部文档（使用经典生成API）

    按DHF清单顺序依次生成设计策划阶段所有文档，
    每完成一个文档推送一条SSE事件，前端可实时展示进度。
    所有文档生成完毕后打包为ZIP下载。
    """
    from app.services.doc_types import DOC_CATEGORIES, DOC_TYPE_LABELS

    # 获取设计策划阶段全部文档类型
    planning_types = DOC_CATEGORIES["design_planning"]["types"]

    async def event_stream():
        generated_files = []  # [(filename, bytes), ...]
        total = len(planning_types)

        yield f"data: {json.dumps({'type': 'batch_start', 'total': total, 'docs': planning_types}, ensure_ascii=False)}\n\n"

        for idx, doc_type in enumerate(planning_types):
            doc_label = DOC_TYPE_LABELS.get(doc_type, doc_type)
            yield f"data: {json.dumps({'type': 'doc_start', 'index': idx + 1, 'total': total, 'doc_type': doc_type, 'label': doc_label}, ensure_ascii=False)}\n\n"

            try:
                generator = DocumentGenerator()
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    file_bytes = loop.run_until_complete(
                        generator.generate(
                            doc_type=doc_type,
                            product_name=product_name,
                            product_type=product_classification,
                            product_params=f"预期用途: {product_intended_use}",
                        )
                    )
                finally:
                    loop.close()

                filename = f"{product_name}_{doc_label}.docx"
                generated_files.append((filename, file_bytes))

                yield f"data: {json.dumps({'type': 'doc_done', 'index': idx + 1, 'total': total, 'doc_type': doc_type, 'label': doc_label, 'filename': filename, 'size_kb': len(file_bytes) // 1024}, ensure_ascii=False)}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'type': 'doc_error', 'index': idx + 1, 'total': total, 'doc_type': doc_type, 'label': doc_label, 'error': str(e)}, ensure_ascii=False)}\n\n"

        # 打包为ZIP
        if generated_files:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fname, fbytes in generated_files:
                    zf.writestr(fname, fbytes)
            zip_buffer.seek(0)
            zip_bytes = zip_buffer.getvalue()

            # 存储ZIP供下载（使用project_id作为key）
            _batch_results[project_id] = {
                "zip_bytes": zip_bytes,
                "filename": f"{product_name}_设计策划阶段文档集.zip",
                "files": [f[0] for f in generated_files],
            }

            yield f"data: {json.dumps({'type': 'batch_done', 'total': total, 'completed': len(generated_files), 'download_id': project_id}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'batch_error', 'message': '所有文档生成失败'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# 批量生成结果存储
_batch_results = {}


@router.get("/agent/batch-download/{project_id}")
async def agent_batch_download(project_id: str):
    """下载批量生成的ZIP文件"""
    if project_id not in _batch_results:
        raise HTTPException(status_code=404, detail="批量生成结果不存在或已过期")

    result = _batch_results[project_id]
    encoded_filename = quote(result["filename"])

    return StreamingResponse(
        io.BytesIO(result["zip_bytes"]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/agent/projects/{project_id}/state")
async def agent_get_state(project_id: str):
    """获取Agent当前状态快照 (供前端进度面板使用)

    返回PRD Section 4.3格式的状态JSON
    """
    from app.services.agent_engine import get_agent_state

    try:
        state = await get_agent_state(project_id)
        return {"success": True, "state": state}
    except Exception as e:
        # Agent可能尚未初始化或thread不存在
        from app.services.agent_state import create_initial_state, build_state_snapshot
        state = build_state_snapshot(create_initial_state())
        return {"success": True, "state": state, "note": f"使用默认状态 (Agent: {str(e)})"}


@router.get("/agent/projects/{project_id}/document")
async def agent_get_document(project_id: str):
    """获取Agent已生成文档的组装内容（供审阅页面使用）

    从Agent状态中读取 generated_sections 并组装为结构化JSON，
    包含产品信息、标准清单、各章节内容。
    """
    from app.services.agent_engine import get_agent

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = await agent.aget_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取Agent状态: {str(e)}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="项目不存在或尚未开始")

    values = state.values
    generated = values.get("generated_sections", {}) or {}
    product_name = values.get("product_name", "") or "未命名产品"

    # 章节顺序: 按 generated_sections 字典的插入顺序（即首次生成顺序）输出
    # 与 Agent build_docx 工具 (_sync_doc_context) 的行为保持一致
    # 修订/重新生成同名小节时 dict 顺序自动保留，避免重排导致顺序错乱
    ordered_sections = [{"title": name, "content": content} for name, content in generated.items()]

    return {
        "success": True,
        "project_id": project_id,
        "product_name": product_name,
        "product": {
            "name": values.get("product_name"),
            "classification": values.get("product_classification"),
            "intended_use": values.get("product_intended_use"),
            "status": values.get("product_status", "not_started"),
        },
        "standards": {
            "confirmed": values.get("confirmed_standards", []),
            "candidate": values.get("candidate_standards", []),
            "status": values.get("standards_status", "not_started"),
        },
        "document_status": values.get("document_status", "not_started"),
        "sections": ordered_sections,
        "unresolved_items": values.get("unresolved_items", []),
    }


@router.post("/agent/projects/{project_id}/document")
async def agent_update_document(project_id: str, request: DocumentUpdateRequest):
    """审阅页面保存修改后的文档内容

    接收前端编辑后的完整章节列表，整体替换 generated_sections 并持久化到 Agent 状态。
    章节顺序按请求列表顺序（前端保留原顺序），修订/新增/删除章节均生效；
    后续 Agent 生成、build_docx、下载都会基于保存后的最新内容。
    """
    from app.services.agent_engine import get_agent

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = await agent.aget_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取Agent状态: {str(e)}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="项目不存在或尚未开始")

    new_sections = {}
    for s in request.sections:
        title = (s.title or "").strip()
        if not title:
            continue
        new_sections[title] = s.content

    if not new_sections:
        raise HTTPException(status_code=400, detail="未提供有效的章节内容")

    try:
        await agent.aupdate_state(config, {"generated_sections": new_sections})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存修改失败: {str(e)}")

    return {
        "success": True,
        "project_id": project_id,
        "sections_updated": len(new_sections),
    }


@router.get("/agent/projects/{project_id}/download")
async def agent_download_document(project_id: str):
    """直接从Agent状态组装文档并下载（无需Agent参与）

    普通文档读取 generated_sections 组装为完整Markdown，通过TemplateService构建.docx；
    风险分析总表类文档（product_risk_analysis_matrix / cybersecurity_risk_analysis_matrix）
    则调用 risk_excel 生成 .xlsx（与参考「风险分析和管理总表」格式一致）。
    """
    from app.services.agent_engine import get_agent
    from app.services.template import TemplateService
    from app.services.risk_excel import (
        is_risk_matrix_doc, generate_risk_rows, build_risk_excel,
    )
    import asyncio
    from urllib.parse import quote

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = await agent.aget_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取Agent状态: {str(e)}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="项目不存在或尚未开始")

    values = state.values
    doc_type = values.get("doc_type", "design_development_plan")
    product_name = values.get("product_name", "") or "贴敷式胰岛素泵"

    # ── 风险分析总表类文档 → 直接导出 Excel (.xlsx) ──
    if is_risk_matrix_doc(doc_type):
        classification = values.get("product_classification", "") or ""
        intended_use = values.get("product_intended_use", "") or ""
        rows = await asyncio.to_thread(
            generate_risk_rows, doc_type, product_name, classification, intended_use
        )
        if not rows:
            raise HTTPException(
                status_code=500,
                detail="风险条目生成失败（模型未返回有效数据），请稍后重试",
            )
        file_bytes = await asyncio.to_thread(build_risk_excel, doc_type, rows)
        label = DOC_TYPE_LABELS.get(doc_type, "风险分析和管理总表")
        filename = f"{product_name}_{label}.xlsx"
        encoded_filename = quote(filename)
        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            },
        )

    generated = values.get("generated_sections", {}) or {}

    if not generated:
        raise HTTPException(status_code=400, detail="尚未生成任何章节，请先在Agent对话中生成文档")

    # 章节顺序: 按 generated_sections 字典的插入顺序（即首次生成顺序）输出
    # 与 Agent build_docx 工具 (_sync_doc_context) 的行为保持一致
    # 修订/重新生成同名小节时 dict 顺序自动保留，避免重排导致顺序错乱
    full_markdown = "\n\n".join(generated.values())

    doc_label = DOC_TYPE_LABELS.get(doc_type, "设计策划文档")

    # 构建.docx：fill_template 内部会用 Playwright 同步 API 渲染 mermaid 流程图，
    # 而 Playwright 同步 API 不能在 asyncio 事件循环线程内运行，故放入独立线程执行。
    def _build_docx():
        template_service = TemplateService()
        doc = template_service.load_template(doc_type)
        doc = template_service.fill_template(
            doc=doc,
            content=full_markdown,
            product_name=product_name,
            doc_type=doc_type,
        )
        return template_service.document_to_bytes(doc)

    file_bytes = await asyncio.to_thread(_build_docx)

    filename = f"{product_name}_{doc_label}.docx"
    encoded_filename = quote(filename)

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/agent/download/{download_id}")
async def agent_download_docx(download_id: str):
    """下载Agent通过 build_docx 工具生成的文档（Word .docx 或风险总表 .xlsx）"""
    from app.services.agent_tools import _get_docx

    docx_data = _get_docx(download_id)
    if not docx_data:
        raise HTTPException(status_code=404, detail="下载链接不存在或已过期，请重新生成文档")

    from urllib.parse import quote
    encoded_filename = quote(docx_data["filename"])
    content_type = docx_data.get(
        "content_type",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    return StreamingResponse(
        io.BytesIO(docx_data["bytes"]),
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/agent/projects/{project_id}/modified-documents")
async def agent_list_modified_documents(project_id: str):
    """列出项目内所有附件修改结果（modify_attachment 工具的产物）

    从Agent状态读取 attachment_modifications，返回摘要列表
    （不含完整 Markdown，避免响应过大）。
    """
    from app.services.agent_engine import get_agent

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = await agent.aget_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取Agent状态: {str(e)}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="项目不存在或尚未开始")

    modifications = state.values.get("attachment_modifications", []) or []
    return {
        "success": True,
        "project_id": project_id,
        "modifications": [
            {
                "file_id": m.get("file_id"),
                "filename": m.get("filename", ""),
                "summary": m.get("summary", ""),
                "modified_chars": m.get("modified_chars", 0),
                "timestamp": m.get("timestamp", ""),
            }
            for m in modifications
        ],
    }


@router.post("/agent/projects/{project_id}/undo")
async def agent_undo(project_id: str):
    """回退到最近一次文档修改/生成/精简/附件修改之前的状态（单步撤销）。

    从 Agent 状态的 undo_stack 弹出栈顶快照，恢复 generated_sections 中被覆盖的章节
    与 attachment_modifications 列表，并持久化。
    """
    from app.services.agent_engine import get_agent

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = await agent.aget_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取Agent状态: {str(e)}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="项目不存在或尚未开始")

    values = state.values
    undo_stack = list(values.get("undo_stack", []) or [])
    if not undo_stack:
        return {"success": False, "message": "没有可回退的操作"}

    entry = undo_stack.pop()
    generated_sections = dict(values.get("generated_sections", {}) or {})
    attachment_modifications = list(values.get("attachment_modifications", []) or [])

    # 恢复被覆盖章节的旧值（old 为 None 表示该章节原本不存在，应删除）
    sections_before = entry.get("sections_before", {}) or {}
    for name, old in sections_before.items():
        if old is None:
            generated_sections.pop(name, None)
        else:
            generated_sections[name] = old

    # 截断附件修改列表到变更前长度
    attachments_before_len = entry.get("attachments_before_len")
    if attachments_before_len is not None:
        attachment_modifications = attachment_modifications[:attachments_before_len]

    await agent.aupdate_state(config, {
        "generated_sections": generated_sections,
        "attachment_modifications": attachment_modifications,
        "undo_stack": undo_stack,
    }, as_node="after_tools")

    return {
        "success": True,
        "message": f"已回退：{entry.get('description', '上次操作')}",
        "description": entry.get("description", ""),
        "removed_file_ids": entry.get("removed_file_ids", []) or [],
    }


@router.get("/agent/projects/{project_id}/modified-documents/{file_id}/download")
async def agent_download_modified_document(project_id: str, file_id: str):
    """下载修改后的附件文档 (.docx)

    从Agent状态读取 attachment_modifications 中 file_id 对应的修改后 Markdown，
    通过 TemplateService 构建 .docx 并返回。
    """
    from app.services.agent_engine import get_agent
    from app.services.template import TemplateService

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = await agent.aget_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取Agent状态: {str(e)}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="项目不存在或尚未开始")

    values = state.values
    modifications = values.get("attachment_modifications", []) or []
    target = next((m for m in modifications if m.get("file_id") == file_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="未找到该附件的修改结果，请先在对话中让Agent修改附件")

    import asyncio

    ops = target.get("ops")
    original_path = target.get("original_path", "")
    if ops and original_path and os.path.isfile(original_path):
        # 段落级手术：在原 docx 上执行编辑指令，未涉及的段落/表格样式原样保留
        from docx import Document as _Document
        from app.services.docx_edit import apply_edit_ops

        def _build_docx():
            doc = _Document(original_path)
            apply_edit_ops(doc, ops)
            buf = io.BytesIO()
            doc.save(buf)
            return buf.getvalue()

        file_bytes = await asyncio.to_thread(_build_docx)
    else:
        modified_markdown = target.get("modified_markdown", "")
        if not modified_markdown.strip():
            raise HTTPException(status_code=400, detail="修改后文档内容为空")

        # 读取实际的 doc_type（无则默认设计开发计划书）
        doc_type = values.get("doc_type", "design_development_plan")
        product_name = values.get("product_name", "") or "贴敷式胰岛素泵"

        # 构建.docx（复用审阅下载链路）；Playwright 同步 API 渲染 mermaid 须在独立线程执行
        def _build_docx():
            template_service = TemplateService()
            doc = template_service.load_template(doc_type)
            doc = template_service.fill_template(
                doc=doc,
                content=modified_markdown,
                product_name=product_name,
                doc_type=doc_type,
            )
            return template_service.document_to_bytes(doc)

        file_bytes = await asyncio.to_thread(_build_docx)

    orig_name = target.get("filename", "document.md")
    stem = os.path.splitext(orig_name)[0]
    filename = f"{stem}_修改版.docx"
    encoded_filename = quote(filename)

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


# ═══════════════════════════════════════════════════════════════
# Agent 附件上传接口
# ═══════════════════════════════════════════════════════════════

@router.post("/agent/upload/{project_id}")
async def agent_upload_attachment(
    project_id: str,
    file: UploadFile = File(..., description="附件文件 (.pdf/.docx/.doc/.txt/.xlsx)"),
    hidden: bool = Form(False),
):
    """Agent模式下上传附件

    提交后台提取任务后立即返回 processing，前端轮询 GET /extract-status/{file_id}，
    提取完成后调用 POST /agent/projects/{project_id}/attachments/{file_id}/finalize
    把全文写入 Agent 状态。避免在请求内同步轮询（MinerU 首次加载模型 +
    多页推理可远超 5 分钟导致上传超时）。

    同时将文本写入向量库（uploads集合），支持混合检索。
    """
    from app.services.attachment_service import extract_tasks

    # 验证文件
    file_content = await file.read()
    is_valid, error_msg = validate_upload(file.filename, len(file_content))
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # 提交提取任务（persist=True 写入向量库），后台线程异步执行
    task_id = submit_extract_task(
        file_content=file_content,
        filename=file.filename,
        persist=True,
        doc_type="agent_attachment",
    )

    # 记录「修改文档」入口标记，供 finalize 端点写入状态时使用
    extract_tasks[task_id]["hidden"] = bool(hidden)

    return {
        "success": True,
        "status": "processing",
        "file_id": task_id,
        "filename": file.filename,
        "message": f"文件「{file.filename}」已接收，正在后台提取文本...",
    }


@router.post("/agent/projects/{project_id}/attachments/{file_id}/finalize")
async def agent_finalize_attachment(project_id: str, file_id: str):
    """将已提取完成的附件全文写入 Agent 状态 attachments 列表。

    与 agent_upload_attachment 配套：上传端点立即返回 processing，前端轮询
    /extract-status/{file_id} 至 completed 后调用本端点，把提取出的 full_text
    写入 Agent 状态，供后续 modify_attachment / enrich_attachment /
    summarize_attachment / search_attachment 使用。
    """
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state
    from app.services.attachment_service import extract_tasks

    task = extract_tasks.get(file_id)
    if not task:
        raise HTTPException(status_code=404, detail="提取任务不存在（服务可能已重启），请重新上传")

    if task.get("status") != "completed":
        raise HTTPException(status_code=409, detail=f"文件文本尚未提取完成（当前状态: {task.get('status')}），请稍后重试")

    full_text = task.get("full_text", "")
    preview = task.get("preview", "")
    char_count = task.get("char_count", 0)

    # 如果内存中的 full_text 已被清理，尝试从向量库重建
    if not full_text and char_count > 0:
        try:
            from app.services.rag.vector_store import VectorStore
            vs = VectorStore(collection_name="uploads")
            results = vs.collection.get(
                where={"file_id": file_id},
                include=["documents"]
            )
            if results and results.get("documents"):
                full_text = "\n\n".join(results["documents"])
                preview = full_text[:500] + ("..." if len(full_text) > 500 else "")
        except Exception:
            pass

    filename = task.get("filename", file_id)
    hidden = bool(task.get("hidden", False))

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        current_state = await agent.aget_state(config)
        state_values = dict(current_state.values) if current_state and current_state.values else dict(create_initial_state())
    except Exception:
        state_values = dict(create_initial_state())

    attachments = list(state_values.get("attachments", []) or [])
    attachments.append({
        "file_id": file_id,
        "filename": filename,
        "char_count": char_count,
        "preview": preview,
        "full_text": full_text,  # 附件全文，不截断，直接给大模型
        "toc": task.get("toc", ""),
        "status": "completed",
        "hidden": hidden,  # 标记「修改文档」入口上传的文档，不展示在附件列表
        # 原 .docx 文件路径（段落级手术编辑基底；非 docx 无此字段）
        "original_path": task.get("original_path", ""),
    })

    # 更新Agent状态
    import traceback as _tb
    try:
        await agent.aupdate_state(config, {"attachments": attachments}, as_node="after_tools")
    except Exception as e:
        err_tb = _tb.format_exc()
        print(f"[agent_finalize_attachment] aupdate_state 失败:\n{err_tb}")
        raise HTTPException(status_code=500, detail=f"状态更新失败: {type(e).__name__}: {e}")

    return {
        "success": True,
        "file_id": file_id,
        "filename": filename,
        "char_count": char_count,
        "preview": preview,
        "message": f"文件「{filename}」已提取完成 ({char_count} 字符)。Agent现在可以在对话中检索此文件内容。",
    }


@router.post("/agent/projects/{project_id}/attachments/from-kb")
async def agent_add_attachment_from_kb(project_id: str, payload: KbToAttachmentRequest):
    """将知识库中已入库的文件直接加入当前会话附件。

    知识库文件在上传时已提取全文并写入 uploads 向量库，此处无需重新上传/提取，
    仅按 source_file 读回全文，再写入会话状态 attachments（供检索/修改等针对性操作）。
    """
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state
    from app.services.rag.vector_store import VectorStore

    source_file = (payload.source_file or "").strip()
    if not source_file:
        raise HTTPException(status_code=400, detail="缺少 source_file 参数")

    filename = (payload.filename or "").strip() or os.path.basename(source_file)
    # 优先复用知识库 chunk 的 file_id（保证后续 resolve_attachment_content 可按 file_id 检索命中），
    # 旧文件 file_id 为空时回退为 source_file（附件全文已存状态，仍可被 Agent 直接读取）。
    file_id = (payload.file_id or "").strip() or source_file

    store = VectorStore(collection_name="uploads")
    full_text = store.get_text_by_source(source_file)
    if not full_text.strip():
        raise HTTPException(status_code=404, detail="知识库文件内容为空，无法添加为附件")

    char_count = len(full_text)
    preview = full_text[:500] + ("..." if len(full_text) > 500 else "")

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        current_state = await agent.aget_state(config)
        state_values = dict(current_state.values) if current_state and current_state.values else dict(create_initial_state())
    except Exception:
        state_values = dict(create_initial_state())

    attachments = list(state_values.get("attachments", []) or [])

    # 去重：同一 file_id 已在附件列表中则直接返回
    if any(a.get("file_id") == file_id for a in attachments):
        return {
            "success": True,
            "file_id": file_id,
            "filename": filename,
            "duplicate": True,
            "message": f"文件「{filename}」已在附件列表中",
        }

    attachments.append({
        "file_id": file_id,
        "filename": filename,
        "char_count": char_count,
        "preview": preview,
        "full_text": full_text,
        "toc": "",
        "status": "completed",
        "hidden": False,
    })

    import traceback as _tb
    try:
        await agent.aupdate_state(config, {"attachments": attachments}, as_node="after_tools")
    except Exception as e:
        err_tb = _tb.format_exc()
        print(f"[agent_add_attachment_from_kb] aupdate_state 失败:\n{err_tb}")
        raise HTTPException(status_code=500, detail=f"状态更新失败: {type(e).__name__}: {e}")

    return {
        "success": True,
        "file_id": file_id,
        "filename": filename,
        "char_count": char_count,
        "message": f"文件「{filename}」已添加到附件 ({char_count} 字符)",
    }


class KbToAttachmentBatchItem(BaseModel):
    """批量添加知识库文件到附件的单项"""
    source_file: str = Field(..., description="知识库文件的 source_file 标识")
    file_id: str = Field(default="", description="知识库文件的 file_id；缺省回退为 source_file")
    filename: str = Field(default="", description="附件展示名；缺省取 source_file 文件名")


class KbToAttachmentBatchRequest(BaseModel):
    """批量将知识库文件加入当前会话附件的请求"""
    files: List[KbToAttachmentBatchItem] = Field(..., description="要添加的知识库文件列表")


@router.post("/agent/projects/{project_id}/attachments/from-kb/batch")
async def agent_add_attachments_from_kb_batch(project_id: str, payload: KbToAttachmentBatchRequest):
    """批量将知识库中已入库的文件加入当前会话附件。

    与单文件 /attachments/from-kb 等价（读回全文、按 file_id 去重），
    但所有文件合并为一次状态更新，适合前端多选批量添加。
    """
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state
    from app.services.rag.vector_store import VectorStore

    if not payload.files:
        raise HTTPException(status_code=400, detail="files 列表为空")

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        current_state = await agent.aget_state(config)
        has_checkpoint = current_state is not None and bool(current_state.values)
        state_values = dict(current_state.values) if has_checkpoint else dict(create_initial_state())
    except Exception:
        has_checkpoint = False
        state_values = dict(create_initial_state())

    attachments = list(state_values.get("attachments", []) or [])
    existing_ids = {a.get("file_id") for a in attachments}

    store = VectorStore(collection_name="uploads")
    results = []
    added_count = 0
    for item in payload.files:
        source_file = (item.source_file or "").strip()
        filename = (item.filename or "").strip() or os.path.basename(source_file)
        file_id = (item.file_id or "").strip() or source_file
        if not source_file:
            results.append({"source_file": item.source_file, "filename": filename,
                            "status": "skipped", "message": "缺少 source_file"})
            continue
        if file_id in existing_ids:
            results.append({"source_file": source_file, "filename": filename,
                            "status": "duplicate", "message": "已在附件列表中"})
            continue
        try:
            full_text = store.get_text_by_source(source_file)
            if not full_text.strip():
                results.append({"source_file": source_file, "filename": filename,
                                "status": "empty", "message": "知识库文件内容为空"})
                continue
        except Exception as e:
            results.append({"source_file": source_file, "filename": filename,
                            "status": "error", "message": f"读取全文失败: {e}"})
            continue

        attachments.append({
            "file_id": file_id,
            "filename": filename,
            "char_count": len(full_text),
            "preview": full_text[:500] + ("..." if len(full_text) > 500 else ""),
            "full_text": full_text,
            "toc": "",
            "status": "completed",
            "hidden": False,
        })
        existing_ids.add(file_id)
        added_count += 1
        results.append({"source_file": source_file, "filename": filename,
                        "status": "ok", "char_count": len(full_text)})

    if added_count > 0:
        import traceback as _tb
        try:
            if has_checkpoint:
                await agent.aupdate_state(config, {"attachments": attachments}, as_node="after_tools")
            else:
                # 新项目无 checkpoint：完整初始 state seed（避免部分通道 checkpoint，见模板 finalize 同款加固）
                init = dict(state_values)
                init["attachments"] = attachments
                await agent.aupdate_state(config, init, as_node="after_tools")
        except Exception as e:
            err_tb = _tb.format_exc()
            print(f"[agent_add_attachments_from_kb_batch] aupdate_state 失败:\n{err_tb}")
            raise HTTPException(status_code=500, detail=f"状态更新失败: {type(e).__name__}: {e}")

    return {
        "success": True,
        "added_count": added_count,
        "total": len(payload.files),
        "results": results,
        "message": f"已添加 {added_count}/{len(payload.files)} 个文件到附件"
                   + ("，其余已在附件列表中或读取失败" if added_count < len(payload.files) else ""),
    }


# ── 文件夹批量上传 ──

PLAINTEXT_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.yaml', '.yml', '.md',
    '.txt', '.html', '.htm', '.css', '.scss', '.less', '.cfg', '.ini',
    '.toml', '.xml', '.sh', '.bat', '.env', '.gitignore', '.sql', '.java',
    '.c', '.cpp', '.h', '.hpp', '.rs', '.go', '.rb', '.php', '.swift', '.kt',
    '.csv', '.log', '.rst', '.tex', '.mjs', '.cjs', '.vue', '.svelte',
    '.cmake', '.mak', '.mk', '.gradle', '.proto', '.graphql',
}


def _classify_file_type(filename: str) -> tuple:
    """根据扩展名判断文件类型: ("plaintext", None) | ("document", None) | ("binary", None)"""
    ext = os.path.splitext(filename)[1].lower()
    if ext in PLAINTEXT_EXTENSIONS:
        return ("plaintext", None)
    if ext in ('.pdf', '.docx', '.doc', '.xlsx', '.xls', '.ppt', '.pptx'):
        return ("document", None)
    return ("binary", None)


# 扩展名 → 轻量主题类别（用于文件夹解析进度提示，避免为每个文件调用 LLM）
_EXT_CATEGORY = {
    '.py': 'Python 代码', '.js': 'JavaScript 代码', '.ts': 'TypeScript 代码',
    '.jsx': 'React 组件', '.tsx': 'React/TS 组件', '.vue': 'Vue 组件',
    '.md': 'Markdown 文档', '.txt': '文本文件', '.rst': 'reStructuredText 文档',
    '.pdf': 'PDF 文档', '.docx': 'Word 文档', '.doc': 'Word 文档',
    '.xlsx': 'Excel 表格', '.xls': 'Excel 表格', '.ppt': 'PPT 演示文稿', '.pptx': 'PPT 演示文稿',
    '.json': 'JSON 数据', '.yaml': 'YAML 配置', '.yml': 'YAML 配置', '.toml': 'TOML 配置',
    '.ini': 'INI 配置', '.cfg': '配置文件', '.env': '环境变量配置',
    '.html': 'HTML 页面', '.htm': 'HTML 页面', '.css': 'CSS 样式',
    '.scss': 'SCSS 样式', '.less': 'LESS 样式',
    '.sql': 'SQL 脚本', '.sh': 'Shell 脚本', '.bat': '批处理脚本',
    '.java': 'Java 代码', '.c': 'C 代码', '.h': 'C/C++ 头文件', '.cpp': 'C++ 代码',
    '.hpp': 'C++ 头文件', '.rs': 'Rust 代码', '.go': 'Go 代码',
    '.rb': 'Ruby 代码', '.php': 'PHP 代码', '.swift': 'Swift 代码', '.kt': 'Kotlin 代码',
    '.csv': 'CSV 数据表', '.log': '日志文件', '.xml': 'XML 文件',
    '.tex': 'LaTeX 文档', '.mjs': 'JavaScript 模块', '.cjs': 'JavaScript 模块',
    '.cmake': 'CMake 构建脚本', '.mk': 'Makefile', '.gradle': 'Gradle 构建脚本',
    '.proto': 'Protobuf 定义', '.graphql': 'GraphQL 定义', '.gitignore': 'Git 忽略规则',
}


def _topic_from_filename(filename: str) -> str:
    """根据文件名/扩展名生成轻量主题描述"""
    ext = os.path.splitext(filename)[1].lower()
    cat = _EXT_CATEGORY.get(ext)
    return f"{cat}「{filename}」" if cat else f"文件「{filename}」"


def _summary_from_preview(preview: str, max_len: int = 150) -> str:
    """从预览文本生成轻量摘要：压平换行并截断到 max_len 字符"""
    s = " ".join((preview or "").strip().split())
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


def _extract_plaintext(file_content: bytes) -> tuple:
    """直接读取纯文本文件内容，尝试多种编码。返回 (text, char_count, preview)"""
    for enc in ["utf-8", "gbk", "gb18030", "latin-1"]:
        try:
            text = file_content.decode(enc)
            char_count = len(text)
            preview = text[:500] + ("..." if char_count > 500 else "")
            return (text, char_count, preview)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ("", 0, "")


def _sanitize_relative_path(path: str) -> str:
    """规范化相对路径，防路径遍历"""
    cleaned = path.replace("\\", "/").lstrip("/")
    parts = []
    for p in cleaned.split("/"):
        if p in ("", ".", ".."):
            continue
        parts.append(p)
    return "/".join(parts) if parts else os.path.basename(cleaned) or "unknown"


@router.post("/agent/upload-folder/{project_id}")
async def agent_upload_folder(
    project_id: str,
    files: List[UploadFile] = File(..., description="文件夹中的所有文件"),
    relative_paths: str = Form(..., description="JSON数组，每个文件的相对路径，与files顺序对应"),
    folder_name: str = Form("", description="根文件夹名称"),
):
    """批量上传文件夹，保留目录结构，所有文件内容供Agent使用。

    接收文件夹中所有文件及对应的相对路径。纯文本/代码文件直接提取文本，
    文档文件（PDF/DOCX等）通过MinerU管道提取，二进制文件仅记录元数据。

    解析过程以 SSE 流式返回，事件序列：
      - file_start: {type, index, total, relative_path, filename, topic}  开始解析某文件
      - file_done:  {type, index, total, relative_path, filename, status, topic, summary}  单文件完成
      - done:       {type, folder_name, total_files, ok_count, total_chars, failed_count, errors}
      - error:      {type, message}

    Args:
        project_id: 项目ID
        files: 文件列表
        relative_paths: JSON数组字符串，如 '["src/main.py", "src/utils/helper.py"]'
        folder_name: 根文件夹名，为空时从路径推断
    """
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state

    try:
        rel_paths = json.loads(relative_paths)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="relative_paths 必须是有效的 JSON 数组")

    if len(files) != len(rel_paths):
        raise HTTPException(
            status_code=400,
            detail=f"文件数量 ({len(files)}) 与路径数量 ({len(rel_paths)}) 不匹配",
        )

    if not files:
        raise HTTPException(status_code=400, detail="未选择任何文件")

    # 推断文件夹名
    if not folder_name.strip():
        first_path = rel_paths[0] if rel_paths else ""
        parts = first_path.replace("\\", "/").lstrip("/").split("/")
        folder_name = parts[0] if parts else "未命名文件夹"

    # 读取当前 Agent 状态
    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}
    try:
        current_state = await agent.aget_state(config)
        state_values = dict(current_state.values) if current_state and current_state.values else dict(create_initial_state())
    except Exception:
        state_values = dict(create_initial_state())

    # 关键：StreamingResponse 的 event_stream 在函数返回后才被消费，
    # 此时 UploadFile 可能已被关闭，故在此一次性把所有文件内容读入内存。
    file_items = []
    for i, (file, raw_path) in enumerate(zip(files, rel_paths)):
        rel_path = _sanitize_relative_path(raw_path)
        filename = file.filename or os.path.basename(rel_path) or f"file_{i}"
        content = await file.read()
        file_items.append((content, rel_path, filename))

    attachments = list(state_values.get("attachments", []) or [])

    async def event_stream():
        total = len(file_items)
        total_chars = 0
        ok_count = 0
        errors = []

        try:
            for i, (content, rel_path, filename) in enumerate(file_items):
                idx = i + 1
                topic = _topic_from_filename(filename)

                yield f"data: {json.dumps({'type': 'file_start', 'index': idx, 'total': total, 'relative_path': rel_path, 'filename': filename, 'topic': topic}, ensure_ascii=False)}\n\n"

                if not content:
                    attachments.append({
                        "file_id": str(uuid.uuid4())[:12],
                        "filename": filename,
                        "relative_path": rel_path,
                        "char_count": 0,
                        "preview": "[空文件]",
                        "full_text": "",
                        "toc": "",
                        "status": "empty",
                    })
                    yield f"data: {json.dumps({'type': 'file_done', 'index': idx, 'total': total, 'relative_path': rel_path, 'filename': filename, 'status': 'empty', 'topic': topic, 'summary': '该文件内容为空'}, ensure_ascii=False)}\n\n"
                    continue

                if len(content) > MAX_UPLOAD_SIZE_BYTES:
                    errors.append(f"{rel_path}: 文件过大")
                    yield f"data: {json.dumps({'type': 'file_done', 'index': idx, 'total': total, 'relative_path': rel_path, 'filename': filename, 'status': 'too_large', 'topic': topic, 'summary': '文件过大，已跳过'}, ensure_ascii=False)}\n\n"
                    continue

                file_type, _ = _classify_file_type(filename)

                if file_type == "plaintext":
                    text, char_count, preview = _extract_plaintext(content)
                    if char_count == 0:
                        attachments.append({
                            "file_id": str(uuid.uuid4())[:12],
                            "filename": filename,
                            "relative_path": rel_path,
                            "char_count": 0,
                            "preview": "[编码错误]",
                            "full_text": "",
                            "toc": "",
                            "status": "encoding_error",
                        })
                        yield f"data: {json.dumps({'type': 'file_done', 'index': idx, 'total': total, 'relative_path': rel_path, 'filename': filename, 'status': 'encoding_error', 'topic': topic, 'summary': '编码无法识别，未能提取文本'}, ensure_ascii=False)}\n\n"
                        continue

                    file_id = str(uuid.uuid4())[:12]
                    attachments.append({
                        "file_id": file_id,
                        "filename": filename,
                        "relative_path": rel_path,
                        "char_count": char_count,
                        "preview": preview,
                        "full_text": text,
                        "toc": "",
                        "status": "completed",
                    })
                    total_chars += char_count
                    ok_count += 1
                    yield f"data: {json.dumps({'type': 'file_done', 'index': idx, 'total': total, 'relative_path': rel_path, 'filename': filename, 'status': 'ok', 'char_count': char_count, 'topic': topic, 'summary': _summary_from_preview(preview)}, ensure_ascii=False)}\n\n"

                elif file_type == "document":
                    task_id = submit_extract_task(
                        file_content=content,
                        filename=filename,
                        persist=False,
                        doc_type="agent_attachment",
                    )
                    extracted = False
                    for _ in range(600):
                        status = get_extract_status(task_id)
                        if status is None:
                            break
                        if status["status"] == "completed":
                            extracted = True
                            break
                        if status["status"] == "failed":
                            break
                        await asyncio.sleep(0.5)

                    if extracted:
                        from app.services.attachment_service import extract_tasks
                        task = extract_tasks.get(task_id, {})
                        full_text = task.get("full_text", "")
                        char_count = task.get("char_count", 0)
                        preview = task.get("preview", "")
                        attachments.append({
                            "file_id": task_id,
                            "filename": filename,
                            "relative_path": rel_path,
                            "char_count": char_count,
                            "preview": preview,
                            "full_text": full_text,
                            "toc": task.get("toc", ""),
                            "status": "completed",
                        })
                        total_chars += char_count
                        ok_count += 1
                        yield f"data: {json.dumps({'type': 'file_done', 'index': idx, 'total': total, 'relative_path': rel_path, 'filename': filename, 'status': 'ok', 'char_count': char_count, 'topic': topic, 'summary': _summary_from_preview(preview)}, ensure_ascii=False)}\n\n"
                    else:
                        errors.append(f"{rel_path}: 文档提取失败或超时")
                        yield f"data: {json.dumps({'type': 'file_done', 'index': idx, 'total': total, 'relative_path': rel_path, 'filename': filename, 'status': 'failed', 'topic': topic, 'summary': '文档提取失败或超时'}, ensure_ascii=False)}\n\n"

                else:
                    file_id = str(uuid.uuid4())[:12]
                    attachments.append({
                        "file_id": file_id,
                        "filename": filename,
                        "relative_path": rel_path,
                        "char_count": 0,
                        "preview": "[二进制文件]",
                        "full_text": "",
                        "toc": "",
                        "status": "binary",
                    })
                    yield f"data: {json.dumps({'type': 'file_done', 'index': idx, 'total': total, 'relative_path': rel_path, 'filename': filename, 'status': 'binary', 'topic': topic, 'summary': f'二进制文件，无法提取文本（{len(content)} 字节）'}, ensure_ascii=False)}\n\n"

            # 全部文件处理完成：写入 Agent 状态
            import traceback as _tb
            try:
                await agent.aupdate_state(config, {"attachments": attachments}, as_node="after_tools")
            except Exception as e:
                err_tb = _tb.format_exc()
                print(f"[agent_upload_folder] aupdate_state 失败:\n{err_tb}")
                yield f"data: {json.dumps({'type': 'error', 'message': f'状态更新失败: {type(e).__name__}: {e}'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'done', 'folder_name': folder_name, 'total_files': total, 'ok_count': ok_count, 'total_chars': total_chars, 'failed_count': len(errors), 'errors': errors}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'文件夹解析异常: {str(e)}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/agent/projects/{project_id}/attachments")
async def agent_list_attachments(project_id: str):
    """获取Agent项目已上传的附件列表"""
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state, build_state_snapshot

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        current_state = await agent.aget_state(config)
        state_values = current_state.values if current_state and current_state.values else {}
    except Exception:
        state_values = {}

    attachments = state_values.get("attachments", []) or []

    return {
        "success": True,
        "project_id": project_id,
        "attachments": [
            {
                "file_id": a.get("file_id"),
                "filename": a.get("filename"),
                "char_count": a.get("char_count", 0),
                "preview": a.get("preview", ""),
                "status": a.get("status", "unknown"),
            }
            for a in attachments
            if not a.get("hidden")
        ],
    }


@router.post("/agent/projects/{project_id}/recall")
async def agent_recall_message(project_id: str):
    """撤回最近一条用户消息及其后所有Agent回复

    通过 LangGraph checkpoint 回滚实现：找到上一条消息之前的 checkpoint 并恢复，
    使 Agent 状态回到发送该消息之前。

    生成已改为后台执行（断开 SSE 不再中断），故撤回前需显式取消进行中的后台流，
    否则回滚后生成任务仍会继续写入状态。
    """
    from app.services.agent_engine import get_agent
    from app.services.agent_state import get_checkpointer
    from app.services import agent_streams

    # 先取消该项目进行中的后台生成（若有），确保回滚后不会被继续写入
    await agent_streams.cancel_stream(project_id)

    try:
        checkpointer = await get_checkpointer()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法获取检查点: {str(e)}")

    config = {"configurable": {"thread_id": project_id}}

    # 获取最近2个checkpoint（倒序，最新在前）
    checkpoints = []
    try:
        async for cp in checkpointer.alist(config, limit=2):
            checkpoints.append(cp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取检查点失败: {str(e)}")

    if len(checkpoints) < 2:
        raise HTTPException(
            status_code=400,
            detail="没有可撤回的消息（检查点不足，可能是首条消息或尚未开始对话）",
        )

    # checkpoints[0] = 最新状态（当前），checkpoints[1] = 上一条消息之前的状态
    prev = checkpoints[1]

    try:
        await checkpointer.aput(
            config,
            checkpoint=prev.checkpoint,
            metadata=prev.metadata,
            new_versions=prev.checkpoint.get("channel_versions", {}),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回滚检查点失败: {str(e)}")

    return {
        "success": True,
        "message": "已撤回到上一条消息之前的状态",
    }


@router.get("/agent/projects/{project_id}/history")
async def agent_get_history(project_id: str):
    """获取项目的对话历史（用户消息与Agent回复文本）

    从 LangGraph checkpoint 恢复的 messages 中提取 HumanMessage / AIMessage 的
    文本内容，供前端刷新页面后回顾之前的对话。ToolMessage 和纯工具调用的
    AI消息（无文本）不返回。
    """
    from app.services.agent_engine import get_agent
    from langchain_core.messages import HumanMessage, AIMessage

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = await agent.aget_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取Agent状态: {str(e)}")

    if not state or not state.values:
        return {"messages": [], "count": 0}

    messages = state.values.get("messages", []) or []
    history = []
    for msg in messages:
        # 消息时间戳（agent_engine 创建消息时写入 additional_kwargs["ts"]，随 checkpoint 持久化）
        ts = ((getattr(msg, "additional_kwargs", None) or {}).get("ts")) or ""
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content and content.strip():
                history.append({"role": "user", "content": content, "ts": ts})
        elif isinstance(msg, AIMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content and content.strip():
                history.append({"role": "assistant", "content": content, "ts": ts})

    return {"messages": history, "count": len(history)}


@router.get("/agent/projects")
async def agent_list_projects():
    """列出所有聊天任务（项目）：供前端侧边栏展示多任务切换

    直接从 checkpoint SQLite 库读取全部 thread_id（按最新活动排序），
    再逐个读取 state 提取标题（首条用户消息前30字）与消息数。
    """
    from app.services import agent_state as _agent_state
    from langchain_core.messages import HumanMessage
    import sqlite3

    # 定位 checkpoint 数据库（get_checkpointer 初始化时记录的模块级路径，回退到默认规则）
    db_path = getattr(_agent_state, "_db_path", None)
    if not db_path:
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        db_path = str(project_root / "project_store" / "agent_checkpoints.db")

    def _query_threads():
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            cur = conn.execute(
                "SELECT DISTINCT thread_id FROM checkpoints "
                "WHERE thread_id != '' AND checkpoint_ns = '' "
                "ORDER BY rowid DESC"
            )
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    try:
        thread_ids = await asyncio.to_thread(_query_threads)
    except Exception as e:
        # 表不存在等 → 无任何项目
        return {"projects": []}

    from app.services.agent_engine import get_agent
    agent = get_agent()

    projects = []
    for tid in thread_ids[:100]:  # 上限保护
        # 跳过内部命名空间（如 HITL/子图使用的 'xxx::yyy' 形式）
        if "::" in tid:
            continue
        title = ""
        msg_count = 0
        try:
            state = await agent.aget_state({"configurable": {"thread_id": tid}})
            if state and state.values:
                messages = state.values.get("messages", []) or []
                for msg in messages:
                    if isinstance(msg, HumanMessage):
                        content = msg.content if isinstance(msg.content, str) else ""
                        if content and content.strip():
                            title = content.strip().replace("\n", " ")[:30]
                            break
                msg_count = len(messages)
        except Exception:
            continue
        projects.append({
            "project_id": tid,
            "title": title or "新聊天",
            "message_count": msg_count,
        })

    return {"projects": projects}


@router.delete("/agent/projects/{project_id}")
async def agent_delete_project(project_id: str):
    """删除一个聊天任务（连同其 checkpoint 全部历史）"""
    from app.services import agent_state as _agent_state
    from app.services import agent_streams
    import sqlite3

    # 先取消该项目进行中的后台生成（若有），避免删除后仍向 checkpoint 库写入
    await agent_streams.cancel_stream(project_id)

    db_path = getattr(_agent_state, "_db_path", None) or ""

    def _thread_exists():
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (project_id,))
            return cur.fetchone()[0] > 0
        finally:
            conn.close()

    try:
        if db_path and await asyncio.to_thread(_thread_exists):
            # 优先使用 langgraph 官方删除接口（同时清理 writes 表）
            checkpointer = await _agent_state.get_checkpointer()
            if hasattr(checkpointer, "adelete_thread"):
                await checkpointer.adelete_thread(project_id)
            else:
                def _delete_rows():
                    conn = sqlite3.connect(db_path, timeout=5)
                    try:
                        conn.execute(
                            "DELETE FROM checkpoints WHERE thread_id = ?", (project_id,))
                        conn.execute(
                            "DELETE FROM writes WHERE thread_id = ?", (project_id,))
                        conn.commit()
                    finally:
                        conn.close()
                await asyncio.to_thread(_delete_rows)
        else:
            # 无 db_path 或库中无此线程 → 项目不存在
            raise HTTPException(status_code=404, detail="项目不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除项目失败: {str(e)}")

    return {"success": True, "message": f"项目 {project_id} 已删除"}


@router.delete("/agent/projects/{project_id}/attachments/{file_id}")
async def agent_delete_attachment(project_id: str, file_id: str):
    """删除Agent项目中的指定附件"""
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        current_state = await agent.aget_state(config)
        state_values = dict(current_state.values) if current_state and current_state.values else dict(create_initial_state())
    except Exception:
        raise HTTPException(status_code=404, detail="项目不存在")

    attachments = list(state_values.get("attachments", []) or [])
    original_count = len(attachments)
    attachments = [a for a in attachments if a.get("file_id") != file_id]

    if len(attachments) == original_count:
        raise HTTPException(status_code=404, detail="附件不存在")

    import traceback as _tb
    try:
        await agent.aupdate_state(config, {"attachments": attachments}, as_node="after_tools")
    except Exception as e:
        err_tb = _tb.format_exc()
        print(f"[agent_delete_attachment] aupdate_state 失败:\n{err_tb}")
        raise HTTPException(status_code=500, detail=f"状态更新失败: {type(e).__name__}: {e}")

    return {
        "success": True,
        "message": "附件已删除",
        "remaining": len(attachments),
    }


@router.post("/agent/projects/{project_id}/templates")
async def agent_upload_template(
    project_id: str,
    file: UploadFile = File(..., description="模板文件 (.docx/.pdf/.doc/.txt/.md)"),
    name: str = Form("", description="模板名称"),
    doc_type: str = Form("", description="模板关联的目标文档类型"),
):
    """Agent模式下添加模板

    上传模板文档后自动提取文本，将模板信息（含全文）存入Agent状态 templates 列表。
    模板作为文档风格/结构参照：agent 生成文档时模仿其章节结构与写作风格。

    与普通附件的区别:
    - 模板带 name + doc_type，前端以独立「模板」UI 展示
    - 系统提示词注入「已添加模板（文档风格参照）」指令，agent 优先按模板生成
    - persist=False：模板内容不写入共享向量库，仅作为本项目风格参照，避免污染 RAG
    """
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state

    # 验证文件
    file_content = await file.read()
    is_valid, error_msg = validate_upload(file.filename, len(file_content))
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # 提交提取任务（persist=False 不入共享向量库，模板仅作风格参照）
    task_id = submit_extract_task(
        file_content=file_content,
        filename=file.filename,
        persist=False,
        doc_type=doc_type or "template",
    )

    # 记录模板元数据到任务，供 finalize 端点读取（提取完成后写入 Agent 状态）
    from app.services.attachment_service import extract_tasks
    template_name = (name or "").strip() or file.filename
    extract_tasks[task_id]["template_name"] = template_name
    extract_tasks[task_id]["template_doc_type"] = (doc_type or "").strip()
    # 记录所属项目：刷新/切换后前端可通过 orphan 接口找回并补 finalize
    extract_tasks[task_id]["project_id"] = project_id

    # 提取在后台线程异步执行，立即返回；前端轮询 /api/extract-status/{task_id}，
    # 提取完成后调用 /agent/projects/{project_id}/templates/{task_id}/finalize 写入状态。
    # 避免在请求内同步轮询（MinerU 首次加载模型 + 多页推理可远超 5 分钟导致超时）。
    return {
        "success": True,
        "status": "processing",
        "template_id": task_id,
        "name": template_name,
        "filename": file.filename,
        "doc_type": doc_type,
        "message": f"模板「{template_name}」已接收，正在后台提取文本...",
    }


@router.post("/agent/projects/{project_id}/templates/{template_id}/finalize")
async def agent_finalize_template(project_id: str, template_id: str):
    """将已提取完成的模板文本写入 Agent 状态 templates 列表。

    与 agent_upload_template 配套：上传端点立即返回 processing，前端轮询
    /api/extract-status/{template_id} 至 completed 后调用本端点，
    把提取出的 full_text 写入 Agent 状态，供后续 outline_from_template / write_chapter 参照。
    """
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state
    from app.services.attachment_service import extract_tasks

    task = extract_tasks.get(template_id)
    if not task:
        raise HTTPException(status_code=404, detail="提取任务不存在（服务可能已重启），请重新上传")

    if task.get("status") != "completed":
        raise HTTPException(status_code=409, detail=f"模板文本尚未提取完成（当前状态: {task.get('status')}），请稍后重试")

    full_text = task.get("full_text", "")
    preview = task.get("preview", "")
    char_count = task.get("char_count", 0)
    toc = task.get("toc", "")
    template_name = task.get("template_name") or task.get("filename", "unknown")
    template_doc_type = task.get("template_doc_type", "")

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        current_state = await agent.aget_state(config)
        has_checkpoint = current_state is not None and bool(current_state.values)
        state_values = dict(current_state.values) if has_checkpoint else dict(create_initial_state())
    except Exception:
        has_checkpoint = False
        state_values = dict(create_initial_state())

    templates = list(state_values.get("templates", []) or [])
    # 去重：同一 template_id 已在模板列表（如刷新后孤儿补 finalize 重复触发）则直接返回
    if any(t.get("template_id") == template_id for t in templates):
        task["finalized"] = True
        return {
            "success": True,
            "template_id": template_id,
            "name": template_name,
            "filename": task.get("filename", ""),
            "doc_type": template_doc_type,
            "char_count": char_count,
            "duplicate": True,
            "message": f"模板「{template_name}」已在模板列表中",
        }
    templates.append({
        "template_id": template_id,
        "name": template_name,
        "filename": task.get("filename", ""),
        "doc_type": template_doc_type,
        "char_count": char_count,
        "preview": preview,
        "toc": toc,
        "full_text": full_text,
        "status": "completed",
    })

    import traceback as _tb
    try:
        if has_checkpoint:
            # 已有 checkpoint：仅部分更新 templates 通道
            await agent.aupdate_state(config, {"templates": templates}, as_node="after_tools")
        else:
            # 新项目尚未产生 checkpoint：用完整初始 state seed（含全部通道），
            # 避免只写 templates 部分通道导致 checkpoint 通道不全、刷新后读取异常丢模板
            init = dict(state_values)
            init["templates"] = templates
            await agent.aupdate_state(config, init, as_node="after_tools")
    except Exception as e:
        err_tb = _tb.format_exc()
        print(f"[agent_finalize_template] aupdate_state 失败:\n{err_tb}")
        raise HTTPException(status_code=500, detail=f"状态更新失败: {type(e).__name__}: {e}")

    task["finalized"] = True  # 标记已完成 finalize，孤儿补 finalize 接口据此跳过
    return {
        "success": True,
        "template_id": template_id,
        "name": template_name,
        "filename": task.get("filename", ""),
        "doc_type": template_doc_type,
        "char_count": char_count,
        "preview": preview,
        "message": f"模板「{template_name}」已添加并提取完成 ({char_count} 字符)。"
                   f"Agent生成文档时将参照其章节结构与写作风格。",
    }


@router.get("/agent/templates/orphan")
async def agent_list_orphan_templates():
    """列出「提取已完成但尚未 finalize」的孤儿模板任务。

    用于刷新页面 / 切换聊天任务后找回中途中断的模板上传：
    前端在页面加载时调用本接口，对属于当前项目的孤儿任务逐个补调 finalize，
    使其写入 Agent 状态，避免"后端提取完成但前端轮询中断导致模板丢失"。
    """
    from app.services.attachment_service import extract_tasks

    orphans = []
    for task_id, task in extract_tasks.items():
        # 仅模板任务（有 template_name 标记），且提取已完成、尚未 finalize
        if not task.get("template_name"):
            continue
        if task.get("status") != "completed":
            continue
        if task.get("finalized"):
            continue
        orphans.append({
            "template_id": task_id,
            "project_id": task.get("project_id", ""),
            "name": task.get("template_name", ""),
            "filename": task.get("filename", ""),
            "doc_type": task.get("template_doc_type", ""),
            "char_count": task.get("char_count", 0),
        })
    return {"count": len(orphans), "orphans": orphans}


@router.get("/agent/projects/{project_id}/templates")
async def agent_list_templates(project_id: str):
    """获取Agent项目已添加的模板列表"""
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        current_state = await agent.aget_state(config)
        state_values = current_state.values if current_state and current_state.values else {}
    except Exception as e:
        import traceback as _tb
        print(f"[agent_list_templates] 读取状态失败 (project={project_id}):\n{_tb.format_exc()}")
        state_values = {}

    templates = state_values.get("templates", []) or []

    return {
        "success": True,
        "project_id": project_id,
        "templates": [
            {
                "template_id": t.get("template_id"),
                "name": t.get("name"),
                "filename": t.get("filename"),
                "doc_type": t.get("doc_type"),
                "char_count": t.get("char_count", 0),
                "preview": t.get("preview", ""),
                "status": t.get("status", "unknown"),
            }
            for t in templates
        ],
    }


@router.delete("/agent/projects/{project_id}/templates/{template_id}")
async def agent_delete_template(project_id: str, template_id: str):
    """删除Agent项目中的指定模板"""
    from app.services.agent_engine import get_agent
    from app.services.agent_state import create_initial_state

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        current_state = await agent.aget_state(config)
        state_values = dict(current_state.values) if current_state and current_state.values else dict(create_initial_state())
    except Exception:
        raise HTTPException(status_code=404, detail="项目不存在")

    templates = list(state_values.get("templates", []) or [])
    original_count = len(templates)
    templates = [t for t in templates if t.get("template_id") != template_id]

    if len(templates) == original_count:
        raise HTTPException(status_code=404, detail="模板不存在")

    import traceback as _tb
    try:
        await agent.aupdate_state(config, {"templates": templates}, as_node="after_tools")
    except Exception as e:
        err_tb = _tb.format_exc()
        print(f"[agent_delete_template] aupdate_state 失败:\n{err_tb}")
        raise HTTPException(status_code=500, detail=f"状态更新失败: {type(e).__name__}: {e}")

    return {
        "success": True,
        "message": "模板已删除",
        "remaining": len(templates),
    }


# ═══════════════════════════════════════════════════════════════
# 流程图生成 / 修改 / 导出 / 插入文档接口
# ═══════════════════════════════════════════════════════════════

_FLOWCHART_SYSTEM_PROMPT = """你是专业的医疗器械文档流程图生成助手。根据用户描述生成 mermaid flowchart 源码。

严格要求：
1. 只输出 mermaid flowchart 源码，不要输出任何解释、前言、markdown 围栏或后缀
2. 第一行必须输出 "flowchart TD"（自上而下）；特殊需要可用 "flowchart LR"
3. 节点文字用中文、简短，选用合适形状：
   - 起止节点用 ([文字]) 圆角形状
   - 处理步骤用 [文字] 矩形
   - 判断分支用 {文字} 菱形
4. 连线用 --> 表示，条件分支连线用 -- 条件文字 -->（如 -- 是 -->）
5. 节点数控制在 5~15 个，避免过于复杂
6. 若描述涉及医疗器械领域（风险管理、设计评审、生产工艺、软件开发生命周期等），使用专业术语
7. 保证 mermaid 语法正确、连接关系自洽（有开始、有结束，不出现孤立节点），可直接渲染
"""


def _extract_mermaid_block(text: str) -> str:
    """从 LLM 返回文本中提取 mermaid 源码（优先围栏内内容）。"""
    if not text:
        return ""
    m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    idx = text.find("flowchart")
    if idx >= 0:
        return text[idx:].strip()
    return text.strip()


class FlowchartGenerateRequest(BaseModel):
    """流程图生成/修改请求"""
    prompt: str = Field(..., description="流程描述（生成）或修改指令（修改）")
    current_mermaid: Optional[str] = Field(None, description="当前流程图源码（修改时传入）")


class FlowchartRenderRequest(BaseModel):
    """流程图渲染请求"""
    mermaid: str = Field(..., description="mermaid 源码")


class FlowchartInsertRequest(BaseModel):
    """流程图插入文档请求"""
    mermaid: str = Field(..., description="mermaid 源码")
    section_name: str = Field("", description="目标章节名，为空则新增独立「流程图」章节")


@router.post("/agent/flowchart/generate")
async def agent_generate_flowchart(request: FlowchartGenerateRequest):
    """生成或修改流程图（返回 mermaid 源码）。

    - 生成：只传 prompt
    - 修改：传 prompt（修改指令）+ current_mermaid（当前流程图源码）

    使用本地模型生成 mermaid 源码，前端用 mermaid 渲染预览，插入文档时
    由后端把 mermaid 渲染为 PNG（_add_mermaid_or_fallback）。
    """
    import asyncio
    from app.services.minimax import _call_minimax_api_raw

    prompt = (request.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="描述不能为空")

    current = (request.current_mermaid or "").strip()
    if current:
        user_prompt = (
            f"以下是当前流程图的 mermaid 源码：\n```mermaid\n{current}\n```\n\n"
            f"用户修改要求：{prompt}\n\n"
            f"请根据修改要求调整流程图，保持 mermaid 语法正确，只输出修改后的 mermaid 源码。"
        )
    else:
        user_prompt = f"请根据以下描述生成 mermaid flowchart 源码：{prompt}"

    try:
        result = await asyncio.to_thread(
            _call_minimax_api_raw,
            _FLOWCHART_SYSTEM_PROMPT,
            user_prompt,
            0.3,
            4096,
            (30, 120),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"流程图生成失败: {str(e)}")

    mermaid_code = _extract_mermaid_block(result or "")
    if not mermaid_code:
        raise HTTPException(status_code=500, detail="模型未返回有效的 mermaid 流程图，请重试")

    # 规范化：确保有 flowchart/graph 方向声明（模型有时直接从节点定义开始输出，
    # 缺少方向声明会导致 mermaid 渲染失败）
    first_line = mermaid_code.splitlines()[0].strip() if mermaid_code else ""
    if not re.match(r"^(flowchart|graph)(\s|$)", first_line, re.IGNORECASE):
        mermaid_code = "flowchart TD\n" + mermaid_code

    return {"success": True, "mermaid": mermaid_code}


@router.post("/agent/flowchart/render")
async def agent_render_flowchart(request: FlowchartRenderRequest):
    """将 mermaid 源码渲染为 PNG 图片（供前端「导出 PNG」下载）。"""
    import asyncio
    from app.services.mermaid_render import render_mermaid_to_png

    code = (request.mermaid or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="mermaid 源码不能为空")

    png = await asyncio.to_thread(render_mermaid_to_png, code)
    if not png:
        raise HTTPException(status_code=500, detail="流程图渲染失败（mermaid 语法可能有误或渲染依赖不可用）")

    return StreamingResponse(
        io.BytesIO(png),
        media_type="image/png",
        headers={"Content-Disposition": 'attachment; filename="flowchart.png"'},
    )


@router.post("/agent/projects/{project_id}/flowchart/insert")
async def agent_insert_flowchart(project_id: str, request: FlowchartInsertRequest):
    """把流程图插入到正在生成的文档。

    - section_name 指定 → 追加到该章节末尾
    - section_name 为空 → 新增独立「流程图」章节（多张则「流程图 2」「流程图 3」...）
    """
    from app.services.agent_engine import get_agent

    code = (request.mermaid or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="mermaid 源码不能为空")

    block = f"```mermaid\n{code}\n```"

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}
    try:
        state = await agent.aget_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取Agent状态: {str(e)}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="项目不存在或尚未开始，请先生成文档")

    generated = dict(state.values.get("generated_sections", {}) or {})

    section_name = (request.section_name or "").strip()
    if section_name:
        if section_name not in generated:
            raise HTTPException(
                status_code=404,
                detail=f"章节「{section_name}」不存在，可用章节: {list(generated.keys())}",
            )
        generated[section_name] = generated[section_name].rstrip() + "\n\n" + block
        target = section_name
    else:
        base = "流程图"
        count = sum(1 for k in generated if k.startswith(base))
        target = base if count == 0 else f"{base} {count + 1}"
        generated[target] = block

    import traceback as _tb
    try:
        await agent.aupdate_state(config, {"generated_sections": generated}, as_node="after_tools")
    except Exception as e:
        err_tb = _tb.format_exc()
        print(f"[agent_insert_flowchart] aupdate_state 失败:\n{err_tb}")
        raise HTTPException(status_code=500, detail=f"状态更新失败: {type(e).__name__}: {e}")

    return {
        "success": True,
        "project_id": project_id,
        "section_name": target,
        "message": f"流程图已插入到「{target}」",
    }


@router.get("/agent/projects/{project_id}/download-excel")
async def agent_download_risk_excel(project_id: str):
    """下载风险分析总表的 Excel (.xlsx) 版本。

    仅对风险分析总表类文档（product_risk_analysis_matrix /
    cybersecurity_risk_analysis_matrix）可用：读取项目状态中的产品信息，
    调用本地 Ollama 生成结构化风险条目，按参考文件 17 列两行表头样式构建 .xlsx。
    """
    import asyncio
    from app.services.agent_engine import get_agent
    from app.services.risk_excel import (
        is_risk_matrix_doc, generate_risk_rows, build_risk_excel,
    )

    agent = get_agent()
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = await agent.aget_state(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取Agent状态: {str(e)}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="项目不存在或尚未开始")

    values = state.values
    doc_type = values.get("doc_type", "design_development_plan")

    if not is_risk_matrix_doc(doc_type):
        raise HTTPException(
            status_code=400,
            detail="当前文档类型不支持导出 Excel（仅风险分析和管理总表类文档可用）",
        )

    product_name = values.get("product_name", "") or "贴敷式胰岛素泵"
    classification = values.get("product_classification", "") or ""
    intended_use = values.get("product_intended_use", "") or ""

    rows = await asyncio.to_thread(
        generate_risk_rows, doc_type, product_name, classification, intended_use
    )
    if not rows:
        raise HTTPException(
            status_code=500,
            detail="风险条目生成失败（模型未返回有效数据），请稍后重试",
        )

    file_bytes = await asyncio.to_thread(build_risk_excel, doc_type, rows)

    filename = f"{product_name}_风险分析和管理总表.xlsx"
    from urllib.parse import quote
    encoded_filename = quote(filename)

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )
