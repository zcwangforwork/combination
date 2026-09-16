"""
Agent State Management - 设计策划文档Agent状态管理

基于PRD Section 4.3的运行时状态快照设计。
使用LangGraph TypedDict + SqliteSaver实现持久化。
"""
import os
from pathlib import Path
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


# ── State Schema (PRD Section 4.3 状态快照) ──

class AgentState(TypedDict, total=False):
    """设计策划文档Agent的全局状态

    与PRD Section 4.3的JSON状态快照一一对应。
    LangGraph自动通过SqliteSaver持久化此状态。
    """
    # ── 消息历史 ──
    messages: Annotated[list[BaseMessage], add_messages]

    # ── 步骤1: 产品画像 ──
    product_name: Optional[str]
    product_classification: Optional[str]
    product_intended_use: Optional[str]
    product_status: Optional[str]  # "confirmed" | "partial"

    # ── 步骤2: 标准适用性清单 ──
    confirmed_standards: list[str]
    candidate_standards: list[str]
    standards_status: Optional[str]  # "confirmed" | "partial" | "not_started"

    # ── 步骤3: 结构化内容采集 ──
    # 结构: {内容域: {status, items_confirmed, items_skipped}}
    content_sections: dict

    # ── 步骤4: 文档生成 ──
    generated_sections: dict   # {章节标题: content}
    document_status: Optional[str]

    # ── 步骤5: 追溯矩阵 ──
    traceability_status: Optional[str]

    # ── 步骤6: 审核+评审 ──
    review_status: Optional[str]

    # ── 待处理项 ──
    unresolved_items: list[str]

    # ── 文档类型 ──
    doc_type: Optional[str]  # 目标文档类型 (design_development_plan, risk_management_plan, etc.)

    # ── 自动模式 ──
    auto_mode: Optional[bool]  # True时跳过所有HITL确认

    # ── 文档风格 ──
    writing_style: Optional[str]  # 文档语言风格: "concise"=精炼简洁 | "detailed"=严谨详细（仅文档内容，不影响聊天回复）

    # ── 补充提示词 ──
    supplementary_prompts: Optional[str]  # 累积的用户补充提示词，追加到文档生成提示词末尾（纯补充，不破坏原有提示词）

    # ── 多代理协作 ──
    outline: Optional[str]          # JSON字符串, 完整的文档框架
    outline_status: Optional[str]   # "not_started" | "draft" | "confirmed" | "revised"
    current_chapter: Optional[str]  # 当前正在生成/审核的章节名
    chapter_write_queue: list[str]  # 待生成章节列表 (章节名称)

    # ── 附件管理 ──
    # 结构: [{"file_id": str, "filename": str, "char_count": int, "preview": str, "full_text": str, "status": str}, ...]
    attachments: list[dict]

    # ── 模板管理 (添加模板功能) ──
    # 结构: [{"template_id": str, "name": str, "filename": str, "doc_type": str,
    #         "char_count": int, "preview": str, "toc": str, "full_text": str,
    #         "status": str}, ...]
    # 模板作为文档风格/结构参照，区别于普通附件：agent 生成文档时模仿其章节结构与写作风格
    templates: list[dict]
    # 模板风格总结：analyze_template_style 工具对模板提炼的结构化写作风格描述，
    # 供 write_chapter 注入（优先于原文片段，更精炼、更有指导性）
    template_style_summary: Optional[str]

    # ── 附件修改结果 ──
    # 结构: [{"file_id": str, "filename": str, "modified_markdown": str, "summary": str,
    #         "modified_chars": int, "timestamp": str, "download_id": str}, ...]
    # 独立于 generated_sections：修改的是上传附件的副本，不污染目标文档章节
    attachment_modifications: list[dict]

    # ── 撤销栈（单步回退） ──
    # 每次覆盖 generated_sections 章节 或 追加 attachment_modifications 前，压入一个快照条目。
    # 结构: [{"sections_before": {章节名: 旧内容或None}, "attachments_before_len": int,
    #         "removed_file_ids": [file_id, ...], "description": str}, ...]
    # None 表示该章节在变更前不存在（回退时应删除）；attachments_before_len 为变更前列表长度（回退时截断）。
    undo_stack: list[dict]

    # ── OpenViking 记忆上下文与活动记录 ──
    # ov_recall 节点检索到的历史记忆（注入 system prompt）；agent 节点回填本轮活动
    memory_context: Optional[str]
    # 最近一次 OpenViking 活动（前端展示用）: {"kind": "recall"|"capture", "count": int}
    ov_activity: Optional[dict]

    # ── PostgreSQL 长期记忆上下文（pgvector 语义检索） ──
    # ltm_recall 节点检索到的长期记忆（注入 system prompt，与 memory_context 合并）
    long_term_memory_context: Optional[str]
    # 最近一次长期记忆活动（调试/前端展示用）: {"kind": "recall"|"capture", "count": int}
    long_term_memory_activity: Optional[dict]

    # ── 附件→章节预分配映射 ──
    # write_chapter 首次调用时构建（LLM 通读全部附件，判定各块适合哪些章节），
    # 随 checkpoint 持久化；outline/附件集合变化（哈希）时自动重建。
    # 结构: {"outline_hash": str, "attachments_hash": str,
    #        "chapters": {章节名: {"blocks": [{file_id, filename, text, reason,
    #                                           subsections: [小节名], priority}], "hint": str}}}
    attachment_chapter_map: Optional[dict]

    # ── 模板分节对位映射 ──
    # write_chapter 首次调用时构建（LLM 通读模板，为每章找到最值得参照的模板节），
    # 随 checkpoint 持久化；outline/模板集合变化（哈希）时自动重建。
    # 结构: {"outline_hash": str, "templates_hash": str,
    #        "chapters": {章节名: {"blocks": [{filename, section_path, text, reason}], "hint": str}}}
    template_chapter_map: Optional[dict]


# ── 默认初始状态 ──

def create_initial_state() -> AgentState:
    """创建新项目的默认空状态"""
    return AgentState(
        messages=[],
        product_name=None,
        product_classification=None,
        product_intended_use=None,
        product_status="not_started",
        confirmed_standards=[],
        candidate_standards=[],
        standards_status="not_started",
        content_sections={},
        generated_sections={},
        document_status="not_started",
        traceability_status="not_started",
        review_status="not_started",
        unresolved_items=[],
        auto_mode=False,
        writing_style="concise",
        supplementary_prompts=None,
        outline=None,
        outline_status="not_started",
        current_chapter=None,
        chapter_write_queue=[],
        attachments=[],
        attachment_modifications=[],
        undo_stack=[],
        templates=[],
        template_style_summary=None,
        memory_context=None,
        ov_activity=None,
        long_term_memory_context=None,
        long_term_memory_activity=None,
        attachment_chapter_map=None,
        template_chapter_map=None,
    )


# ── SqliteSaver 实例管理 ──

_checkpointer_instance: Optional[AsyncSqliteSaver] = None
_ctx = None  # from_conn_string() returns async context manager in 3.x
_db_path: Optional[str] = None


async def get_checkpointer(db_path: Optional[str] = None) -> AsyncSqliteSaver:
    """获取或创建SqliteSaver检查点实例（单例）

    Args:
        db_path: SQLite数据库路径，默认在项目根目录 project_store/
    """
    global _checkpointer_instance, _ctx, _db_path

    if db_path is None:
        project_root = Path(__file__).parent.parent.parent
        db_dir = project_root / "project_store"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(db_dir / "agent_checkpoints.db")

    # 如果路径变了，关闭旧实例
    if _checkpointer_instance is not None and db_path != _db_path:
        if _ctx:
            try:
                await _ctx.__aexit__(None, None, None)
            except Exception:
                pass
            _ctx = None
        _checkpointer_instance = None

    if _checkpointer_instance is None:
        # from_conn_string() returns async context manager (not awaitable) in 3.x
        _ctx = AsyncSqliteSaver.from_conn_string(db_path)
        _checkpointer_instance = await _ctx.__aenter__()
        _db_path = db_path

    return _checkpointer_instance


async def close_checkpointer():
    """关闭检查点实例（应用关闭时调用）"""
    global _checkpointer_instance, _ctx
    if _ctx:
        try:
            await _ctx.__aexit__(None, None, None)
        except Exception:
            pass
        _ctx = None
    _checkpointer_instance = None


# ── 状态辅助函数 ──

def build_state_snapshot(state: AgentState) -> dict:
    """从State提取JSON快照，用于注入System Prompt

    对应PRD Section 4.3的JSON结构
    """
    return {
        "writing_style": state.get("writing_style", "concise") or "concise",
        "supplementary_prompts": state.get("supplementary_prompts"),
        "product": {
            "name": state.get("product_name"),
            "classification": state.get("product_classification"),
            "intended_use": state.get("product_intended_use"),
            "status": state.get("product_status", "not_started"),
        },
        "standards": {
            "confirmed": state.get("confirmed_standards", []),
            "candidate": state.get("candidate_standards", []),
            "status": state.get("standards_status", "not_started"),
        },
        "content_sections": state.get("content_sections", {}),
        "document_generation": {
            "status": state.get("document_status", "not_started"),
            "sections_generated": list(state.get("generated_sections", {}).keys()),
            "doc_type": state.get("doc_type", "design_development_plan"),
        },
        "traceability": {"status": state.get("traceability_status", "not_started")},
        "review": {"status": state.get("review_status", "not_started")},
        "unresolved_items": state.get("unresolved_items", []),
        "outline": {
            "status": state.get("outline_status", "not_started"),
            "chapters_count": _count_chapters(state.get("outline")),
        },
        "multi_agent": {
            "current_chapter": state.get("current_chapter"),
            "pending_chapters": state.get("chapter_write_queue", []),
        },
        # PostgreSQL 长期记忆活动（仅暴露轻量元信息，避免记忆正文膨胀 system prompt）
        "long_term_memory": {
            "has_injected_context": bool(state.get("long_term_memory_context")),
            "last_activity_kind": (state.get("long_term_memory_activity") or {}).get("kind"),
            "last_activity_count": (state.get("long_term_memory_activity") or {}).get("count", 0),
        },
        "attachments": [
            {
                "file_id": a.get("file_id"),
                "filename": a.get("filename"),
                "relative_path": a.get("relative_path"),
                "char_count": a.get("char_count", 0),
                "preview": a.get("preview", ""),
                "status": a.get("status", "unknown"),
            }
            for a in state.get("attachments", [])
        ],
        "templates": [
            {
                "template_id": t.get("template_id"),
                "name": t.get("name"),
                "filename": t.get("filename"),
                "doc_type": t.get("doc_type"),
                "char_count": t.get("char_count", 0),
                "status": t.get("status", "unknown"),
            }
            for t in state.get("templates", [])
        ],
    }


def _count_chapters(outline_json: Optional[str]) -> int:
    """从框架JSON中提取章节数"""
    if not outline_json:
        return 0
    try:
        import json
        data = json.loads(outline_json)
        return len(data.get("chapters", []))
    except (json.JSONDecodeError, TypeError):
        return 0
