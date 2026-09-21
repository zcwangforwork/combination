"""
Agent Tools — 设计策划文档Agent工具集 (Phase 1: 4核心工具)

Tool 1: search_kb     — 检索贴敷式胰岛素泵知识库
Tool 2: generate_section — 基于策划内容生成指定章节
Tool 3: revise_section   — 根据用户指令修改章节内容
Tool 4: build_docx       — 构建Word文档并提供下载

所有工具封装为LangChain Tool，直接复用现有模块 (minimax.py, vector_store.py)
"""
import json
import os
import time
import asyncio
import contextvars
import math
import statistics
from langchain_core.tools import tool

# 跨工具共享: _after_tools_node 写入, build_docx 读取
# 使用 contextvars 确保 async task 隔离
_current_generated_markdown: contextvars.ContextVar[str] = contextvars.ContextVar(
    'generated_markdown', default=''
)
_current_product_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    'product_name', default=''
)
_current_doc_type: contextvars.ContextVar[str] = contextvars.ContextVar(
    'doc_type', default='design_development_plan'
)


_current_attachments: contextvars.ContextVar[list[dict]] = contextvars.ContextVar(
    'attachments', default=[]
)

# 模板上下文（添加模板功能）：存储用户添加的模板文档列表，供 outline_from_template 读取
_current_templates: contextvars.ContextVar[list[dict]] = contextvars.ContextVar(
    'templates', default=[]
)

# 产品画像上下文（供 generate_search_query 等工具读取）
_current_product_classification: contextvars.ContextVar[str] = contextvars.ContextVar(
    'product_classification', default=''
)
_current_product_intended_use: contextvars.ContextVar[str] = contextvars.ContextVar(
    'product_intended_use', default=''
)
_current_confirmed_standards: contextvars.ContextVar[list] = contextvars.ContextVar(
    'confirmed_standards', default=[]
)

# 补充提示词上下文：累积的用户补充要求，追加到文档生成提示词末尾
_current_supplementary_prompts: contextvars.ContextVar[str] = contextvars.ContextVar(
    'supplementary_prompts', default=''
)

# 记忆上下文：ov_recall/ltm_recall 检索到的记忆（合并后），注入文档生成提示词，
# 让跨会话/跨轮记忆（用户偏好、项目背景、历史决策）参与章节/小节写作
_current_memory_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    'memory_context', default=''
)

# 模板风格总结上下文：analyze_template_style 提炼的写作风格描述，注入文档生成提示词
_current_template_style_summary: contextvars.ContextVar[str] = contextvars.ContextVar(
    'template_style_summary', default=''
)

# 流式输出通道：文档生成/修改工具把 LLM 的「思维链 + 正文」chunk 推入此队列，
# 由 agent_engine 的 stream_agent_events 并发 drain 后以 doc_token 事件推给前端。
# 无 sink（None）时工具退化为普通阻塞调用，不影响非流式路径。
_current_stream_sink: contextvars.ContextVar = contextvars.ContextVar(
    'stream_sink', default=None
)

# 用户文档格式要求（set_document_format 工具设置，build_docx/导出时应用）
_current_document_format: contextvars.ContextVar[dict] = contextvars.ContextVar(
    'document_format', default={}
)

# 历史用户消息（agent_engine._sync_doc_context 从 state 同步），供生成/修改工具
# 构建「历史用户要求累积参考」块——修改时不丢弃前几轮的关键要求
_current_user_messages: contextvars.ContextVar[list] = contextvars.ContextVar(
    'user_messages', default=[]
)

_DEGENERATE_USER_MSGS = ("继续", "好的", "确认", "可以", "开始", "下一步", "是", "对", "嗯")


def set_current_user_messages(texts: list) -> None:
    """由 agent_engine 在每轮开始前调用，同步历史用户消息文本（时间升序）。"""
    _current_user_messages.set(list(texts or []))


def _user_requirements_block(current_instruction: str = "", max_msgs: int = 10) -> str:
    """历史用户要求累积参考块：修改/生成时兼顾前几轮用户的关键要求。

    规则：与当前指令不冲突的历史要求必须继续遵守；冲突时以当前指令为准。
    过滤退化消息（"继续/确认"等），每条截断 300 字，取最近 max_msgs 条。
    """
    msgs = [t.strip() for t in (_current_user_messages.get() or []) if t and t.strip()]
    substantive = []
    for t in msgs:
        if t.lower() in _DEGENERATE_USER_MSGS or len(t) < 4:
            continue
        substantive.append(t)
    # 排除与当前指令相同的那条（当前指令已在工具参数里）
    if current_instruction:
        cur = current_instruction.strip()
        substantive = [t for t in substantive if t != cur and cur not in t]
    if not substantive:
        return ""
    recent = substantive[-max_msgs:]
    lines = []
    for i, t in enumerate(recent, 1):
        t_cut = t[:300] + ("…" if len(t) > 300 else "")
        lines.append(f"[要求{i}] {t_cut}")
    return (
        "\n## 历史用户要求（累积参考，时间从早到近）\n"
        "以下是用户在本会话中先前提出的要求。执行本次任务时：\n"
        "- 与本次指令**不冲突**的历史要求必须继续遵守/保持（不得因本次修改而丢失）\n"
        "- 与本次指令**冲突**时，以本次指令为准（历史要求中被冲突覆盖的部分作废）\n"
        + "\n".join(lines) + "\n"
    )
_pending_document_format: dict = {}  # 旁路：工具写 → after_tools 写回 state


def set_current_document_format(fmt: dict) -> None:
    """由 agent_engine 在每轮开始前调用，同步当前文档格式要求"""
    _current_document_format.set(fmt or {})


def pop_pending_document_format() -> dict | None:
    """读取并清除待写回 state 的文档格式要求（无更新时返回 None）。"""
    return _pending_document_format.pop("format", None)

# write_chapter 完整内容旁路: 工具返回简短摘要，完整内容通过此字典
# 传递给 _after_tools_node，避免大段内容进入 LLM 对话历史。
# 使用模块级 dict 而非 contextvar，避免 LangGraph 异步节点切换时
# contextvar 丢失导致回退到 JSON 摘要被写入文档。
_pending_chapter_contents: dict = {}  # {chapter_name: full_content}

# modify_attachment 完整内容旁路: 工具返回简短JSON摘要，完整修改后文档通过此字典
# 传递给 _after_tools_node（复用 write_chapter 的旁路模式，避免大段内容进入 LLM 对话历史）。
# 使用模块级 dict 而非 contextvar，避免 LangGraph 异步节点切换时 contextvar 丢失。
_pending_modified_documents: dict = {}  # {file_id: {"markdown": str, "filename": str}}


def get_pending_modified_document(file_id: str) -> dict | None:
    """读取并删除 modify_attachment 写入的指定附件修改结果"""
    return _pending_modified_documents.pop(file_id, None)


def set_current_doc_context(
    doc_type: str,
    product_name: str,
    markdown: str,
    product_classification: str = '',
    product_intended_use: str = '',
    confirmed_standards: list = None,
    supplementary_prompts: str = '',
    template_style_summary: str = '',
    memory_context: str = '',
) -> None:
    """由 agent_engine 在每轮开始前调用，同步当前文档上下文"""
    _current_doc_type.set(doc_type)
    _current_product_name.set(product_name)
    _current_generated_markdown.set(markdown)
    _current_product_classification.set(product_classification or '')
    _current_product_intended_use.set(product_intended_use or '')
    _current_confirmed_standards.set(confirmed_standards or [])
    _current_supplementary_prompts.set(supplementary_prompts or '')
    _current_template_style_summary.set(template_style_summary or '')
    _current_memory_context.set(memory_context or '')


def set_current_attachments(attachments: list[dict]) -> None:
    """由 agent_engine 在每轮开始前调用，同步当前附件列表"""
    _current_attachments.set(attachments or [])


def set_current_templates(templates: list[dict]) -> None:
    """由 agent_engine 在每轮开始前调用，同步当前模板列表"""
    _current_templates.set(templates or [])


def set_stream_sink(queue) -> None:
    """设置/清除流式输出通道（agent_engine 在流式生成前后调用，传 None 清除）。"""
    _current_stream_sink.set(queue)


def push_stream_chunk(kind: str, text: str) -> None:
    """向当前流式 sink 推入一个 chunk（对话/文档通用），供 agent_engine 并发 drain。

    kind 取值:
    - "chat_content" / "chat_reasoning"  → 主 agent 对话正文/思维链
    - "thinking" / "content"             → 文档工具思维链/正文
    无 sink（非流式调用）时静默忽略。
    """
    if not text:
        return
    sink = _current_stream_sink.get()
    if sink is None:
        return
    try:
        sink.put_nowait((kind, text))
    except Exception:
        pass


async def _stream_llm_to_sink(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 16384,
    temperature: float = 0.3,
    enable_thinking: bool = True,
) -> str:
    """文档生成/修改工具的 LLM 调用（阻塞）。

    历史上曾把「思维链 + 正文」流式推送到前端右侧面板；前端已下线文档流式输出
    （仅保留对话正文/思维链），本函数恢复为普通阻塞调用（think: False），
    避免 qwen3 思考拖慢文档生成并额外消耗 token。
    """
    from app.services.minimax import _call_minimax_api_raw
    return await asyncio.to_thread(
        _call_minimax_api_raw,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _attachments_hint(attachments: list[dict]) -> str:
    """生成可用附件清单（file_id + filename），供 not_found 错误提示 LLM 用正确 id 重试"""
    return ", ".join(f"{a.get('file_id')} ({a.get('filename', '?')})" for a in attachments) or "（无）"


# ═══════════════════════════════════════════════════════════════
# 附件→章节提示词预分配（详见 docs/code_writer_docs/附件-章节提示词预分配技术方案.md）
# 三阶段：①全文切语义块（纯代码）→ ②LLM 逐附件通读并分配块到章节 → ③生成时定向注入
# ═══════════════════════════════════════════════════════════════

# 切分与注入阈值
_ATT_MAP_BLOCK_MAX_CHARS = 800       # 单块目标长度上限（超出按句边界二次切分）
_ATT_MAP_SEGMENT_CHARS = 30000       # 单次映射 LLM 调用的附件正文字数上限（超长分段）
_ATT_MAP_MAX_BLOCKS_PER_CHAPTER = 10  # 每章注入块数上限
_ATT_MAP_MAX_CHARS_PER_CHAPTER = 6000  # 每章注入正文字数上限
_ATT_MAP_MAX_BLOCKS_PER_ATTACHMENT = 200  # 每附件块数上限

# 当前附件→章节映射（agent_engine._sync_doc_context 从 state 同步到 contextvar）
_current_attachment_map: contextvars.ContextVar[dict] = contextvars.ContextVar(
    'attachment_chapter_map', default={}
)

# 映射旁路：write_chapter 构建映射后写入，_after_tools_node 读出并写回 state
# （复用 _pending_chapter_contents 模式，避免大内容进入 LLM 对话历史）
_pending_attachment_map: dict = {}

# 进程级映射缓存：按内容哈希键控（outline+附件集合），跨轮次/跨线程正确复用
_attachment_map_cache: dict = {}


def set_current_attachment_map(mapping: dict) -> None:
    """由 agent_engine 在每轮开始前调用，同步当前附件映射"""
    _current_attachment_map.set(mapping or {})


def pop_pending_attachment_map() -> dict | None:
    """读取并清除待写回 state 的附件映射（无新构建时返回 None）。"""
    return _pending_attachment_map.pop("map", None)


def _att_map_hashes(outline_json: str, attachments: list) -> tuple:
    """计算映射失效键：(outline 哈希, 附件集合哈希)。"""
    import hashlib
    outline_hash = hashlib.md5((outline_json or "").encode("utf-8")).hexdigest()
    att_keys = sorted(f"{a.get('file_id', '')}:{a.get('filename', '')}:{a.get('char_count', 0)}"
                      for a in (attachments or []) if a.get("full_text"))
    attachments_hash = hashlib.md5("|".join(att_keys).encode("utf-8")).hexdigest()
    return outline_hash, attachments_hash


def _segment_attachment_blocks(file_id: str, filename: str, full_text: str,
                               max_blocks: int = _ATT_MAP_MAX_BLOCKS_PER_ATTACHMENT) -> list[dict]:
    """把附件全文切成语义块（标题感知 + 段落打包 + 表格保护）。

    - 按 markdown 标题（#~######）切节，维护标题链作为 section_path
    - 节内按空行分段，贪心打包到 _ATT_MAP_BLOCK_MAX_CHARS；单段超长按句边界二次切分
    - 表格行（| 开头）与其邻近行不拆散（归入同一段）
    - 超过 max_blocks 截断（保留前面的块）
    """
    import re as _re

    blocks: list[dict] = []
    heading_stack: list = []  # [(level, title)]
    buf_lines: list = []
    section_path = ""

    def _flush():
        nonlocal buf_lines
        if not buf_lines:
            return
        text = "\n".join(buf_lines).strip()
        buf_lines = []
        if not text:
            return
        # 节内按空行分段；表格行与邻行合并为一个段落单元
        paras: list[str] = []
        cur: list = []
        for ln in text.split("\n"):
            if not ln.strip() and not (cur and cur[0].lstrip().startswith("|")):
                if cur:
                    paras.append("\n".join(cur).strip())
                    cur = []
                continue
            cur.append(ln)
        if cur:
            paras.append("\n".join(cur).strip())
        paras = [p for p in paras if p]
        # 贪心打包到目标块大小；超长单段按句边界切分
        packed: list[str] = []
        acc = ""
        for p in paras:
            while len(p) > _ATT_MAP_BLOCK_MAX_CHARS:
                # 句边界二次切分
                cut = _ATT_MAP_BLOCK_MAX_CHARS
                for m in _re.finditer(r"[。！？.!?；;]", p[:_ATT_MAP_BLOCK_MAX_CHARS]):
                    cut = m.end()
                piece, p = p[:cut], p[cut:]
                if acc:
                    packed.append(acc)
                    acc = ""
                packed.append(piece)
            if not p:
                continue
            if acc and len(acc) + len(p) + 2 > _ATT_MAP_BLOCK_MAX_CHARS:
                packed.append(acc)
                acc = p
            else:
                acc = (acc + "\n\n" + p) if acc else p
        if acc:
            packed.append(acc)
        for piece in packed:
            if len(blocks) >= max_blocks:
                return
            blocks.append({
                "block_id": f"att-{(file_id or 'x')[:6]}-b{len(blocks) + 1:03d}",
                "file_id": file_id,
                "filename": filename,
                "section_path": section_path,
                "text": piece,
            })

    for line in (full_text or "").split("\n"):
        s = line.strip()
        m = _re.match(r"^(#{1,6})\s+(.+)$", s)
        if m:
            _flush()
            level = len(m.group(1))
            heading_stack = [h for h in heading_stack if h[0] < level]
            heading_stack.append((level, m.group(2).strip()))
            section_path = " > ".join(t for _, t in heading_stack)
        else:
            buf_lines.append(line)
    _flush()
    return blocks


_ATT_MAP_SYSTEM_PROMPT = """你是文档参考资料分配专家。给定待生成文档的完整框架和一篇参考文档的内容块清单，
判断每个内容块适合作为哪些章节/小节的参考资料。输出严格 JSON（不要代码围栏、不要解释文字）：
{"assignments": [{"block_id": "...", "chapters": ["章节名"], "subsections": ["小节名"],
  "reason": "≤30字理由", "priority": "high"}], "chapter_hints": {"章节名": "该章选用提示≤50字"}}
规则：
- chapters/subsections 必须使用框架中出现过的准确名称（照抄，不要改写）
- 与任何章节都无关的块不要出现在 assignments 中（宁缺毋滥）
- 含具体参数、实测数据、法规条款、技术指标的块 priority 填 "high"，其余填 "normal"
- 一个块可以同时分配给多个章节（如通用参数）"""


def _outline_compact(outline_json: str) -> str:
    """把框架 JSON 压缩为映射用的紧凑序列化（章→小节→要点）。"""
    try:
        outline = json.loads(outline_json) if isinstance(outline_json, str) else outline_json
    except Exception:
        return (outline_json or "")[:4000]
    lines = []
    for ch in (outline.get("chapters") or []):
        lines.append(f"# {ch.get('title', '')}")
        for sec in (ch.get("sections") or []):
            for sub in (sec.get("subsections") or []):
                pts = sub.get("content_points") or []
                pts_str = "；".join(str(p) for p in pts[:4])
                lines.append(f"- {sub.get('title', '')}" + (f"：{pts_str}" if pts_str else ""))
    return "\n".join(lines)


def _parse_att_map_json(raw: str) -> dict:
    """解析映射 LLM 输出（容忍围栏/前后杂质的脏 JSON）。"""
    import re as _re
    raw = (raw or "").strip()
    raw = _re.sub(r"^```(?:json)?\s*", "", raw)
    raw = _re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except Exception:
        m = _re.search(r"\{.*\}", raw, _re.S)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
        except Exception:
            return {}
    return data if isinstance(data, dict) else {}


async def _map_attachments_to_outline(outline_json: str, attachments: list) -> dict:
    """LLM 逐附件通读全文，构建 块→章节 分配映射（设计方案 Phase 2）。

    每个附件至少一次映射调用（超长按 _ATT_MAP_SEGMENT_CHARS 分段）；失败静默跳过该附件。
    返回 {"outline_hash", "attachments_hash", "chapters": {章节名: {"blocks", "hint"}}}。
    """
    from app.services.minimax import _call_minimax_api_raw

    outline_hash, attachments_hash = _att_map_hashes(outline_json, attachments)
    compact_outline = _outline_compact(outline_json)
    chapters: dict = {}  # 章节名 -> {"blocks": [...], "hint": str}

    for att in (attachments or []):
        full_text = (att.get("full_text") or "").strip()
        if not full_text:
            continue
        file_id = att.get("file_id", "")
        filename = att.get("filename", "unknown")
        blocks = _segment_attachment_blocks(file_id, filename, full_text)
        if not blocks:
            continue

        # 按 _ATT_MAP_SEGMENT_CHARS 分段调用（保持 block_id 连续）
        seg: list = []
        seg_chars = 0
        segments: list = []
        for b in blocks:
            if seg and seg_chars + len(b["text"]) > _ATT_MAP_SEGMENT_CHARS:
                segments.append(seg)
                seg, seg_chars = [], 0
            seg.append(b)
            seg_chars += len(b["text"])
        if seg:
            segments.append(seg)

        for seg_blocks in segments:
            blocks_text = "\n".join(
                f"[{b['block_id']}] {'（' + b['section_path'] + '）' if b['section_path'] else ''}\n{b['text']}"
                for b in seg_blocks
            )
            user_prompt = (
                f"## 待生成文档框架\n{compact_outline}\n\n"
                f"## 参考文档：《{filename}》（共{len(blocks)}块，本批{len(seg_blocks)}块）\n{blocks_text}\n\n"
                f"请输出这些块的分配 JSON。"
            )
            try:
                raw = await asyncio.to_thread(
                    _call_minimax_api_raw,
                    system_prompt=_ATT_MAP_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.2,
                    max_tokens=4096,
                )
            except Exception:
                continue
            data = _parse_att_map_json(raw or "")
            block_by_id = {b["block_id"]: b for b in seg_blocks}
            for asg in (data.get("assignments") or []):
                if not isinstance(asg, dict):
                    continue
                bid = asg.get("block_id", "")
                blk = block_by_id.get(bid)
                if not blk:
                    continue
                for ch_name in (asg.get("chapters") or []):
                    if not isinstance(ch_name, str) or not ch_name.strip():
                        continue
                    entry = chapters.setdefault(ch_name.strip(), {"blocks": [], "hint": ""})
                    entry["blocks"].append({
                        "file_id": blk["file_id"],
                        "filename": blk["filename"],
                        "section_path": blk["section_path"],
                        "text": blk["text"],
                        "reason": (asg.get("reason") or "")[:60],
                        "subsections": [s for s in (asg.get("subsections") or [])
                                        if isinstance(s, str) and s.strip()],
                        "priority": "high" if asg.get("priority") == "high" else "normal",
                    })
            for ch_name, hint in (data.get("chapter_hints") or {}).items():
                if isinstance(ch_name, str) and isinstance(hint, str):
                    entry = chapters.setdefault(ch_name.strip(), {"blocks": [], "hint": ""})
                    entry["hint"] = hint[:80]

    # 每章上限：high 优先，其余按出现序；超限截断
    for ch_name, entry in chapters.items():
        entry["blocks"].sort(key=lambda b: 0 if b["priority"] == "high" else 1)
        kept, total = [], 0
        for b in entry["blocks"]:
            if len(kept) >= _ATT_MAP_MAX_BLOCKS_PER_CHAPTER or total >= _ATT_MAP_MAX_CHARS_PER_CHAPTER:
                break
            kept.append(b)
            total += len(b["text"])
        entry["blocks"] = kept

    return {
        "outline_hash": outline_hash,
        "attachments_hash": attachments_hash,
        "chapters": chapters,
    }


async def _get_or_build_attachment_map(outline_json: str) -> dict:
    """获取当前框架对应的附件映射（懒加载 + 哈希失效 + 多级缓存）。

    优先级：contextvar（本轮 state 同步）→ 进程级缓存（哈希键控）→ 构建（LLM 通读）。
    构建结果写入 _pending_attachment_map 旁路（由 _after_tools_node 持久化到 state）。
    """
    attachments = [a for a in (_current_attachments.get() or []) if a.get("full_text")]
    if not attachments or not (outline_json or "").strip():
        return {}
    outline_hash, attachments_hash = _att_map_hashes(outline_json, attachments)

    # contextvar（state 同步来的）
    current = _current_attachment_map.get() or {}
    if (current.get("outline_hash") == outline_hash
            and current.get("attachments_hash") == attachments_hash):
        return current
    # 进程级缓存
    cache_key = f"{outline_hash}:{attachments_hash}"
    cached = _attachment_map_cache.get(cache_key)
    if cached is not None:
        set_current_attachment_map(cached)  # 同步 contextvar，本轮注入可读
        return cached
    # 构建（LLM 通读全部附件）
    mapping = await _map_attachments_to_outline(outline_json, attachments)
    if mapping.get("chapters"):
        _attachment_map_cache[cache_key] = mapping
        if len(_attachment_map_cache) > 16:
            _attachment_map_cache.pop(next(iter(_attachment_map_cache)))
        _pending_attachment_map["map"] = mapping
        set_current_attachment_map(mapping)  # 同步 contextvar，本轮注入可读
        print(f"[agent_tools] 附件→章节映射已构建: {len(mapping['chapters'])} 章 "
              f"({len(attachments)} 个附件已通读)")
    return mapping


def _assigned_attachment_block(chapter_name: str, sub_title: str = "") -> str:
    """格式化分配给指定章节（小节）的附件块，作为最高优先参考资料注入。

    小节级过滤：块标了 subsections 且当前小节能匹配 → 注入；块未标小节 → 视为章级块注入。
    无映射/无分配返回空串。
    """
    mapping = _current_attachment_map.get() or {}
    entry = None
    for ch, e in (mapping.get("chapters") or {}).items():
        if _same_chapter(ch, chapter_name):
            entry = e
            break
    if not entry:
        return ""
    sub_key = (sub_title or "").replace(" ", "")
    blocks = [b for b in entry.get("blocks", [])
              if not b.get("subsections")
              or any(_same_chapter(s.replace(" ", ""), sub_key) or sub_key in s.replace(" ", "")
                     for s in b["subsections"])]
    if not blocks:
        return ""
    lines = []
    hint = (entry.get("hint") or "").strip()
    if hint:
        lines.append(f"[选用指引] {hint}")
    for b in blocks:
        sec = f" | {b['section_path']}" if b.get("section_path") else ""
        reason = f" | 理由: {b['reason']}" if b.get("reason") else ""
        lines.append(f"[附件块 |《{b['filename']}》{sec}{reason}]\n{b['text']}")
    return "\n\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 模板贴近增强：①风格总结懒加载（write_chapter 自动补，不依赖主 agent 自觉）
# ②模板分节对位映射（每个目标章节 → 模板中最值得参照的节，逐章对位模仿写法）
# ═══════════════════════════════════════════════════════════════

async def _analyze_template_style_core() -> str:
    """分析模板写作风格的核心实现（analyze_template_style 工具与懒加载共用）。

    返回风格总结正文；无模板/无文本/API 失败返回空串（静默）。
    """
    import re as _re
    from app.services.minimax import _call_minimax_api_raw

    templates = _current_templates.get()
    text_parts = []
    for tpl in (templates or []):
        ft = tpl.get("full_text", "")
        if not ft or not ft.strip():
            continue
        fn = tpl.get("filename", "unknown")
        text_parts.append(f"【模板「{fn}」】\n{_template_body_sample(ft)}")
    if not text_parts:
        return ""

    text_sample = "\n\n".join(text_parts)
    if len(text_sample) > 12000:
        text_sample = text_sample[:12000] + "\n……（模板过长已截断）"

    try:
        result = _call_minimax_api_raw(
            system_prompt=_TEMPLATE_STYLE_ANALYZE_SYSTEM,
            user_prompt=f"请分析以下模板文档的写作风格，提炼结构化风格总结：\n\n{text_sample}",
            temperature=0.2,
            max_tokens=1024,
            timeout=(30, 120),
        )
    except Exception:
        return ""
    summary = (result or "").strip()
    if not summary:
        return ""
    summary = _re.sub(r"^```(?:markdown)?\s*\n?", "", summary)
    summary = _re.sub(r"\n?```\s*$", "", summary)
    return summary


# 风格总结懒加载旁路：write_chapter 补齐后写此，after_tools 读出写回 state
_pending_template_style_summary: dict = {}


def pop_pending_template_style_summary() -> str | None:
    """读取并清除懒加载产出的模板风格总结（无则 None）。"""
    return _pending_template_style_summary.pop("summary", None)


# ── 模板分节对位映射 ──

_TEMPLATE_MAP_MAX_BLOCKS_PER_CHAPTER = 2   # 每章参照样例块数上限（防提示词膨胀）
_TEMPLATE_MAP_MAX_CHARS_PER_CHAPTER = 4000  # 每章参照样例字数上限

# 当前模板对位映射（agent_engine._sync_doc_context 从 state 同步）
_current_template_map: contextvars.ContextVar[dict] = contextvars.ContextVar(
    'template_chapter_map', default={}
)
# 映射旁路与进程级缓存（同附件映射模式）
_pending_template_map: dict = {}
_template_map_cache: dict = {}


def set_current_template_map(mapping: dict) -> None:
    """由 agent_engine 在每轮开始前调用，同步当前模板对位映射"""
    _current_template_map.set(mapping or {})


def pop_pending_template_map() -> dict | None:
    """读取并清除待写回 state 的模板对位映射（无新构建时返回 None）。"""
    return _pending_template_map.pop("map", None)


_TEMPLATE_MAP_SYSTEM_PROMPT = """你是文档写法对位专家。给定待生成文档的完整框架和一篇模板文档的内容块清单，
为框架中的每个章节找到模板中「写法最值得参照」的节——结构组织、编号方式、句式、表格用法。
输出严格 JSON（不要代码围栏、不要解释文字）：
{"assignments": [{"block_id": "...", "chapters": ["章节名"], "reason": "≤30字：该节写法为何适配此章"}],
 "chapter_hints": {"章节名": "该章参照模板写法要点≤60字（结构/编号/句式/表格用法）"}}
规则：
- chapters 必须使用框架中出现过的准确章节名（照抄，不要改写）
- 只分配真正具有写法代表性的块（宁缺毋滥）；框架中无合适参照的章节可不分配
- 优先选择结构完整（有标题层级/列表/表格）的块作为写法样例"""


def _tmpl_map_hashes(outline_json: str, templates: list) -> tuple:
    """模板对位映射失效键：(outline 哈希, 模板集合哈希)。"""
    import hashlib
    outline_hash = hashlib.md5((outline_json or "").encode("utf-8")).hexdigest()
    keys = sorted(f"{t.get('template_id', '')}:{t.get('filename', '')}:{len(t.get('full_text', '') or '')}"
                  for t in (templates or []) if t.get("full_text"))
    attachments_hash = hashlib.md5("|".join(keys).encode("utf-8")).hexdigest()
    return outline_hash, attachments_hash


async def _map_templates_to_outline(outline_json: str, templates: list) -> dict:
    """LLM 逐模板通读，构建 章节→模板对应节 的写法对位映射。

    返回 {"outline_hash", "templates_hash", "chapters": {章节名: {"blocks", "hint"}}}。
    """
    from app.services.minimax import _call_minimax_api_raw

    outline_hash, templates_hash = _tmpl_map_hashes(outline_json, templates)
    compact_outline = _outline_compact(outline_json)
    chapters: dict = {}

    for tpl in (templates or []):
        full_text = (tpl.get("full_text") or "").strip()
        if not full_text:
            continue
        tid = tpl.get("template_id", "")
        filename = tpl.get("filename", "unknown")
        blocks = _segment_attachment_blocks(tid, filename, full_text)
        if not blocks:
            continue
        segments, seg, seg_chars = [], [], 0
        for b in blocks:
            if seg and seg_chars + len(b["text"]) > _ATT_MAP_SEGMENT_CHARS:
                segments.append(seg)
                seg, seg_chars = [], 0
            seg.append(b)
            seg_chars += len(b["text"])
        if seg:
            segments.append(seg)

        for seg_blocks in segments:
            blocks_text = "\n".join(
                f"[{b['block_id']}] {'（' + b['section_path'] + '）' if b['section_path'] else ''}\n{b['text']}"
                for b in seg_blocks
            )
            user_prompt = (
                f"## 待生成文档框架\n{compact_outline}\n\n"
                f"## 模板文档：《{filename}》（共{len(blocks)}块，本批{len(seg_blocks)}块）\n{blocks_text}\n\n"
                f"请输出这些块的写法对位分配 JSON。"
            )
            try:
                raw = await asyncio.to_thread(
                    _call_minimax_api_raw,
                    system_prompt=_TEMPLATE_MAP_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.2,
                    max_tokens=4096,
                )
            except Exception:
                continue
            data = _parse_att_map_json(raw or "")
            block_by_id = {b["block_id"]: b for b in seg_blocks}
            for asg in (data.get("assignments") or []):
                if not isinstance(asg, dict):
                    continue
                blk = block_by_id.get(asg.get("block_id", ""))
                if not blk:
                    continue
                for ch_name in (asg.get("chapters") or []):
                    if not isinstance(ch_name, str) or not ch_name.strip():
                        continue
                    entry = chapters.setdefault(ch_name.strip(), {"blocks": [], "hint": ""})
                    entry["blocks"].append({
                        "filename": blk["filename"],
                        "section_path": blk["section_path"],
                        "text": blk["text"],
                        "reason": (asg.get("reason") or "")[:60],
                    })
            for ch_name, hint in (data.get("chapter_hints") or {}).items():
                if isinstance(ch_name, str) and isinstance(hint, str):
                    entry = chapters.setdefault(ch_name.strip(), {"blocks": [], "hint": ""})
                    entry["hint"] = hint[:100]

    for ch_name, entry in chapters.items():
        kept, total = [], 0
        for b in entry["blocks"]:
            if len(kept) >= _TEMPLATE_MAP_MAX_BLOCKS_PER_CHAPTER or total >= _TEMPLATE_MAP_MAX_CHARS_PER_CHAPTER:
                break
            kept.append(b)
            total += len(b["text"])
        entry["blocks"] = kept

    return {
        "outline_hash": outline_hash,
        "templates_hash": templates_hash,
        "chapters": chapters,
    }


async def _get_or_build_template_map(outline_json: str) -> dict:
    """获取当前框架对应的模板对位映射（懒加载 + 哈希失效 + 多级缓存）。"""
    templates = [t for t in (_current_templates.get() or []) if t.get("full_text")]
    if not templates or not (outline_json or "").strip():
        return {}
    outline_hash, templates_hash = _tmpl_map_hashes(outline_json, templates)

    current = _current_template_map.get() or {}
    if (current.get("outline_hash") == outline_hash
            and current.get("templates_hash") == templates_hash):
        return current
    cache_key = f"{outline_hash}:{templates_hash}"
    cached = _template_map_cache.get(cache_key)
    if cached is not None:
        set_current_template_map(cached)
        return cached
    mapping = await _map_templates_to_outline(outline_json, templates)
    if mapping.get("chapters"):
        _template_map_cache[cache_key] = mapping
        if len(_template_map_cache) > 16:
            _template_map_cache.pop(next(iter(_template_map_cache)))
        _pending_template_map["map"] = mapping
        set_current_template_map(mapping)
        print(f"[agent_tools] 模板对位映射已构建: {len(mapping['chapters'])} 章 "
              f"({len(templates)} 个模板已通读)")
    return mapping


def _assigned_template_block(chapter_name: str) -> str:
    """格式化指定章节的模板对应节写法样例（分节对位参照）。

    无映射/无分配返回空串。
    """
    mapping = _current_template_map.get() or {}
    entry = None
    for ch, e in (mapping.get("chapters") or {}).items():
        if _same_chapter(ch, chapter_name):
            entry = e
            break
    if not entry:
        return ""
    blocks = entry.get("blocks") or []
    if not blocks:
        return ""
    lines = []
    hint = (entry.get("hint") or "").strip()
    if hint:
        lines.append(f"[写法要点] {hint}")
    for b in blocks:
        sec = f" | {b['section_path']}" if b.get("section_path") else ""
        reason = f" | {b['reason']}" if b.get("reason") else ""
        lines.append(f"[模板《{b['filename']}》对应节{sec}{reason}]\n{b['text']}")
    return "\n\n".join(lines)


def _templates_hint(templates: list[dict]) -> str:
    """生成可用模板清单（template_id + name），供 not_found 错误提示 LLM 用正确 id 重试"""
    return ", ".join(
        f"{t.get('template_id')} ({t.get('name') or t.get('filename', '?')})" for t in templates
    ) or "（无）"


async def _retrieve_attachment_refs(query: str, top_k: int = 5) -> list:
    """检索用户上传附件中与查询相关的内容（供文档生成注入）。

    调用 search_attachment（关键词 TF + uploads 向量兜底），静默降级返回空列表。
    """
    query = (query or "").strip()
    if not query:
        return []
    try:
        raw = await search_attachment.ainvoke({"query": query, "top_k": top_k})
        data = json.loads(raw)
        if data.get("status") == "ok" and data.get("results"):
            return data["results"][:top_k]
    except Exception:
        pass
    return []


async def _attachment_refs_block(query: str, top_k: int = 5, verb: str = "编写") -> str:
    """把附件检索结果格式化为「最高优先参考资料」注入块。

    附件是用户提供的原始依据（参数/数据/条款/表格），其内容必须优先于
    内置知识库与模型常识采用——这是提升生成内容对附件参考程度的核心注入。
    无相关附件内容时返回空串，不影响原有流程。
    """
    results = await _retrieve_attachment_refs(query, top_k=top_k)
    if not results:
        return ""
    lines = [
        f"\n\n# 用户上传附件参考资料（最高优先级——其中出现的参数、数据、条款、"
        f"表格内容与表述必须优先于知识库和常识采用，供{verb}时参考）:"
    ]
    for j, r in enumerate(results, 1):
        lines.append(
            f"\n[附件{j}] 来源: {r.get('source', '用户上传附件')} "
            f"(相关度:{r.get('score', 0)})\n{r.get('content', '')}"
        )
    return "".join(lines)


def get_pending_chapter_content(chapter_name: str) -> dict:
    """读取并删除 write_chapter 写入的指定章节完整内容"""
    return {"chapter_name": chapter_name, "full_content": _pending_chapter_contents.pop(chapter_name, "")}


# ── 全文字数收敛（build_docx 导出前自动迭代精简到字数上限）──
# 口径与 prompt「总字数约 10000 字」一致：_count_chinese_chars 统计有效字符（去 markdown 标记与空白）。
_DOC_WORD_LIMIT = 10000                # 全文字数预算上限
_DOC_WORD_LIMIT_MAX_ITERATIONS = 3     # 收敛最大迭代轮数（软收敛，超限仍返回最佳结果）

# 字数收敛旁路：build_docx 精简全文后写入精简后的章节 dict + 统计，
# 供 agent_engine._after_tools_node 同步回 generated_sections（review 页与下载一致）。
# 模块级 dict 复用 write_chapter 旁路模式，避免大段内容进入 LLM 对话历史。
_pending_condensed_sections: dict = {}


def pop_pending_condensed_sections() -> dict:
    """读取并清空 build_docx 写入的字数收敛结果。

    Returns:
        {"sections": {章节名: 精简后正文}, "stats": {...}}；无数据时为空 dict。
    """
    data = {
        "sections": _pending_condensed_sections.get("sections", {}),
        "stats": _pending_condensed_sections.get("stats", {}),
    }
    _pending_condensed_sections.clear()
    return data


# 项目计划书类文档类型：不需要在文档中写明具体法规条款（其余文档须带明确条款号）
_PLAN_DOC_TYPES = {"design_development_plan"}


def _regulation_clause_rule(doc_type: str) -> str:
    """法规条款引用规则：项目计划书类文档不写明具体法规/标准条款号，
    其余文档（风险管理、设计输入、产品需求等）须引用明确条款号。"""
    if doc_type in _PLAN_DOC_TYPES:
        return (
            "- 本策划书为项目计划类文档，**不需要写明具体法规/标准条款号**，"
            "聚焦阶段划分、任务分配、资源配置、里程碑与评审点等计划内容\n"
        )
    return "- 所有标准条款引用必须有明确的条款号\n"


# 表格格式强制规则：统一使用 Markdown 管道表格，禁止输出 HTML <table> 标签
_TABLE_FORMAT_RULE = (
    "- 表格必须使用 Markdown 管道表格语法（表头行如 `| 列1 | 列2 |`，"
    "下一行用 `| --- | --- |` 分隔），禁止输出 HTML 的 <table>/<tr>/<td> 标签\n"
)

# 缺失表格补充规则：识别并补全文档中"应有表格却缺失"的位置
_MISSING_TABLE_RULE = (
    "- 识别并补全文档中\"应有表格却缺失\"的位置：当文中出现\"见表X\"、\"如下表所示\"、"
    "\"下表\"、\"以下表格\"、\"参数如下\"、\"技术要求如下\"等表格引用，或内容明显适合用表格"
    "呈现（如参数清单、阶段/资源/时间安排、检验项目、指标对比等）但当前没有表格时，"
    "必须按上下文补全一个合理的 Markdown 管道表格（含表头、分隔行、至少2-3行数据）\n"
)

# 人名与签署栏位规则：具体人名/签名/签署日期一律留空，岗位角色照常写明
# （须显式声明优先级，否则会与"表格要填写完整、不能留占位符"规则冲突）
_NO_PERSON_NAME_RULE = (
    "- **禁止编造或填写任何具体人名**（如张三、李四、王工等）。凡需填写具体人员姓名或"
    "签名的栏位（编制/审核/批准/修订人/会签/签名/审核组成员等），一律输出**空单元格**："
    "Markdown 管道表格中写成 `|  |`，正文中该处直接省略，"
    "不写\"待填写\"、\"XXX\"、下划线或任何占位文字\n"
    "- 与签名配套的**签署日期/生效日期**栏位同样留空，不要填生成当天日期\n"
    "- **岗位与角色必须照常写明**：职责分工中的岗位、角色、部门名称"
    "（如\"配置管理负责人\"、\"项目经理\"、\"质量部\"、\"研发团队\"）不得留空 —— "
    "ISO 13485 要求职责分工明确，留空会伤合规。只留空\"具体人名\"，不留空\"角色\"\n"
    "- 本规则优先级**高于**\"表格要填写完整、不能留占位符\"：表格其它列必须填实，"
    "仅人名与签署日期栏位例外留空\n"
)

# 产品核心前提（用户明确的领域事实，所有文档生成/修改必须遵守）：
# 开环控制（非闭环）、记忆丝驱动（非电机驱动）
_PRODUCT_PREMISE_RULE = (
    "\n"
    "- **产品核心前提（强制，适用于所有内容）**：本产品为**开环控制**（用户手动设定"
    "基础率/大剂量，不集成CGM闭环调节）；输注机构为**记忆丝驱动**（形状记忆合金丝，"
    "非电机/步进电机/微电机驱动）。涉及控制模式、驱动方式、输注机构的任何描述必须"
    "符合此前提；**禁止出现闭环控制、电机驱动、步进电机、微电机、堵转检测等与实际"
    "产品不符的表述**\n"
)


def _output_structure_requirement(doc_type: str, is_revision: bool = False) -> str:
    """输出结构要求：项目计划书类文档不引用法规条款/合规要点，其余文档保持法规导向结构。"""
    # 标题完整性规则（generate_section / revise_section 共用，保证章节与小节标题不缺失）
    title_rule = (
        "5. 标题完整性（强制）：章节与小节标题必须逐级完整——每章以 `## {章节名}` 开头、"
        "每个小节/子小节有自己的 `###`/`####` 标题行；禁止缺失、省略、跳级或把多个小节"
        "合并到同一标题下；修改时原有标题必须逐个保留，不得删标题只留正文"
    )
    if doc_type in _PLAN_DOC_TYPES:
        return (
            "## 输出结构要求\n"
            "请按以下结构组织内容:\n"
            "1. 首先用1-2段概述本节要点（聚焦计划目的、范围与产品适用性）\n"
            "2. 然后逐个详细阐述每个关键计划要素（阶段划分/任务分配/资源/时间安排/职责等），每个要素至少200字\n"
            "3. 如涉及阶段、资源、时间安排对比，以表格形式呈现（至少3列）\n"
            "4. 最后用1段总结本节的计划要点和与贴敷式胰岛素泵的关联性\n"
            + title_rule
        )
    verb = "修改后的" if is_revision else ""
    return (
        f"## 输出结构要求\n"
        f"请按以下结构组织{verb}内容:\n"
        f"1. 首先用1-2段概述本节要点（含法规依据和产品适用性）\n"
        f"2. 然后逐个详细阐述每个关键要求（每个要求至少200字，包含法规条款原文引用、产品参数映射、实施建议）\n"
        f"3. 如涉及数据/参数对比，以表格形式呈现（至少3列）\n"
        f"4. 最后用1段总结本节的合规要点和与贴敷式胰岛素泵的关联性\n"
        + title_rule
    )


def _supplementary_block() -> str:
    """返回累积的用户补充提示词块，追加到各文档生成工具 system_prompt 末尾。

    纯附加（appended）——只在原有提示词之后追加，不修改、不覆盖原有提示词。
    无补充提示词时返回空字符串，不影响原有提示词结构。
    """
    prompts = _current_supplementary_prompts.get()
    if not prompts or not prompts.strip():
        return ""
    return (
        f"\n\n"
        f"## 补充提示词（用户额外要求，必须遵守，且优先于上述默认规则）\n"
        f"{prompts.strip()}\n"
    )


def _memory_context_block() -> str:
    """返回召回记忆参考块，追加到文档生成工具 system_prompt 末尾。

    记忆由 ov_recall/ltm_recall 按当前用户消息检索（跨会话/跨轮的用户偏好、
    项目背景、历史决策），作为生成的主要依据之一（尤其用户偏好与项目背景应落实到
    文档）；与附件原文冲突时以附件为准。无记忆时返回空字符串。
    """
    memory = (_current_memory_context.get() or "").strip()
    if not memory:
        return ""
    # 截断，避免记忆块过大挤占生成 prompt 预算
    if len(memory) > 3000:
        memory = memory[:3000]
    return (
        f"\n\n"
        f"## 历史记忆参考（主要生成依据之一）\n"
        f"以下是从历史会话中检索到的相关记忆（用户偏好、项目背景、既往决策等），"
        f"其中的用户偏好与项目背景应落实到文档内容；与用户上传附件原文冲突时以附件为准，"
        f"与法规标准冲突时以法规为准：\n"
        f"{memory}\n"
    )


def _doc_scope_rule(doc_type: str) -> str:
    """文档范围规则：软件类文档只写软件内容，不写硬件内容（反之亦然）。

    依据 doc_type 前缀判定软件/硬件类文档；非软件类不注入（零影响）。
    """
    dt = (doc_type or "").strip()
    if not dt.startswith("software_"):
        return ""
    return (
        "\n## 文档范围（强制）\n"
        "- 本文档为**软件类文档**：只写与软件开发相关的内容（软件需求/架构/设计/"
        "编码/测试/配置管理/版本等）\n"
        "- **禁止写入硬件相关内容**：不得描述电路、电机/驱动机构、传感器选型、"
        "结构尺寸、材料、外壳、电池等硬件设计与实现；硬件信息仅在作为软件运行"
        "环境或接口前提时用一句话带过（如\"运行于 XX MCU 平台\"），不得展开\n"
        "- 涉及软硬件接口时，只从软件视角描述接口逻辑与数据协议，不展开硬件实现\n"
    )


def _grounding_rule() -> str:
    """有据生成规则（防编造）：生成内容必须以参考材料为主要依据。

    参考材料优先级：用户上传附件 > 召回记忆 > 知识库/网络检索。
    未覆盖内容用通用行业表述，禁止给出无法核实的具体细节。
    """
    return (
        "\n## 有据生成规则（强制——尽量减少编造内容）\n"
        "- 事实性内容（参数、数值、法规条款、技术指标、流程、结论）必须优先取自本次"
        "提示词中提供的参考材料，优先级：**用户上传附件（分配块/检索块）> 召回的记忆"
        "（用户偏好/项目背景/历史决策）> 知识库与网络检索结果**；参考材料之间冲突时"
        "按此优先级取舍\n"
        "- 各参考材料均未覆盖的内容：使用通用、行业公认的表述撰写，**避免给出具体数值、"
        "条款号、型号、测试结果等无法核实的细节**\n"
        "- 确需具体值而所有参考材料均未提供时：不要编造，采用通用表述或标注该值为"
        "建议值（需结合产品实际确认）\n"
        "- **禁止编造**任何无参考材料支撑的具体数据、标准条款引用、实验/测试结果、"
        "供应商或产品型号\n"
    )


def _attachment_priority_rule() -> str:
    """附件优先规则（条件注入：仅当用户已上传附件时），防幻觉核心约束。

    附件内容是最高优先事实来源：参数/数值/条款/产品事实凡附件中有必须一致采用；
    附件未覆盖的才可用知识库/网络/专业常识，且不得与附件冲突。无附件返回空串。
    """
    attachments = [a for a in (_current_attachments.get() or []) if a.get("full_text")]
    if not attachments:
        return ""
    names = "、".join((a.get("filename") or "?") for a in attachments[:5])
    return (
        "\n## 附件优先规则（强制——用户已上传附件：" + names + "）\n"
        "- 附件内容是本次生成/修改的**最高优先事实来源**：所有参数、数值、条款、"
        "产品事实与事实性描述，凡附件中有的，必须与附件一致并优先采用\n"
        "- 提示词中标注「附件分配内容」「[附件·最高优先]」「用户上传附件参考资料」"
        "的内容均来自附件原文，必须作为事实依据\n"
        "- 附件未覆盖的内容方可使用知识库/网络检索结果或专业常识，且**不得与附件"
        "已有内容冲突**；冲突时一律以附件为准\n"
        "- **禁止编造附件中没有且无其他依据的数据、参数或事实**\n"
    )


def _same_chapter(a: str, b: str) -> bool:
    """宽松的章节名相等判断（容忍"2 目的和范围"vs"目的和范围"这类差异）"""
    a = (a or "").replace(" ", "")
    b = (b or "").replace(" ", "")
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _build_covered_digest(exclude_chapter: str) -> str:
    """从已生成文档（_current_generated_markdown，`# 章节\n\n内容` 拼接格式）
    提取除 exclude_chapter 之外各章节的"已覆盖内容"摘要，返回 Markdown 文本。

    摘要包含：已写章节标题 + 各小节标题 + 每小节首条要点（截断80字）。
    注入 write_chapter / generate_section 提示词，让模型避免跨章节重复相同内容。
    文档为空或无可排除章节时返回空串。
    """
    md = _current_generated_markdown.get()
    if not md or not md.strip():
        return ""

    # (chapter_title, [(section_heading, first_point)]) 列表
    digest: list = []
    cur_chapter = None
    cur_section = None
    cur_first = None
    section_points: list = []

    def _flush_section():
        nonlocal cur_section, cur_first
        if cur_section is not None:
            section_points.append((cur_section, (cur_first or "")[:80]))
            cur_section = None
            cur_first = None

    for line in md.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("# "):
            _flush_section()
            if cur_chapter is not None and not _same_chapter(cur_chapter, exclude_chapter):
                digest.append((cur_chapter, section_points))
            cur_chapter = s[2:].strip()
            section_points = []
        elif s.startswith("##### ") or s.startswith("#### ") \
                or s.startswith("### ") or s.startswith("## "):
            _flush_section()
            cur_section = s.lstrip("#").strip()
        else:
            if cur_section is not None and cur_first is None:
                cur_first = s
    _flush_section()
    if cur_chapter is not None and not _same_chapter(cur_chapter, exclude_chapter):
        digest.append((cur_chapter, section_points))

    if not digest:
        return ""

    parts = ["已覆盖内容（请勿重复以下章节内容，如需引用用\"详见第X章\"简述）:"]
    for ch, points in digest:
        parts.append(f"- {ch}")
        for sec, first in points:
            if first:
                parts.append(f"  - {sec}：{first}")
            else:
                parts.append(f"  - {sec}")
    return "\n".join(parts)


def _build_style_reference(exclude_chapter: str, max_chars: int = 2600) -> str:
    """从已生成文档全文（_current_generated_markdown，`# 章节\n\n内容` 拼接格式）
    提取「整体风格参照」，供修改/补全工具让输出与全文既有风格保持一致。

    提取三部分：
    1. 结构概览：全部章/节/小节标题树（轻量，让模型感知全文结构）；
    2. 相邻章节节选：目标章节前后各一章的开头片段（保持上下文衔接）；
    3. 文风范本：从其余各章抽取代表性段落开头（句式/详略/术语/列表习惯），
       总预算控制在 max_chars 以内。
    文档为空、或除目标章节外无其他内容时返回空串。
    """
    md = _current_generated_markdown.get()
    if not md or not md.strip():
        return ""

    # 解析为 [(chapter_title, [body_lines])] 列表，按 `# ` 划分章节
    chapters: list = []
    cur_title = None
    cur_lines: list = []
    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("# "):
            if cur_title is not None:
                chapters.append((cur_title, cur_lines))
            cur_title = s[2:].strip()
            cur_lines = []
        elif cur_title is not None:
            cur_lines.append(line)
    if cur_title is not None:
        chapters.append((cur_title, cur_lines))

    # 其余章节（排除目标章节）
    other = [(t, ls) for (t, ls) in chapters if not _same_chapter(t, exclude_chapter)]

    # 相邻章节（在原文顺序中与目标章节相邻，用于上下文衔接）
    adj: list = []
    for i, (t, _ls) in enumerate(chapters):
        if _same_chapter(t, exclude_chapter):
            if i > 0:
                adj.append(("上文相邻章节", chapters[i - 1]))
            if i < len(chapters) - 1:
                adj.append(("下文相邻章节", chapters[i + 1]))
            break

    if not other and not adj:
        return ""

    # 1. 结构概览：标题树（仅标题行，不展开正文）
    tree_lines: list = []
    for t, ls in other:
        tree_lines.append(f"- {t}")
        for l in ls:
            s = l.strip()
            if s.startswith("#"):
                depth = len(s) - len(s.lstrip("#"))
                tree_lines.append(f"  {'  ' * max(depth - 2, 0)}{s}")
    structure = "\n".join(tree_lines)

    # 2. 相邻章节节选：每章正文开头片段
    adj_lines: list = []
    for label, (t, ls) in adj:
        body = " ".join(x.strip() for x in ls if x.strip() and not x.strip().startswith("#"))
        excerpt = body[:300]
        if excerpt:
            adj_lines.append(f"【{label}：{t}】{excerpt}")
    adj_text = "\n".join(adj_lines) if adj_lines else ""

    # 3. 文风范本：从其余各章抽取代表性段落开头，预算控制
    samples: list = []
    budget = max_chars
    for t, ls in other:
        if budget <= 0:
            break
        chunks: list = []
        for l in ls:
            s = l.strip()
            if not s or s.startswith("#"):
                continue
            chunks.append(s)
            if sum(len(c) for c in chunks) >= 220:
                break
        if chunks:
            text = " ".join(chunks)[:280]
            samples.append(f"【{t}】{text}")
            budget -= len(text) + 24
    style_samples = "\n".join(samples) if samples else ""

    parts = ["## 全文整体风格参照（修改/新增内容需与全文既有风格保持一致）"]
    if structure:
        parts.append("### 全文结构概览（章节/小节标题树）\n" + structure)
    if adj_text:
        parts.append("### 相邻章节节选（保持上下文衔接）\n" + adj_text)
    if style_samples:
        parts.append("### 文风范本（模仿其句式长短、详略程度、术语表达、列表与表格使用习惯）\n" + style_samples)
    return "\n\n".join(parts)


# ── Tool 1: search_kb ──

# search_kb 网络搜索自动升级的放宽阈值（本地结果不足时联网补充）：
# 本地无结果 / 结果少于 N 条 / 最高相关度低于 S 时触发；env 可调
_WEB_FALLBACK_MIN_RESULTS = int(os.getenv("WEB_FALLBACK_MIN_RESULTS", "3"))
_WEB_FALLBACK_MIN_SCORE = float(os.getenv("WEB_FALLBACK_MIN_SCORE", "0.5"))


@tool
async def search_kb(query: str, top_k: int = 15, use_rerank: bool = True) -> str:
    """检索贴敷式胰岛素泵知识库 (标准、法规、技术文档、测试报告等)。

    同时检索两个 collection 并合并结果:
      1. 主知识库 (insulin_pump_kb) — 标准、法规、技术参考文档
      2. 用户上传附件库 (uploads) — 当前项目用户上传的参考文件

    当需要查找具体标准条款、技术参数限值、法规要求、同类产品数据时，必须先调用此工具。
    不要在未检索的情况下编造标准条款号和具体限值。

    Args:
        query: 搜索查询关键词。应为具体的标准号、参数名或技术问题。
        top_k: 返回结果数量，默认15条。
        use_rerank: 是否启用Cross-Encoder精排（默认开启，提升精确率）。
                    两阶段检索：粗召回40条→BGE-Reranker精排→Top-K。
                    注：精排仅作用于主知识库；uploads 集合较小，直接向量检索即可。

    Returns:
        JSON格式的检索结果列表，每项包含 content, source, source_collection, score。
        source_collection 标识结果来源: "insulin_pump_kb" 或 "uploads"。
    """
    try:
        from app.services.rag.vector_store import VectorStore

        def _do_retrieve_main():
            """检索主知识库 (insulin_pump_kb)，可走 Reranker 精排"""
            store = VectorStore()
            if use_rerank:
                return store.retrieve_and_rerank(
                    query=query,
                    top_k=top_k,
                    candidate_pool_size=50,
                    vector_weight=0.85,
                )
            else:
                return store.retrieve_hybrid(
                    query=query,
                    top_k=top_k,
                    vector_weight=0.85,
                )

        def _do_retrieve_uploads():
            """直接检索 uploads collection (用户上传附件库)。

            uploads 已纳入 QUERY_COLLECTIONS，主库检索会一并命中 uploads。
            本方法仍独立检索一次，用于控制 uploads 配额 (uploads_n) 并打上
            [附件] 来源标注；主库结果中的 uploads chunk 会在后续被剔除，避免重复。
            直接走 self.collection.query 即可，无需 Reranker 或 BM25 二次召回。
            """
            try:
                store = VectorStore(collection_name="uploads")
                try:
                    count = store.collection.count()
                except Exception:
                    return []
                if count == 0:
                    return []
                query_embedding = store.embedder.encode_single(query)
                # uploads 集合独立检索，给予与主库同等的配额
                uploads_n = max(top_k, 5)
                raw = store.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=uploads_n,
                    include=["documents", "metadatas", "distances"],
                )
                if not raw or not raw.get("ids") or not raw["ids"][0]:
                    return []
                results = []
                for i in range(len(raw["ids"][0])):
                    distance = raw["distances"][0][i]
                    similarity = max(0.0, 1.0 - distance / 2.0)
                    meta = raw["metadatas"][0][i] or {}
                    results.append({
                        "text": raw["documents"][0][i],
                        "source_file": meta.get("source_file", "用户上传附件"),
                        "section_title": meta.get("section_title", ""),
                        "doc_type": meta.get("doc_type", ""),
                        "chunk_index": meta.get("chunk_index", 0),
                        "similarity": similarity,
                        "distance": distance,
                        "chunk_id": raw["ids"][0][i],
                    })
                return results
            except Exception as e:
                print(f"[search_kb] uploads 检索异常: {e}")
                return []

        # 并行执行两个检索 (主库可能耗时较长，uploads 几秒内完成)
        timeout_sec = 120.0 if use_rerank else 90.0
        try:
            main_results, upload_results = await asyncio.wait_for(
                asyncio.gather(
                    asyncio.to_thread(_do_retrieve_main),
                    asyncio.to_thread(_do_retrieve_uploads),
                    return_exceptions=True,
                ),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            return json.dumps({
                "status": "timeout",
                "message": f"知识库检索超时（{int(timeout_sec)}秒）。请尝试缩小查询范围或稍后重试。",
                "results": [],
            }, ensure_ascii=False)

        # 归一化主库结果
        if isinstance(main_results, Exception):
            print(f"[search_kb] 主库检索异常: {main_results}")
            main_results = []
        main_results = main_results or []
        # uploads 已通过 _do_retrieve_uploads 单独检索（含配额与[附件]标注），
        # 剔除主库结果中的 uploads 来源 chunk，避免同一内容重复进入 Agent 上下文
        main_results = [
            r for r in main_results
            if r.get("source_collection") != "qms_doc_uploads"
        ]
        for r in main_results:
            r.setdefault("source_collection", "insulin_pump_kb")

        # 归一化 uploads 结果
        if isinstance(upload_results, Exception):
            print(f"[search_kb] uploads 检索异常: {upload_results}")
            upload_results = []
        upload_results = upload_results or []
        for r in upload_results:
            r["source_collection"] = "uploads"

        all_results = list(main_results) + list(upload_results)

        # ── 网络搜索自动升级（放宽触发：系统级兜底，不依赖 LLM 二次判断）──
        # 触发条件任一满足即联网：①本地无结果 ②结果少于 WEB_FALLBACK_MIN_RESULTS 条
        # ③最高相关度低于 WEB_FALLBACK_MIN_SCORE（本地有少量低相关结果时网络结果作补充）
        def _need_web_fallback(results: list) -> bool:
            if not results:
                return True
            if len(results) < _WEB_FALLBACK_MIN_RESULTS:
                return True
            top = max((float(r.get("rerank_score") or r.get("similarity") or 0.0)
                       for r in results), default=0.0)
            return top < _WEB_FALLBACK_MIN_SCORE

        web_supplement = None  # 格式化后的网络补充结果（None=未触发或联网失败）
        if _need_web_fallback(all_results):
            try:
                web_json = await web_search.ainvoke({
                    "query": query,
                    "doc_type": _current_doc_type.get(),
                })
                parsed = json.loads(web_json)
                if parsed.get("status") == "ok" and parsed.get("content"):
                    web_supplement = {
                        "content": parsed["content"],
                        "source": f"[网络] {parsed.get('search_method', 'web')}",
                        "source_collection": "web",
                        "score": 0.0,
                    }
                    print(f"[search_kb] 触发 web_search 升级 "
                          f"(local={len(all_results)}, web={len(parsed['content'])} chars)")
            except Exception as e:
                print(f"[search_kb] web 自动升级失败: {e}")

        if not all_results:
            # 本地为空 → 网络结果独立返回（原行为）
            web_results = [web_supplement] if web_supplement else []
            return json.dumps({
                "status": "ok" if web_results else "no_results",
                "query": query,
                "count": len(web_results),
                "reranked": use_rerank,
                "uploads_included": False,
                "web_fallback": True,
                "results": web_results,
            }, ensure_ascii=False)

        # 按分数排序 (精排分数优先，回退到相似度)
        def _get_score(r):
            rs = r.get("rerank_score")
            if rs is not None:
                return rs
            return r.get("similarity", 0.0)
        all_results.sort(key=_get_score, reverse=True)

        # 去重 (按 text 前 100 字)。
        # 统一按文本去重: 主库结果无 chunk_id，uploads 结果有 chunk_id，
        # 若按 chunk_id 去重会漏掉两路检索返回的同一段内容 (含 BM25-only 命中)，
        # 统一用文本前缀可确保跨路径重复被剔除。
        seen = set()
        unique = []
        for r in all_results:
            key = (r.get("text") or "")[:100]
            if key in seen:
                continue
            seen.add(key)
            unique.append(r)
            if len(unique) >= top_k * 2:
                break

        # 格式化输出
        formatted = []
        for r in unique:
            score = _get_score(r)
            source = r.get("source_file", "未知来源")
            if r.get("source_collection") == "uploads":
                source = f"[附件] {source}"
            formatted.append({
                "content": r.get("text", ""),
                "source": source,
                "source_collection": r.get("source_collection", "unknown"),
                "score": round(score, 3),
            })

        # 本地结果不足时补充的网络结果：置于列表最前（网络字段结构与本地不同，
        # 不进上面的排序/去重流程，避免被丢弃）
        if web_supplement is not None:
            formatted.insert(0, web_supplement)

        return json.dumps({
            "status": "ok",
            "query": query,
            "count": len(formatted),
            "reranked": use_rerank,
            "uploads_included": len(upload_results) > 0,
            "web_fallback": web_supplement is not None,
            "results": formatted,
        }, ensure_ascii=False)

    except ImportError:
        return json.dumps({
            "status": "unavailable",
            "message": "知识库服务暂时不可用。请用已有知识回答，并告知用户当前无法检索知识库。",
            "results": [],
        }, ensure_ascii=False)
    except asyncio.TimeoutError:
        return json.dumps({
            "status": "timeout",
            "message": f"知识库检索超时（90秒）。请尝试缩小查询范围或稍后重试。",
            "results": [],
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"知识库检索异常: {str(e)}。请告知用户当前检索遇到问题，可用已有知识先回答。",
            "results": [],
        }, ensure_ascii=False)


# ── Tool 1a: generate_search_query ──

async def _generate_search_queries(
    chapter_name: str,
    sub_title: str = "",
    content_points: list = None,
    intent: str = "",
    num_queries: int = 3,
) -> list[str]:
    """
    内部函数：调用 LLM 基于产品上下文+章节信息生成针对性检索查询词。

    供 generate_search_query 工具和 write_chapter/generate_section/design_outline 内部复用。

    Args:
        chapter_name: 章节名（如"设计开发阶段划分"）
        sub_title: 小节名（可选，逐小节检索时传入）
        content_points: 内容要点列表（可选）
        intent: Agent 描述的查询意图（可选，如"查找IEC 62304软件C级测试要求"）
        num_queries: 生成的查询词数量

    Returns:
        查询词列表，如 ["IEC 62304 Class C 软件单元测试要求", ...]
    """
    from app.services.minimax import _call_minimax_api_raw

    # 收集产品上下文
    product_name = _current_product_name.get() or "贴敷式胰岛素泵"
    product_class = _current_product_classification.get()
    intended_use = _current_product_intended_use.get()
    standards = _current_confirmed_standards.get()
    doc_type = _current_doc_type.get()

    context_lines = [f"- 产品名称: {product_name}"]
    if product_class:
        context_lines.append(f"- 分类: {product_class}")
    if intended_use:
        context_lines.append(f"- 预期用途: {intended_use}")
    if standards:
        context_lines.append(f"- 已确认适用标准: {', '.join(standards[:10])}")
    if doc_type:
        context_lines.append(f"- 目标文档类型: {doc_type}")
    context_block = "\n".join(context_lines)

    target = chapter_name
    if sub_title:
        target = f"{chapter_name} → {sub_title}"

    points_hint = ""
    if content_points:
        points_hint = "\n本节内容要点:\n" + "\n".join(f"- {p}" for p in content_points[:5])

    intent_hint = ""
    if intent:
        intent_hint = f"\nAgent查询意图: {intent}"

    system_prompt = f"""你是医疗器械法规标准检索专家。基于以下产品上下文和章节信息，生成 {num_queries} 条精准的知识库检索查询词。

## 产品上下文
{context_block}

## 当前检索目标
章节: {target}{points_hint}{intent_hint}

## 任务
生成 {num_queries} 条检索查询词，每条查询词应：
1. 包含具体的标准号、参数名、技术术语或法规条款号（不要泛泛而谈）
2. 与产品上下文紧密结合（如软件C级、贴敷式胰岛素泵、开环控制等）
3. 覆盖不同检索维度（如：标准要求类、测试方法类、限值参数类）

## 输出格式（严格JSON）
{{
  "queries": ["查询词1", "查询词2", "查询词3"]
}}

只输出JSON，不要包含其他文字或markdown代码块标记。"""

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                _call_minimax_api_raw,
                system_prompt=system_prompt,
                user_prompt=f"请生成 {num_queries} 条针对「{target}」的检索查询词。",
                temperature=0.2,
                max_tokens=1024,
            ),
            timeout=60.0,
        )
        if not response:
            return []

        # 提取JSON
        import re
        json_text = response.strip()
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', json_text)
        if match:
            json_text = match.group(1).strip()
        else:
            match = re.search(r'\{[\s\S]*\}', json_text)
            if match:
                json_text = match.group(0).strip()

        parsed = json.loads(json_text)
        queries = parsed.get("queries", [])
        return [str(q).strip() for q in queries if str(q).strip()][:num_queries]
    except Exception as e:
        print(f"[generate_search_query] LLM生成查询失败: {e}")
        # 回退到简单拼接
        fallback = " ".join(filter(None, [doc_type, chapter_name, sub_title]))
        if content_points:
            fallback += " " + " ".join(content_points[:3])
        return [fallback] if fallback else []


@tool
async def generate_search_query(
    chapter_name: str,
    intent: str = "",
    num_queries: int = 3,
) -> str:
    """基于当前产品上下文和章节信息，生成精准的知识库检索查询词。

    调用此工具后，会返回 2-4 条针对性查询词，每条覆盖不同检索维度
    （标准要求/测试方法/限值参数）。然后用这些查询词分别调用 search_kb 检索。

    何时调用:
    - 开始生成新章节前（替代凭直觉拼凑查询词）
    - 需要查找具体标准条款但不确定用什么关键词时
    - 用户描述模糊的查询意图时（如"查一下软件测试要求"）

    Args:
        chapter_name: 章节名或主题，如"设计开发阶段划分"、"软件验证"
        intent: 查询意图描述（可选），如"查找IEC 62304 C级软件单元测试的具体要求和通过准则"
        num_queries: 生成的查询词数量，默认3条

    Returns:
        JSON格式的查询词列表，供后续 search_kb 使用。
    """
    queries = await _generate_search_queries(
        chapter_name=chapter_name,
        intent=intent,
        num_queries=num_queries,
    )

    if not queries:
        return json.dumps({
            "status": "error",
            "message": "查询词生成失败，请直接用章节名或标准号调用 search_kb。",
            "queries": [],
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "chapter_name": chapter_name,
        "intent": intent,
        "queries": queries,
        "usage_hint": "请用上述每条查询词分别调用 search_kb，合并结果后取最相关的作为生成参考。",
    }, ensure_ascii=False)


# ── Tool 1b: search_attachment ──
# 附件段落级精准检索：jieba 分词关键词 + 附件块向量（qwen3-embedding 懒加载缓存）
# 混合召回 → bge-reranker-v2-m3 精排 → 结果带位置信息（section_path/块号）。
# 支持 filename 参数限定单个附件（用户选中某文档提问时精确定位）。

_QUERY_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "及", "其", "对", "于", "中", "上", "下",
    "有", "什么", "哪些", "哪个", "请问", "如何", "怎么", "怎样", "为什么", "这个", "那个",
    "可以", "需要", "应该", "我们", "你们", "他们", "进行", "通过", "使用", "以及", "还有",
    "一个", "一下", "告诉", "帮我", "查找", "查询", "搜索", "内容", "信息", "相关", "关于",
    "请", "吗", "呢", "吧", "啊", "文档", "附件", "文件",
}


def _tokenize_query(query: str) -> list:
    """jieba 分词 + 停用词过滤（中文关键词检索的基础，替代空格分词）。"""
    try:
        import jieba
        words = [w.strip() for w in jieba.lcut(query or "")]
    except Exception:
        words = (query or "").split()
    out, seen = [], set()
    for w in words:
        if not w or w in _QUERY_STOPWORDS:
            continue
        # 单字仅保留字母/数字（如 U、5、C），过滤无信息量单字
        if len(w) == 1 and not w.isalnum():
            continue
        k = w.lower()
        if k not in seen:
            seen.add(k)
            out.append(w)
    return out


def _kw_block_score(text: str, terms: list, full_query: str) -> float:
    """块级关键词打分：词覆盖率为主 + 命中密度轻加成 + 完整短语命中加分。"""
    if not text or not terms:
        return 0.0
    t = text.lower()
    hits = [w for w in terms if w.lower() in t]
    if not hits:
        return 0.0
    coverage = len(hits) / len(terms)
    density = sum(t.count(w.lower()) for w in hits) / max(len(t) / 100.0, 1.0)
    score = min(coverage * 0.8 + min(density, 0.4) * 0.5, 1.0)
    if full_query and full_query.strip().lower() in t:
        score = min(score + 0.3, 1.0)  # 完整查询短语命中加分
    return round(score, 3)


# 附件块切分缓存（file_id → blocks，char_count 变化时失效）
_attachment_blocks_cache: dict = {}


def _get_attachment_blocks(att: dict) -> list:
    fid = att.get("file_id", "") or att.get("filename", "")
    cc = att.get("char_count", 0) or len(att.get("full_text", "") or "")
    cached = _attachment_blocks_cache.get(fid)
    if cached and cached.get("char_count") == cc:
        return cached["blocks"]
    blocks = _segment_attachment_blocks(fid, att.get("filename", "unknown"),
                                        att.get("full_text", ""))
    _attachment_blocks_cache[fid] = {"char_count": cc, "blocks": blocks}
    if len(_attachment_blocks_cache) > 32:
        _attachment_blocks_cache.pop(next(iter(_attachment_blocks_cache)))
    return blocks


# 附件块向量缓存（懒加载；embedding 不可用时静默降级为纯关键词）
_attachment_vec_cache: dict = {}
_ollama_embeddings = None


def _get_ollama_embeddings():
    global _ollama_embeddings
    if _ollama_embeddings is None:
        from langchain_openai import OpenAIEmbeddings
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435").rstrip("/") + "/v1"
        _ollama_embeddings = OpenAIEmbeddings(
            model=os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:4b"),
            base_url=base_url,
            api_key=os.getenv("MINIMAX_API_KEY", "ollama"),
            # Ollama OpenAI 兼容端点只接受原始文本，关闭 tiktoken 长度检查
            check_embedding_ctx_length=False,
        )
    return _ollama_embeddings


def _cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def _get_block_vectors(att: dict, blocks: list):
    """获取附件块向量（缓存；首次调用 embed 全文块，失败返回 None 降级关键词路）。"""
    fid = att.get("file_id", "") or att.get("filename", "")
    cc = att.get("char_count", 0) or len(att.get("full_text", "") or "")
    cached = _attachment_vec_cache.get(fid)
    if cached and cached.get("char_count") == cc and len(cached.get("vectors", [])) == len(blocks):
        return cached["vectors"]
    try:
        emb = _get_ollama_embeddings()
        texts = [b["text"][:1500] for b in blocks]
        vectors = await asyncio.wait_for(
            asyncio.to_thread(emb.embed_documents, texts), timeout=300.0)
        _attachment_vec_cache[fid] = {"char_count": cc, "vectors": vectors}
        if len(_attachment_vec_cache) > 8:
            _attachment_vec_cache.pop(next(iter(_attachment_vec_cache)))
        print(f"[search_attachment] 附件向量化完成: {att.get('filename')} ({len(vectors)} 块)")
        return vectors
    except Exception as e:
        print(f"[search_attachment] 附件向量化失败（降级关键词检索）: {e}")
        return None


async def _search_attachment_core(query: str, top_k: int = 10, filename: str = "") -> list:
    """附件段落级混合检索核心：关键词（jieba）+ 向量 混合召回 → 精排 → 带位置信息。

    Returns:
        [{"content", "source", "score", "rerank_score", "section_path", "block_id", "match"}]
        按相关度降序；无结果返回空列表。
    """
    attachments = [a for a in (_current_attachments.get() or []) if a.get("full_text")]
    if filename:
        fl = filename.strip().lower()
        attachments = [a for a in attachments
                       if fl in (a.get("filename") or "").lower()]
    if not attachments or not (query or "").strip():
        return []

    terms = _tokenize_query(query)
    candidates = {}  # block_id -> item

    for att in attachments:
        blocks = _get_attachment_blocks(att)
        if not blocks:
            continue
        fname = att.get("filename", "unknown")

        # 关键词路
        if terms:
            for b in blocks:
                s = _kw_block_score(b["text"], terms, query)
                if s > 0:
                    candidates[b["block_id"]] = {
                        "content": b["text"], "source": fname, "score": s,
                        "section_path": b.get("section_path", ""),
                        "block_id": b["block_id"], "match": "kw",
                    }

        # 向量路（懒加载 embedding，失败静默跳过）
        vectors = await _get_block_vectors(att, blocks)
        if vectors:
            try:
                emb = _get_ollama_embeddings()
                qv = await asyncio.wait_for(
                    asyncio.to_thread(emb.embed_query, query), timeout=60.0)
                for b, v in zip(blocks, vectors):
                    cs = _cosine(qv, v)
                    if cs < 0.35:
                        continue
                    key = b["block_id"]
                    if key in candidates:
                        candidates[key]["score"] = round(max(candidates[key]["score"], cs), 3)
                        candidates[key]["match"] = "kw+vec"
                    else:
                        candidates[key] = {
                            "content": b["text"], "source": fname, "score": round(cs, 3),
                            "section_path": b.get("section_path", ""),
                            "block_id": key, "match": "vec",
                        }
            except Exception as e:
                print(f"[search_attachment] 查询向量化失败（仅关键词结果）: {e}")

    if not candidates:
        return []

    merged = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)[:20]

    # Cross-Encoder 精排（bge-reranker-v2-m3；失败时保留混合分数排序）
    try:
        from app.services.rag.reranker import Reranker
        for m in merged:
            m["text"] = m["content"]
        ranked = await asyncio.wait_for(
            asyncio.to_thread(Reranker().rerank, query, merged, top_k), timeout=120.0)
        for r in ranked:
            r.pop("text", None)
        return ranked
    except Exception as e:
        print(f"[search_attachment] 精排失败（用混合分数）: {e}")
        return merged[:top_k]


@tool
async def search_attachment(query: str, top_k: int = 10, filename: str = "") -> str:
    """搜索用户上传的附件内容（段落级精准定位）。当需要查找用户上传文件中的具体信息时使用此工具。

    适用场景: 用户上传了PDF/Word/Excel等参考文档，需要从中提取特定信息、
    回答关于某个文档具体段落/章节的问题。
    与 search_kb 的区别: search_kb 搜索预置知识库（标准法规），search_attachment 搜索用户上传文件。

    Args:
        query: 搜索查询。包含具体术语/参数名/章节关键词（如"输注精度 要求"），
               不要只写完整问句——术语词命中率更高。
        top_k: 返回结果数量，默认10条。
        filename: 可选，限定只搜索某个附件（文件名关键词即可，如"技术要求"）。
                  用户明确针对某一文档提问时传入，定位更准。

    Returns:
        JSON格式的搜索结果，每项包含 content（段落原文）、source（文件名）、
        section_path（所在章节路径）、block_id（块号）、score/rerank_score（相关度）。
        回答用户时应引用 section_path 位置信息，便于用户核对原文。
    """
    try:
        results = await _search_attachment_core(query, top_k=top_k, filename=filename)
        if results:
            return json.dumps({
                "status": "ok",
                "query": query,
                "count": len(results),
                "source": "hybrid_kw_vec_rerank",
                "results": results,
            }, ensure_ascii=False)

        # 兜底：附件已入库 uploads 集合时走向量库（附件未入库/向量不可用均可能走到）
        try:
            from app.services.rag.vector_store import VectorStore
            store = VectorStore(collection_name="uploads")
            if store.collection.count() > 0:
                query_embedding = store.embedder.encode_single(query)
                raw = store.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                )
                formatted = []
                if raw and raw.get("ids") and raw["ids"][0]:
                    for i in range(len(raw["ids"][0])):
                        distance = raw["distances"][0][i]
                        similarity = max(0.0, 1.0 - distance / 2.0)
                        meta = raw["metadatas"][0][i] or {}
                        formatted.append({
                            "content": raw["documents"][0][i],
                            "source": meta.get("source_file", "用户上传附件"),
                            "score": round(similarity, 3),
                        })
                if formatted:
                    return json.dumps({
                        "status": "ok",
                        "query": query,
                        "count": len(formatted),
                        "source": "vector_search",
                        "results": formatted,
                    }, ensure_ascii=False)
        except Exception:
            pass

        return json.dumps({
            "status": "no_match",
            "message": f'在附件中未找到与"{query}"直接相关的内容。请尝试更换术语关键词，或告知用户当前附件中未包含此信息。',
            "results": [],
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"附件检索异常: {str(e)}",
            "results": [],
        }, ensure_ascii=False)


# ── Tool: search_template ──

@tool
async def search_template(query: str, top_k: int = 5) -> str:
    """搜索用户添加的模板文档内容（模板是通过「添加模板」登记的结构/风格参照文档）。

    与 search_attachment 的区别:
    - search_attachment 搜索普通上传附件
    - search_template 搜索用户登记的模板文档（含章节结构目录、内容预览）

    适用场景: 用户提到某个模板（如"参照KF-GS1模板的章节结构"）并需要查找该模板内容时。

    Args:
        query: 搜索查询，可包含模板名或关键词。
        top_k: 返回结果数量，默认5条。

    Returns:
        JSON格式的搜索结果，含匹配文本片段、来源模板名、template_id 和相关度评分。
    """
    import re as _re
    templates = _current_templates.get()
    if not templates:
        return json.dumps({
            "status": "no_templates",
            "message": "当前项目没有添加模板。请提示用户先通过「添加模板」上传参考文档，"
                       "或改用 search_attachment / search_kb。",
            "results": [],
        }, ensure_ascii=False)

    query_lower = query.lower()
    query_terms = query_lower.split()
    all_matches = []

    for tpl in templates:
        name = tpl.get("name") or tpl.get("filename", "?")
        template_id = tpl.get("template_id", "")
        full_text = tpl.get("full_text", "")

        # 目录（章节结构）视为高价值命中对象，单独作为一条结果，便于 LLM 直接拿到结构
        toc = (tpl.get("toc") or "").strip()
        if toc:
            name_hit = name and name.lower() in query_lower
            all_matches.append({
                "content": toc,
                "source": name,
                "template_id": template_id,
                "kind": "目录(章节结构)",
                "score": 1.0 if name_hit or query_lower in toc.lower() else 0.3,
            })

        # 正文 TF 匹配
        if full_text:
            paragraphs = _re.split(r'\n\s*\n', full_text)
            if len(paragraphs) < 2:
                paragraphs = _re.split(r'(?<=[。！？.!?])\s*', full_text)
            for para in paragraphs:
                para = para.strip()
                if len(para) < 10:
                    continue
                para_lower = para.lower()
                score = 0
                for term in query_terms:
                    count = para_lower.count(term)
                    if count > 0:
                        score += count * (1.0 / len(query_terms))
                if query_lower in para_lower:
                    score += 2.0
                if score > 0:
                    all_matches.append({
                        "content": para,
                        "source": name,
                        "template_id": template_id,
                        "kind": "正文",
                        "score": round(min(score / 3.0, 1.0), 3),
                    })

    if not all_matches:
        return json.dumps({
            "status": "no_match",
            "message": f"在已添加的{len(templates)}个模板中未找到与\"{query}\"相关的内容。"
                       f"可用模板: {_templates_hint(templates)}。",
            "results": [],
        }, ensure_ascii=False)

    all_matches.sort(key=lambda x: x["score"], reverse=True)
    seen = set()
    unique = []
    for m in all_matches:
        key = m["content"][:100]
        if key not in seen:
            seen.add(key)
            unique.append(m)
        if len(unique) >= top_k:
            break

    return json.dumps({
        "status": "ok",
        "query": query,
        "count": len(unique),
        "source": "template_text",
        "results": unique,
    }, ensure_ascii=False)


# ── Tool: modify_attachment ──
# 根据用户指令修改上传附件的内容。短文档单遍改写，长文档按章节分段改写
# （先识别受影响章节，再逐段改写，避免无关章节被 LLM 顺手改动）。

# 单遍改写阈值（字符数）：超过则走章节分段改写
_MODIFY_SINGLE_PASS_LIMIT = 6000
# 修改要点标记：标记行之前为文档正文，之后为修改要点
_MODIFY_SUMMARY_MARKER = "@@CHANGES@@"


# ── 段落级手术（docx 编辑指令）──────────────────────────────────────────
# 当附件保留了原 .docx 文件时，修改/精简/补全不再让 LLM 重写全文，
# 而是输出「基于原文档块清单的编辑指令 JSON」，由 docx_edit.apply_edit_ops
# 在原 docx 上执行，未涉及的段落/表格样式原样保留。
_DOCX_EDIT_MAX_INVENTORY_CHARS = 30000  # 块清单字符上限，超过则退回全文重写


def _can_use_docx_edit(target: dict) -> bool:
    """判断附件是否可用段落级手术：有原 .docx 路径且文件存在。"""
    p = target.get("original_path", "")
    return bool(p) and p.lower().endswith(".docx") and os.path.isfile(p)


async def _build_docx_inventory(original_path: str) -> str:
    """异步读取原 docx 的块清单文本（IO 放线程池）。"""
    from app.services.docx_edit import inventory_text_from_path
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(inventory_text_from_path, original_path), timeout=60.0
        )
    except Exception:
        return ""


def _parse_edit_ops(resp: str) -> tuple:
    """解析 LLM 输出的编辑指令 JSON，返回 (ops, summary)。容错：提取首个 JSON 对象。"""
    import re as _re
    if not resp:
        return [], ""
    s = resp.strip()
    if s.startswith("```"):
        s = _re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = _re.sub(r"\s*```$", "", s)
    idx = s.find("{")
    end = s.rfind("}")
    if idx == -1 or end <= idx:
        return [], ""
    try:
        data = json.loads(s[idx:end + 1])
    except Exception:
        return [], ""
    ops = data.get("ops", [])
    if not isinstance(ops, list):
        ops = []
    return ops, data.get("summary", "")


def _ops_modified_chars(ops: list) -> int:
    """粗略估算编辑指令产生的字符量（replace/insert 的 text 长度之和）。"""
    return sum(len(o.get("text", "")) for o in ops if isinstance(o, dict) and o.get("text"))


async def _llm_summarize_ops(inventory_text: str) -> tuple:
    """让 LLM 基于块清单输出「精简」编辑指令。返回 (ops, summary)。"""
    system_prompt = (
        "你是一位专业的文档精简专家。下面是一份 Word 文档的「块清单」，每块以 [序号] 开头，"
        "标题块、正文块、[表格] 块按文档顺序编号。\n"
        "请判断哪些块需要精简，输出编辑指令 JSON，格式：\n"
        '{"ops": [...], "summary": "精简要点（一句话）"}\n'
        "指令类型：\n"
        '- {"op":"delete","block":N}  删除第 N 块（冗余段落、铺垫、过渡句、重复表述）\n'
        '- {"op":"replace","block":N,"text":"压缩后的文字"}  把第 N 块压缩为更精炼文字（保留核心观点、法规条款号、技术参数）\n'
        "规则：\n"
        "- [表格] 块只能 delete 或保留，不得 replace、不得 insert\n"
        "- 标题块尽量保留，不删除\n"
        "- 意思不变：保留核心观点、结论、法规条款号、技术参数，不编造、不篡改\n"
        "- 涉及法规/标准的过程性、描述性语言直接精简为结论\n"
        "- replace 的 text 为单段文字（不含换行）\n"
        "- 不需要改动的块不要出现在 ops 里\n"
        "- 严格输出 JSON，不要输出任何其他内容\n"
    )
    user_prompt = f"请精简这份文档（保留核心要点）：\n\n块清单:\n{inventory_text}"
    response = await _llm_rewrite(system_prompt, user_prompt)
    return _parse_edit_ops(response)


async def _llm_modify_ops(instruction: str, inventory_text: str) -> tuple:
    """让 LLM 基于块清单输出「修改」编辑指令。返回 (ops, summary)。"""
    system_prompt = (
        "你是一位专业的文档改写专家。下面是一份 Word 文档的「块清单」，每块以 [序号] 开头，"
        "标题块、正文块、[表格] 块按文档顺序编号。\n"
        "请根据用户修改指令，输出编辑指令 JSON，格式：\n"
        '{"ops": [...], "summary": "修改要点（一句话）"}\n'
        "指令类型：\n"
        '- {"op":"replace","block":N,"text":"修改后的文字"}  替换第 N 块文字（保留块样式）\n'
        '- {"op":"insert_after","block":N,"text":"新增段落文字"}  在第 N 块之后插入新段落\n'
        '- {"op":"delete","block":N}  删除第 N 块\n'
        "规则：\n"
        "- 严格按用户指令修改；指令未涉及的块不要出现在 ops 里，保持原样\n"
        "- [表格] 块只能 delete 或保留，不得 replace、不得 insert\n"
        "- 标题块尽量保留，不删除\n"
        "- 技术参数要具体、可测量；用中文表述（标准号和必要缩写除外）\n"
        "- replace/insert 的 text 为单段文字（不含换行）\n"
        "- 严格输出 JSON，不要输出任何其他内容\n"
    )
    user_prompt = f"修改指令: {instruction}\n\n块清单:\n{inventory_text}"
    response = await _llm_rewrite(system_prompt, user_prompt)
    return _parse_edit_ops(response)


async def _llm_enrich_ops(instruction: str, inventory_text: str) -> tuple:
    """让 LLM 基于块清单输出「补全」编辑指令。返回 (ops, summary)。"""
    system_prompt = (
        "你是一位专业的文档内容补全专家。下面是一份 Word 文档的「块清单」，每块以 [序号] 开头，"
        "标题块、正文块、[表格] 块按文档顺序编号。\n"
        "请判断哪些块内容简略、单薄、缺少细节，输出补全编辑指令 JSON，格式：\n"
        '{"ops": [...], "summary": "补全要点（一句话）"}\n'
        "指令类型：\n"
        '- {"op":"replace","block":N,"text":"扩写后的文字"}  把第 N 块扩写补充得更详细（保留块样式）\n'
        '- {"op":"insert_after","block":N,"text":"新增段落文字"}  在第 N 块之后补充新段落\n'
        "规则：\n"
        "- 不得删除、篡改或替换已有内容，只能扩写补充（replace 时原文要点必须保留并扩展）\n"
        "- [表格] 块只能 delete 或保留，不得 replace、不得 insert\n"
        "- 内容已足够详实的块不要出现在 ops 里\n"
        "- 补充内容与原文主题一致，不引入新主题\n"
        "- replace/insert 的 text 为单段文字（不含换行）\n"
        "- 严格输出 JSON，不要输出任何其他内容\n"
    )
    user_prompt = f"请把这份文档内容补充得更完整：\n\n块清单:\n{inventory_text}"
    if instruction and instruction.strip():
        user_prompt += f"\n\n补充重点：{instruction.strip()}"
    response = await _llm_rewrite(system_prompt, user_prompt)
    return _parse_edit_ops(response)


async def _llm_rewrite(system_prompt: str, user_prompt: str, timeout: float = 180.0) -> str:
    """调用本地 LLM 改写，返回文本（失败返回空串）"""
    from app.services.minimax import _call_minimax_api_raw

    def _do():
        return _call_minimax_api_raw(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=16384,
        )

    try:
        return await asyncio.wait_for(asyncio.to_thread(_do), timeout=timeout)
    except Exception:
        return ""


def _one_line(text: str, limit: int = 80) -> str:
    """取文本第一个非空行的前 limit 个字符（用于章节列表预览）"""
    for line in (text or "").split("\n"):
        if line.strip():
            line = line.strip()
            return line[:limit] + ("..." if len(line) > limit else "")
    return "(空)"


def _split_sections_by_heading(markdown: str) -> list[str]:
    """按 Markdown 标题 (# ~ ######) 将文档拆分为若干章节，保留原文。

    每个章节从标题行开始，到下一个标题行之前结束（含标题行与其正文）。
    文档开头无标题的内容作为第一个章节（前言段）。
    """
    import re as _re
    lines = markdown.split('\n')
    heading_re = _re.compile(r'^(#{1,6})\s+')
    sections = []
    current = []
    for line in lines:
        if heading_re.match(line) and current:
            sections.append('\n'.join(current))
            current = []
        current.append(line)
    if current:
        sections.append('\n'.join(current))
    if not sections:
        sections = [markdown]
    return sections


def _split_summary(response: str) -> tuple[str, str]:
    """将模型输出拆分为 (正文, 修改要点)。标记行之前为正文，之后为要点。"""
    marker = _MODIFY_SUMMARY_MARKER
    if marker in response:
        doc, _, summary = response.partition(marker)
        return doc.strip(), summary.strip()
    return response.strip(), ""


def _parse_affected_indices(resp: str) -> list[int]:
    """从"受影响章节识别"的模型输出中解析章节编号列表"""
    import re as _re
    if not resp:
        return []
    idx = resp.find("{")
    end = resp.rfind("}")
    if idx != -1 and end > idx:
        try:
            data = json.loads(resp[idx:end + 1])
            affected = data.get("affected", [])
            return [int(i) for i in affected if str(i).lstrip('-').isdigit()]
        except Exception:
            pass
    # 回退：提取所有数字（保守，宁可多改不可漏改）
    return [int(m) for m in _re.findall(r'\d+', resp)]


async def _rewrite_single_pass(full_text: str, instruction: str) -> tuple[str, str]:
    """单遍改写整个文档。返回 (修改后文档, 修改要点)"""
    system_prompt = (
        "你是一位专业的文档改写专家。用户要求修改一份文档，请输出修改后的完整文档。\n"
        "要求:\n"
        "- 严格按用户指令修改；指令未涉及的部分保持原样，不得擅自增删\n"
        "- 保持原有的Markdown格式和标题层级\n"
        + _TABLE_FORMAT_RULE + _NO_PERSON_NAME_RULE
        + _MISSING_TABLE_RULE
        + "- 技术参数要具体、可测量\n"
        "- 用中文表述（标准号和必要缩写除外）\n"
        f"- 在文档正文结束后空一行，输出标记行 `{_MODIFY_SUMMARY_MARKER}`，"
        "标记行之后逐条列出本次修改要点（每条一行，以-开头）\n"
    )
    user_prompt = f"修改指令: {instruction}\n\n原文:\n{full_text}"
    response = await _llm_rewrite(system_prompt, user_prompt)
    if not response:
        return "", ""
    return _split_summary(response)


async def _rewrite_section_wise(full_text: str, instruction: str) -> tuple[str, str]:
    """长文档分段改写：先识别受影响的章节，再逐段改写，其余章节原样保留。

    返回 (修改后文档, 修改要点)。
    """
    sections = _split_sections_by_heading(full_text)

    # 步骤1: 识别受影响的章节（防止无关章节被 LLM 顺手改动）
    outline = "\n".join(f"[{i}] {_one_line(s)}" for i, s in enumerate(sections))
    detect_prompt = (
        "以下是一份文档的章节列表。用户给出一个修改指令。\n"
        "请判断哪些章节需要修改。只把**内容会被指令影响**的章节编号列入 affected。\n"
        "严格输出JSON，格式: {\"affected\": [章节编号]}，不要输出任何其他内容。\n\n"
        f"章节列表:\n{outline}\n\n修改指令: {instruction}"
    )
    detect_resp = await _llm_rewrite(
        "你只输出JSON，不输出任何其他内容。", detect_prompt, timeout=120.0
    )
    affected = _parse_affected_indices(detect_resp)
    if not affected:
        # 无法识别 → 保守处理：全部章节视为受影响（改写指令含"无关则原样输出"保护）
        affected = list(range(len(sections)))

    # 步骤2: 逐个改写受影响章节
    notes = []
    for idx in affected:
        if not (0 <= idx < len(sections)):
            continue
        sec = sections[idx]
        sys_p = (
            "你是一位专业的文档改写专家。下面是文档中的一个章节，请根据用户指令修改它。\n"
            "要求:\n"
            "- 严格按指令修改本节；指令与本节点内容无关时，原样输出本节内容，不要改动\n"
            "- 保持Markdown格式和标题层级\n"
            + _TABLE_FORMAT_RULE + _NO_PERSON_NAME_RULE
            + _MISSING_TABLE_RULE
            + "- 只输出修改后的**这一节**的完整内容，不要输出章节列表或解释\n"
            f"- 在本节内容结束后空一行，输出标记行 `{_MODIFY_SUMMARY_MARKER}`，"
            "标记行之后用一行概括本节的修改要点；若本节未修改则标记行后写“无”\n"
        )
        user_p = f"修改指令: {instruction}\n\n本节原文:\n{sec}"
        resp = await _llm_rewrite(sys_p, user_p)
        if not resp:
            continue  # 失败保留原文
        new_sec, note = _split_summary(resp)
        if new_sec.strip():
            sections[idx] = new_sec.strip()
        if note.strip() and note.strip() != "无":
            notes.append(note.strip())

    modified_md = "\n\n".join(s.strip() for s in sections if s.strip())
    summary = "\n".join(notes)
    return modified_md, summary


@tool
async def modify_attachment(instruction: str, file_id: str = "") -> str:
    """根据用户指令修改指定上传附件的内容，生成修改版文档并提供下载。

    调用时机: 用户要求"修改/改写/更新"某个已上传的参考文档内容时。
    修改的是附件副本，不改变原附件，也不影响已生成的目标文档。

    Args:
        instruction: 用户的具体修改指令，如"把技术参数表中电池寿命改为3年，并更新相关描述"。
        file_id: 要修改的附件ID（来自附件列表）。为空时自动选择第一个已上传附件。

    Returns:
        JSON格式的结果，包含 file_id、filename、summary（修改要点）等信息。
    """
    try:
        attachments = _current_attachments.get()
        if not attachments:
            return json.dumps({
                "status": "error",
                "message": "当前项目没有上传附件，无法修改。请先上传需要修改的文档。",
            }, ensure_ascii=False)

        # 定位附件
        target = None
        if file_id:
            target = next((a for a in attachments if a.get("file_id") == file_id), None)
            if target is None:
                return json.dumps({
                    "status": "error",
                    "message": f"未找到附件 {file_id}。可用附件: {_attachments_hint(attachments)}",
                }, ensure_ascii=False)
        else:
            completed = [a for a in attachments if a.get("status") == "completed" and a.get("full_text")]
            if not completed:
                return json.dumps({
                    "status": "error",
                    "message": "没有可修改的附件（附件可能仍在处理中）。请稍后重试或重新上传。",
                }, ensure_ascii=False)
            if len(completed) > 1:
                return json.dumps({
                    "status": "error",
                    "message": f"有多个附件，请指定要修改的附件 file_id。可用附件: {_attachments_hint(completed)}",
                }, ensure_ascii=False)
            target = completed[0]

        filename = target.get("filename", "document.md")

        # ── 段落级手术：保留原 docx 时，基于块清单输出编辑指令，避免全文重写破坏样式 ──
        if _can_use_docx_edit(target):
            original_path = target.get("original_path")
            inventory = await _build_docx_inventory(original_path)
            if inventory and len(inventory) <= _DOCX_EDIT_MAX_INVENTORY_CHARS:
                ops, summary = await _llm_modify_ops(instruction, inventory)
                if ops:
                    file_id_actual = target.get("file_id", "")
                    _pending_modified_documents[file_id_actual] = {
                        "ops": ops,
                        "original_path": original_path,
                        "filename": filename,
                        "kind": "modify",
                    }
                    return json.dumps({
                        "status": "ok",
                        "kind": "modify",
                        "file_id": file_id_actual,
                        "filename": filename,
                        "modified_chars": _ops_modified_chars(ops),
                        "summary": summary,
                        "message": f"附件「{filename}」修改完成，已生成修改版文档供下载。",
                    }, ensure_ascii=False)
            # 块清单生成失败 / 超长 / ops 为空 → 回退到全文重写

        full_text = target.get("full_text", "") or ""
        if not full_text.strip():
            return json.dumps({
                "status": "error",
                "message": f"附件「{target.get('filename', '?')}」内容为空，无法修改。",
            }, ensure_ascii=False)

        if len(full_text) <= _MODIFY_SINGLE_PASS_LIMIT:
            modified_md, summary = await _rewrite_single_pass(full_text, instruction)
        else:
            modified_md, summary = await _rewrite_section_wise(full_text, instruction)

        if not (modified_md or "").strip():
            return json.dumps({
                "status": "error",
                "message": "文档修改失败（模型未返回有效内容）。请稍后重试。",
            }, ensure_ascii=False)

        # 存入旁路，供 _after_tools_node 写入 state（完整内容不进 LLM 对话历史）
        file_id_actual = target.get("file_id", "")
        _pending_modified_documents[file_id_actual] = {
            "markdown": modified_md,
            "filename": filename,
        }

        return json.dumps({
            "status": "ok",
            "kind": "modify",
            "file_id": file_id_actual,
            "filename": filename,
            "modified_chars": len(modified_md),
            "summary": summary,
            "message": f"附件「{filename}」修改完成，已生成修改版文档供下载。",
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"修改附件时发生异常: {str(e)}。请稍后重试。",
        }, ensure_ascii=False)


# ── Tool: enrich_attachment ──
# 把用户上传附件的内容补充得更完整、更详细。与 modify_attachment 的区别：
# modify_attachment 按用户具体指令修改某处；enrich_attachment 主动识别简略/单薄处并扩写补充。
# 复用 modify_attachment 的旁路存储与前端下载链路（_pending_modified_documents + attachment_modifications）。


async def _enrich_single_pass(full_text: str, instruction: str = "") -> tuple[str, str]:
    """单遍补全整个文档。instruction 为用户指定的补充重点（可空）。返回 (补全后文档, 补充要点)"""
    system_prompt = (
        "你是一位专业的文档内容补全专家。用户上传了一份文档，要求把内容补充得更完整、更详细。\n"
        "请输出补全后的完整文档。\n"
        "要求:\n"
        "- 保持原有章节结构、标题层级和段落顺序完全不变，不得增删章节\n"
        "- 对内容简略、单薄、缺少细节的段落进行扩写补充，使其更详细、更完整、更有说服力\n"
        "- 不得删除、篡改或替换已有的任何内容，只能在原有内容基础上增加细节、说明、数据、示例等\n"
        "- 补充的内容必须与原文主题一致，不得引入文档未涉及的新主题或无关内容\n"
        "- 保持原有的Markdown格式和标题层级\n"
        + _TABLE_FORMAT_RULE + _NO_PERSON_NAME_RULE
        + _MISSING_TABLE_RULE
        + "- 技术参数要具体、可测量\n"
        "- 用中文表述（标准号和必要缩写除外）\n"
        f"- 在文档正文结束后空一行，输出标记行 `{_MODIFY_SUMMARY_MARKER}`，"
        "标记行之后逐条列出本次补充的要点（每条一行，以-开头）\n"
    )
    user_prompt = f"请把下面这份文档的内容补充得更完整、更详细：\n\n原文:\n{full_text}"
    if instruction and instruction.strip():
        user_prompt += f"\n\n补充重点（请优先补充、加强该方面内容）：{instruction.strip()}"
    response = await _llm_rewrite(system_prompt, user_prompt)
    if not response:
        return "", ""
    return _split_summary(response)


async def _enrich_section_wise(full_text: str, instruction: str = "") -> tuple[str, str]:
    """长文档分段补全：先识别内容简略需补充的章节，再逐节补全，其余章节原样保留。

    instruction 为用户指定的补充重点（可空）。返回 (补全后文档, 补充要点)。
    """
    sections = _split_sections_by_heading(full_text)

    # 步骤1: 识别内容简略、需要补充的章节（内容已足够详实的章节不列入）
    outline = "\n".join(f"[{i}] {_one_line(s)}" for i, s in enumerate(sections))
    focus_line = ""
    if instruction and instruction.strip():
        focus_line = f"\n用户补充重点：{instruction.strip()}（相关章节若内容简略或缺失表格应优先列入）"
    detect_prompt = (
        "以下是一份文档的章节列表。用户要求把文档内容补充得更完整。\n"
        "请判断哪些章节需要补充：内容简略、单薄、缺少细节的章节，以及文中引用了表格"
        "（如\"见表X\"、\"如下表所示\"、\"参数如下\"、\"技术要求如下\"等）但实际缺失表格的章节。\n"
        "只把**确实需要补充**的章节编号列入 affected；内容已足够详实且无缺失表格的章节不要列入。\n"
        "严格输出JSON，格式: {\"affected\": [章节编号]}，不要输出任何其他内容。\n"
        + focus_line
        + f"\n\n章节列表:\n{outline}"
    )
    detect_resp = await _llm_rewrite(
        "你只输出JSON，不输出任何其他内容。", detect_prompt, timeout=120.0
    )
    affected = _parse_affected_indices(detect_resp)
    if not affected:
        # 无法识别 → 保守处理：全部章节视为需补充
        affected = list(range(len(sections)))

    # 步骤2: 逐个补全受影响章节
    notes = []
    for idx in affected:
        if not (0 <= idx < len(sections)):
            continue
        sec = sections[idx]
        sys_p = (
            "你是一位专业的文档内容补全专家。下面是文档中的一个章节，请把它补充得更完整、更详细。\n"
            "要求:\n"
            "- 保持本节标题和结构不变\n"
            "- 对内容简略、单薄处进行扩写补充，使其更详细、更完整\n"
            "- 不得删除、篡改或替换已有内容，只能在原有基础上增加细节\n"
            "- 若本节内容已足够完整，原样输出本节，不要改动\n"
            + _TABLE_FORMAT_RULE + _NO_PERSON_NAME_RULE
            + _MISSING_TABLE_RULE
            + "- 只输出补全后的**这一节**的完整内容，不要输出章节列表或解释\n"
            f"- 在本节内容结束后空一行，输出标记行 `{_MODIFY_SUMMARY_MARKER}`，"
            "标记行之后用一行概括本节的补充要点；若本节未补充则标记行后写“无”\n"
        )
        user_p = f"请把下面这一节的内容补充得更完整：\n\n本节原文:\n{sec}"
        if instruction and instruction.strip():
            user_p += f"\n\n补充重点（请优先补充、加强该方面内容）：{instruction.strip()}"
        resp = await _llm_rewrite(sys_p, user_p)
        if not resp:
            continue  # 失败保留原文
        new_sec, note = _split_summary(resp)
        if new_sec.strip():
            sections[idx] = new_sec.strip()
        if note.strip() and note.strip() != "无":
            notes.append(note.strip())

    enriched_md = "\n\n".join(s.strip() for s in sections if s.strip())
    summary = "\n".join(notes)
    return enriched_md, summary


@tool
async def enrich_attachment(file_id: str = "", instruction: str = "") -> str:
    """把用户上传附件的内容补充得更完整、更详细，生成补全版文档并提供下载。

    调用时机: 用户要求"把文档补充完整/补充得更详细/完善这份文档/扩写文档内容"时。
    补全的是附件副本，不改变原附件，也不影响已生成的目标文档。

    与 modify_attachment 的区别: modify_attachment 按用户的具体指令修改某处；
    enrich_attachment 主动识别文档中简略、单薄的内容并扩写补充，使其更完整。

    Args:
        file_id: 要补全的附件ID（来自附件列表）。为空时自动选择第一个已上传附件。
        instruction: 可选，用户指定的补充重点（如"重点补充测试方法"）。
                     为空时对文档整体补全。

    Returns:
        JSON格式的结果，包含 file_id、filename、summary（补充要点）等信息。
    """
    try:
        attachments = _current_attachments.get()
        if not attachments:
            return json.dumps({
                "status": "error",
                "message": "当前项目没有上传附件，无法补全。请先上传需要补全的文档。",
            }, ensure_ascii=False)

        # 定位附件（复用 modify_attachment 的定位逻辑）
        target = None
        if file_id:
            target = next((a for a in attachments if a.get("file_id") == file_id), None)
            if target is None:
                return json.dumps({
                    "status": "error",
                    "message": f"未找到附件 {file_id}。可用附件: {_attachments_hint(attachments)}",
                }, ensure_ascii=False)
        else:
            completed = [a for a in attachments if a.get("status") == "completed" and a.get("full_text")]
            if not completed:
                return json.dumps({
                    "status": "error",
                    "message": "没有可补全的附件（附件可能仍在处理中）。请稍后重试或重新上传。",
                }, ensure_ascii=False)
            if len(completed) > 1:
                return json.dumps({
                    "status": "error",
                    "message": f"有多个附件，请指定要补全的附件 file_id。可用附件: {_attachments_hint(completed)}",
                }, ensure_ascii=False)
            target = completed[0]

        filename = target.get("filename", "document.md")

        # ── 段落级手术：保留原 docx 时，基于块清单输出编辑指令，避免全文重写破坏样式 ──
        if _can_use_docx_edit(target):
            original_path = target.get("original_path")
            inventory = await _build_docx_inventory(original_path)
            if inventory and len(inventory) <= _DOCX_EDIT_MAX_INVENTORY_CHARS:
                ops, summary = await _llm_enrich_ops(instruction, inventory)
                if ops:
                    file_id_actual = target.get("file_id", "")
                    _pending_modified_documents[file_id_actual] = {
                        "ops": ops,
                        "original_path": original_path,
                        "filename": filename,
                        "kind": "enrich",
                    }
                    return json.dumps({
                        "status": "ok",
                        "kind": "enrich",
                        "file_id": file_id_actual,
                        "filename": filename,
                        "modified_chars": _ops_modified_chars(ops),
                        "summary": summary,
                        "message": f"附件「{filename}」补全完成，已生成补全版文档供下载。",
                    }, ensure_ascii=False)
            # 块清单生成失败 / 超长 / ops 为空 → 回退到全文重写

        full_text = target.get("full_text", "") or ""
        if not full_text.strip():
            return json.dumps({
                "status": "error",
                "message": f"附件「{target.get('filename', '?')}」内容为空，无法补全。",
            }, ensure_ascii=False)

        if len(full_text) <= _MODIFY_SINGLE_PASS_LIMIT:
            enriched_md, summary = await _enrich_single_pass(full_text, instruction)
        else:
            enriched_md, summary = await _enrich_section_wise(full_text, instruction)

        if not (enriched_md or "").strip():
            return json.dumps({
                "status": "error",
                "message": "文档补全失败（模型未返回有效内容）。请稍后重试。",
            }, ensure_ascii=False)

        # 存入旁路，供 _after_tools_node 写入 state（完整内容不进 LLM 对话历史）
        file_id_actual = target.get("file_id", "")
        _pending_modified_documents[file_id_actual] = {
            "markdown": enriched_md,
            "filename": filename,
        }

        return json.dumps({
            "status": "ok",
            "kind": "enrich",
            "file_id": file_id_actual,
            "filename": filename,
            "modified_chars": len(enriched_md),
            "summary": summary,
            "message": f"附件「{filename}」补全完成，已生成补全版文档供下载。",
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"补全附件时发生异常: {str(e)}。请稍后重试。",
        }, ensure_ascii=False)


# ── Tool: summarize_attachment ──
# 把用户上传附件的内容精简压缩、去除冗余。与 enrich_attachment 方向相反：
# enrich_attachment 扩写补充；summarize_attachment 压缩精简。
# 复用 modify_attachment / enrich_attachment 的旁路存储与前端下载链路。


async def _summarize_attachment_single_pass(full_text: str) -> tuple[str, str]:
    """单遍精简整个上传文档。返回 (精简后文档, 精简要点)"""
    system_prompt = (
        "你是一位专业的文档精简专家。用户上传了一份文档，要求把内容精简压缩、去除冗余，保留核心要点。\n"
        "请输出精简后的完整文档。\n"
        "要求:\n"
        "- 保持原有章节结构、标题层级和段落顺序完全不变，不得增删章节\n"
        "- 意思不变：保留所有核心观点、结论、法规条款号、技术参数，不编造、不篡改\n"
        "- 精简冗余：合并重复表述、压缩冗长背景、删除过渡句和铺垫\n"
        "- 表格结构必须完整保留：不得删除任何表格、表头，不得删除整列、整行或任何数据行，也不得合并行列（行数列数与顺序不变）；但**表格单元格内的文字可以精简**——压缩冗长描述、删除修饰性措辞、长句改短句，每格须保持语法完整、语义不变、可读通顺；单元格中的数值、参数、单位、标准号不得改变\n"
        "- 涉及法规/标准的过程性、描述性语言（层层分析推导的叙述）直接精简为结论，删除分析推导过程，只保留条款号和最终结论\n"
        "- 保持语句完整、段落连贯，禁止残句、悬空引用\n"
        "- 保持原有的Markdown格式和标题层级\n"
        + _TABLE_FORMAT_RULE + _NO_PERSON_NAME_RULE
        + "- 用中文表述（标准号和必要缩写除外）\n"
        f"- 在文档正文结束后空一行，输出标记行 `{_MODIFY_SUMMARY_MARKER}`，"
        "标记行之后逐条列出本次精简的要点（每条一行，以-开头）\n"
    )
    user_prompt = f"请把下面这份文档的内容精简压缩、保留核心要点：\n\n原文:\n{full_text}"
    response = await _llm_rewrite(system_prompt, user_prompt)
    if not response:
        return "", ""
    return _split_summary(response)


async def _summarize_attachment_section_wise(full_text: str) -> tuple[str, str]:
    """长文档分段精简：逐节精简，失败章节保留原文。返回 (精简后文档, 精简要点)。"""
    sections = _split_sections_by_heading(full_text)

    notes = []
    for idx in range(len(sections)):
        sec = sections[idx]
        sys_p = (
            "你是一位专业的文档精简专家。下面是文档中的一个章节，请把它精简压缩、去除冗余。\n"
            "要求:\n"
            "- 保持本节标题和结构不变\n"
            "- 意思不变：保留本节核心观点、结论、法规条款号、技术参数\n"
            "- 合并重复表述、压缩冗长背景、删除过渡句和铺垫\n"
            "- 所有表格（含表号、表头、全部数据行）结构必须完整保留，不得删除任何表格、表头或数据行，也不得合并行列；单元格内文字可精简但须语义不变、可读通顺，数值/参数/单位不得改变\n"
            "- 涉及法规/标准的过程性、描述性语言直接精简为结论，删除分析推导过程\n"
            "- 保持语句完整、段落连贯，禁止残句、悬空引用\n"
            + _TABLE_FORMAT_RULE + _NO_PERSON_NAME_RULE
            + "- 只输出精简后的**这一节**的完整内容，不要输出章节列表或解释\n"
            f"- 在本节内容结束后空一行，输出标记行 `{_MODIFY_SUMMARY_MARKER}`，"
            "标记行之后用一行概括本节的精简要点；若本节未精简则标记行后写“无”\n"
        )
        user_p = f"请精简下面这一节的内容：\n\n本节原文:\n{sec}"
        resp = await _llm_rewrite(sys_p, user_p)
        if not resp:
            continue  # 失败保留原文
        new_sec, note = _split_summary(resp)
        if new_sec.strip():
            sections[idx] = new_sec.strip()
        if note.strip() and note.strip() != "无":
            notes.append(note.strip())

    summarized_md = "\n\n".join(s.strip() for s in sections if s.strip())
    summary = "\n".join(notes)
    return summarized_md, summary


@tool
async def summarize_attachment(file_id: str = "") -> str:
    """把用户上传附件的内容精简压缩、去除冗余，生成精简版文档并提供下载。

    调用时机: 用户要求"精简这篇文档/压缩这份附件/把上传的文档精简一下/删掉冗余内容"时。
    精简的是附件副本，不改变原附件，也不影响已生成的目标文档。

    与 summarize_section / summarize_document 的区别: 那两者精简的是已生成的目标文档章节
    （generated_sections）；本工具精简的是用户上传的附件（attachments）。

    Args:
        file_id: 要精简的附件ID（来自附件列表）。为空时自动选择第一个已上传附件。

    Returns:
        JSON格式的结果，包含 file_id、filename、summary（精简要点）等信息。
    """
    try:
        attachments = _current_attachments.get()
        if not attachments:
            return json.dumps({
                "status": "error",
                "message": "当前项目没有上传附件，无法精简。请先上传需要精简的文档。",
            }, ensure_ascii=False)

        # 定位附件（复用 modify_attachment / enrich_attachment 的定位逻辑）
        target = None
        if file_id:
            target = next((a for a in attachments if a.get("file_id") == file_id), None)
            if target is None:
                return json.dumps({
                    "status": "error",
                    "message": f"未找到附件 {file_id}。可用附件: {_attachments_hint(attachments)}",
                }, ensure_ascii=False)
        else:
            completed = [a for a in attachments if a.get("status") == "completed" and a.get("full_text")]
            if not completed:
                return json.dumps({
                    "status": "error",
                    "message": "没有可精简的附件（附件可能仍在处理中）。请稍后重试或重新上传。",
                }, ensure_ascii=False)
            if len(completed) > 1:
                return json.dumps({
                    "status": "error",
                    "message": f"有多个附件，请指定要精简的附件 file_id。可用附件: {_attachments_hint(completed)}",
                }, ensure_ascii=False)
            target = completed[0]

        filename = target.get("filename", "document.md")

        # ── 段落级手术：保留原 docx 时，基于块清单输出编辑指令，避免全文重写破坏样式 ──
        if _can_use_docx_edit(target):
            original_path = target.get("original_path")
            inventory = await _build_docx_inventory(original_path)
            if inventory and len(inventory) <= _DOCX_EDIT_MAX_INVENTORY_CHARS:
                ops, summary = await _llm_summarize_ops(inventory)
                if ops:
                    file_id_actual = target.get("file_id", "")
                    _pending_modified_documents[file_id_actual] = {
                        "ops": ops,
                        "original_path": original_path,
                        "filename": filename,
                        "kind": "summarize",
                    }
                    return json.dumps({
                        "status": "ok",
                        "kind": "summarize",
                        "file_id": file_id_actual,
                        "filename": filename,
                        "modified_chars": _ops_modified_chars(ops),
                        "summary": summary,
                        "message": f"附件「{filename}」精简完成，已生成精简版文档供下载。",
                    }, ensure_ascii=False)
            # 块清单生成失败 / 超长 / ops 为空 → 回退到全文重写

        full_text = target.get("full_text", "") or ""
        if not full_text.strip():
            return json.dumps({
                "status": "error",
                "message": f"附件「{target.get('filename', '?')}」内容为空，无法精简。",
            }, ensure_ascii=False)

        if len(full_text) <= _MODIFY_SINGLE_PASS_LIMIT:
            summarized_md, summary = await _summarize_attachment_single_pass(full_text)
        else:
            summarized_md, summary = await _summarize_attachment_section_wise(full_text)

        if not (summarized_md or "").strip():
            return json.dumps({
                "status": "error",
                "message": "文档精简失败（模型未返回有效内容）。请稍后重试。",
            }, ensure_ascii=False)

        # 存入旁路，供 _after_tools_node 写入 state（完整内容不进 LLM 对话历史）
        file_id_actual = target.get("file_id", "")
        _pending_modified_documents[file_id_actual] = {
            "markdown": summarized_md,
            "filename": filename,
        }

        return json.dumps({
            "status": "ok",
            "kind": "summarize",
            "file_id": file_id_actual,
            "filename": filename,
            "modified_chars": len(summarized_md),
            "summary": summary,
            "message": f"附件「{filename}」精简完成，已生成精简版文档供下载。",
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"精简附件时发生异常: {str(e)}。请稍后重试。",
        }, ensure_ascii=False)


# ── Tool 2: generate_section ──

@tool
async def generate_section(section_name: str, doc_type: str = "design_development_plan") -> str:
    """基于当前已确认的策划内容，生成指定文档类型中指定章节的初稿。

    生成前应确认: 该章节依赖的策划内容项是否都已确认。
    生成后会暂停等待用户确认——用户可以批准、要求修改、或重新生成。

    Args:
        section_name: 章节名称，如 "目的和范围"、"阶段划分"、"风险可接受性准则" 等。
        doc_type: 文档类型标识，如 "design_development_plan"、"risk_management_plan" 等。
                  从当前会话状态的 doc_type 字段获取，默认为 design_development_plan。

    Returns:
        生成的章节内容 (Markdown格式)。
    """
    try:
        from app.services.minimax import _call_minimax_api_raw, DOC_CHAPTERS, DEFAULT_CHAPTERS
        from app.services.doc_types import DOC_TYPE_LABELS
        from app.services.prompt_engineer import DOC_TYPE_SPECIFIC_PROMPTS

        doc_label = DOC_TYPE_LABELS.get(doc_type, "设计策划文档")

        # 查找章节定义 (用于更精准的生成指导)
        chapters = DOC_CHAPTERS.get(doc_type, DEFAULT_CHAPTERS)
        chapter_query = ""
        for ch in chapters:
            if ch.get("name") == section_name:
                chapter_query = ch.get("query", "")
                break

        # 文档类型专属专家提示词
        expert_prompt = DOC_TYPE_SPECIFIC_PROMPTS.get(doc_type, "")

        # 构建 system prompt: 专家角色 + 文档类型特定要求
        expert_section = f"\n\n# 本文档类型特定要求\n{expert_prompt}" if expert_prompt else ""

        # 已覆盖内容摘要（排除本节省），避免与已生成章节内容重复
        covered_digest = _build_covered_digest(section_name)
        covered_block = (
            f"\n## 去重要求（避免跨章节内容重复）\n"
            f"- 已覆盖内容（请勿重复，引用用\"详见第X章\"）:\n{covered_digest}\n"
            if covered_digest
            else "\n## 去重要求（避免跨章节内容重复）\n"
                 "- 产品通用参数（尺寸、储药量、输注精度、BLE、IPX8、灭菌方式、Class C等）"
                 "只在最相关章节写全，其他章节引用时用\"见第X章\"简述\n"
                 "- 标准总则类描述（\"本部分适用于…\"\"本标准规定…\"）全文档只出现一次\n"
                 "- 同一法规条款仅在与本节直接相关处展开，不在多节重复相同说明\n"
        )

        # 模板写作风格参考：用户上传模板时注入，让章节模仿模板风格
        template_style_block = _build_template_style_hint()
        style_section = f"{template_style_block}\n\n" if template_style_block else ""

        # 全文整体风格参照：从已生成章节提取结构概览 + 文风范本，让新章节与全文风格一致
        style_reference = _build_style_reference(section_name)
        style_ref_block = f"{style_reference}\n\n" if style_reference else ""

        system_prompt = f"""你是一位贴敷式胰岛素泵RA文档专家。请基于当前已确认的策划内容信息，
生成《{doc_label}》文档中「{section_name}」章节的初稿。{expert_section}

要求:
- 内容必须极其细致和具体，每个段落都要有实质性内容，不能只写框架标题
- 内容专业、完整，符合NMPA注册申报要求
{_regulation_clause_rule(doc_type)}- 使用Markdown格式，标题层级清晰 (##, ###)
- 技术参数要具体、可测量、有明确的数值范围
- 表格要填写完整，不能留"(描述)"或"待填写"等占位符
{_TABLE_FORMAT_RULE}{_NO_PERSON_NAME_RULE}- 针对贴敷式胰岛素泵产品特性编写{_PRODUCT_PREMISE_RULE}
- 生成内容的详细程度要像实际可用于注册申报的正式文档一样
- 用中文表述 (标准号和必要缩写除外)
- 禁止以"本章依据XX标准编制"等冗余前缀行开头

{covered_block}
{style_ref_block}{style_section}{_output_structure_requirement(doc_type)}{_supplementary_block()}{_memory_context_block()}{_attachment_priority_rule()}{_grounding_rule()}{_doc_scope_rule(doc_type)}{_user_requirements_block()}"""

        # RAG 检索: 用 LLM 基于产品上下文+章节信息生成针对性查询词
        rag_context = ""
        try:
            queries = await _generate_search_queries(
                chapter_name=section_name,
                intent=chapter_query[:200] if chapter_query else "",
                num_queries=3,
            )
            if not queries:
                # 回退到原硬编码拼接
                fallback = f"{doc_label} {section_name}"
                if chapter_query:
                    fallback += f" {chapter_query[:200]}"
                queries = [fallback]

            # 对每条查询词调用 search_kb，合并去重结果
            merged_results = []
            seen_keys = set()
            for q in queries:
                rag_result = await search_kb.ainvoke({"query": q, "top_k": 15})
                rag_data = json.loads(rag_result)
                if rag_data.get("status") == "ok" and rag_data.get("results"):
                    for item in rag_data["results"]:
                        key = item.get("content", "")[:100]
                        if key not in seen_keys:
                            seen_keys.add(key)
                            merged_results.append(item)

            if merged_results:
                lines = ["\n\n# 知识库参考资料（必须优先依据以下内容编写）:"]
                for j, r in enumerate(merged_results, 1):
                    lines.append(
                        f"\n[参考{j}] 来源: {r['source']} (相关度:{r['score']})\n{r['content']}"
                    )
                rag_context = "".join(lines)
        except Exception:
            pass

        # 附件检索：用户上传附件内容为最高优先参考资料（参数/数据/条款优先采用）
        att_query = f"{doc_label} {section_name}"
        if chapter_query:
            att_query += f" {chapter_query[:100]}"
        att_context = await _attachment_refs_block(att_query, top_k=5, verb="编写")

        # 构建 user prompt: 章节特定查询
        query_hint = f"\n\n# 本章节内容要点\n请重点覆盖以下方面: {chapter_query}" if chapter_query else ""
        # 附件分配内容（预分配映射命中本章节时注入，最高优先参考）
        assigned_context = _assigned_attachment_block(section_name)
        if assigned_context:
            assigned_context = (
                f"\n\n# 附件分配内容（最高优先参考——已通读全部上传附件并判定与本章相关，"
                f"其中的参数、数据、条款与表述必须优先采用）:\n{assigned_context}"
            )
        user_prompt = f"请生成「{section_name}」章节的{doc_label}文档内容。内容包括该章节应覆盖的所有要求项、适用的法规标准依据、以及建议的具体参数/验收标准。{query_hint}{assigned_context}{att_context}{rag_context}"

        response = await asyncio.wait_for(
            _stream_llm_to_sink(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=8192,
            ),
            timeout=300.0,
        )

        if response:
            return (
                f"[章节: {section_name}]\n\n{response}\n\n"
                "（系统提示：以上全文已保存进文档。回复用户时不要复述全文，"
                "只输出提炼后的简短总结：本章要点 3-6 条短句，整条回复 ≤200 字。）"
            )
        else:
            return f"[错误] 无法生成「{section_name}」章节。MiniMax API 返回空结果，请稍后重试。"

    except asyncio.TimeoutError:
        return f"[错误] 生成「{section_name}」章节超时（300秒）。请尝试缩小章节范围或稍后重试。"
    except ImportError:
        return f"[错误] 生成服务暂时不可用。请稍后重试。"
    except Exception as e:
        return f"[错误] 生成「{section_name}」时发生异常: {str(e)}。请稍后重试。"


# ── Tool 3: revise_section ──（见下方）

# ── Tool 4: build_docx ──

# 内存中的文档存储 (download_id → bytes)
_docx_store: dict = {}


def _store_docx(
    file_bytes: bytes,
    filename: str,
    content_type: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
) -> str:
    """将生成的文档（docx 或 xlsx）存入内存，返回download_id"""
    import uuid
    download_id = str(uuid.uuid4())[:8]
    _docx_store[download_id] = {
        "bytes": file_bytes,
        "filename": filename,
        "content_type": content_type,
    }
    return download_id


def _get_docx(download_id: str) -> dict | None:
    """从内存中取出docx（不删除，允许多次下载）"""
    return _docx_store.get(download_id)


async def _build_risk_excel(doc_type: str, product_name: str) -> str:
    """风险分析总表类文档：调用本地模型生成结构化风险条目并构建 Excel (.xlsx)。"""
    from app.services.risk_excel import generate_risk_rows, build_risk_excel
    from app.services.doc_types import DOC_TYPE_LABELS

    classification = _current_product_classification.get()
    intended_use = _current_product_intended_use.get()

    rows = await asyncio.wait_for(
        asyncio.to_thread(
            generate_risk_rows, doc_type, product_name, classification, intended_use
        ),
        timeout=240.0,
    )
    if not rows:
        return json.dumps({
            "status": "error",
            "message": "风险条目生成失败（模型未返回有效数据），请稍后重试。",
        }, ensure_ascii=False)

    file_bytes = await asyncio.to_thread(build_risk_excel, doc_type, rows)

    label = DOC_TYPE_LABELS.get(doc_type, "风险分析和管理总表")
    filename = f"{product_name}_{label}.xlsx"

    download_id = _store_docx(
        file_bytes,
        filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    return json.dumps({
        "status": "ok",
        "download_id": download_id,
        "filename": filename,
        "size_bytes": len(file_bytes),
        "message": f"风险分析和管理总表 Excel「{filename}」已生成，点击下载按钮即可获取。",
    }, ensure_ascii=False)


@tool
async def build_docx(doc_type: str = "", product_name: str = "", markdown: str = "") -> str:
    """将已生成的文档内容构建为可下载文件并提供下载。

    普通文档构建为 Word (.docx)；风险分析总表类文档
    （product_risk_analysis_matrix / cybersecurity_risk_analysis_matrix）
    自动构建为 Excel (.xlsx)，与参考「风险分析和管理总表」格式一致。

    调用时机: 在所有章节生成完毕、用户确认内容无误后调用。
    调用后前端会自动弹出下载按钮。
    当 markdown 参数为空时，自动使用已生成的章节内容。

    Args:
        doc_type: 文档类型，如 "design_input"、"risk_management_report" 等。为空时自动从上下文获取。
        product_name: 产品名称，用于生成文件名。为空时自动从上下文获取。
        markdown: 完整的Markdown格式文档内容。为空时自动使用已生成的所有章节。

    Returns:
        JSON格式的结果，包含 download_id 和文件名。
    """
    try:
        from app.services.template import TemplateService
        from app.services.doc_types import DOC_TYPE_LABELS
        from app.services.risk_excel import is_risk_matrix_doc

        # 从上下文填充缺失参数
        if not doc_type:
            doc_type = _current_doc_type.get()
        if not product_name:
            product_name = _current_product_name.get()
        if not markdown:
            markdown = _current_generated_markdown.get()

        # ── 风险分析总表类文档 → 直接导出 Excel (.xlsx) ──
        if is_risk_matrix_doc(doc_type):
            return await _build_risk_excel(doc_type, product_name)

        if not markdown:
            return json.dumps({
                "status": "error",
                "message": "没有已生成的文档内容。请先生成至少一个章节后再导出。",
            }, ensure_ascii=False)

        label = DOC_TYPE_LABELS.get(doc_type, doc_type) or "设计策划文档"

        # ── 导出前处理链：①法规引用剥离（生成时保留法规依据防幻觉，呈现时去除）
        #    ②全文字数收敛（软收敛，不硬截断）。任一环节改动内容都同步回 state，
        #    保证 review 页与下载文件一致。风险矩阵类已在上面提前返回。──
        condense_stats = None
        strip_stats = None
        _pending_condensed_sections.clear()  # 清空上轮旁路，避免本轮未精简时残留旧数据
        original_markdown = markdown
        try:
            # ① 法规引用剥离（默认开启，env STRIP_REGULATIONS_ON_EXPORT=false 关闭）
            if _STRIP_REGULATIONS_ENABLED:
                stripped_md, n_stripped = await _strip_regulations_from_document(markdown)
                if stripped_md and n_stripped and stripped_md.strip() != markdown.strip():
                    markdown = stripped_md
                    strip_stats = {"subsections": n_stripped}
                    print(f"[build_docx] 法规引用剥离: {n_stripped} 个小节已处理")

            # ② 全文字数收敛
            condensed_md, condense_stats = await _condense_document_to_limit(
                markdown,
                doc_label=label,
                target_chars=_DOC_WORD_LIMIT,
                max_iterations=_DOC_WORD_LIMIT_MAX_ITERATIONS,
            )
            if condensed_md and condense_stats and \
                    condense_stats.get("final_chars", 0) < condense_stats.get("original_chars", 0):
                markdown = condensed_md
                print(f"[build_docx] 字数收敛: {condense_stats.get('original_chars')} → "
                      f"{condense_stats.get('final_chars')} 字（迭代 {condense_stats.get('iterations')} 轮，"
                      f"收敛={condense_stats.get('converged')}）")

            # 剥离或精简实际改动内容 → 同步回 state（供 review 页与后续修改保持一致）
            if markdown.strip() != original_markdown.strip():
                _pending_condensed_sections["sections"] = {
                    sec["name"]: sec["content"]
                    for sec in _split_full_markdown(markdown) if sec.get("name")
                }
                _pending_condensed_sections["stats"] = condense_stats or {}
        except Exception as e:
            print(f"[build_docx] 导出前处理失败，改用原文导出: {type(e).__name__}: {e}")
            condense_stats = None

        def _do_build():
            template_service = TemplateService()
            doc = template_service.load_template(doc_type)
            doc = template_service.fill_template(
                doc=doc,
                content=markdown,
                product_name=product_name,
                doc_type=doc_type,
                format_overrides=dict(_current_document_format.get() or {}),
            )
            file_bytes = template_service.document_to_bytes(doc)
            return file_bytes

        file_bytes = await asyncio.wait_for(
            asyncio.to_thread(_do_build),
            timeout=60.0,
        )

        filename = f"{product_name}_{label}.docx"

        download_id = _store_docx(file_bytes, filename)

        return json.dumps({
            "status": "ok",
            "download_id": download_id,
            "filename": filename,
            "size_bytes": len(file_bytes),
            "word_count": condense_stats,
            "regulation_stripped": strip_stats,
            "message": f"文档「{filename}」已生成，点击下载按钮即可获取。",
        }, ensure_ascii=False)

    except asyncio.TimeoutError:
        return json.dumps({
            "status": "error",
            "message": "文档构建超时（60秒）。请稍后重试。",
        }, ensure_ascii=False)
    except ImportError as e:
        return json.dumps({
            "status": "error",
            "message": f"Word模板服务不可用: {str(e)}",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"文档构建失败: {str(e)}",
        }, ensure_ascii=False)

# ── 修改符合性自检（revise_section 生成后多轮验证）──
# 用户提出修改意见重新生成后，自动检查：①是否完整落实了最新指令 ②是否做了
# 指令之外的额外更改；未通过则带审查反馈修复再验，封顶 REVISION_VERIFY_ROUNDS 轮。

_REVISION_VERIFY_ROUNDS = int(os.getenv("REVISION_VERIFY_ROUNDS", "2"))

_VERIFY_REVISION_SYSTEM = """你是文档修改审查专家。给定用户的修改指令、修改前的原文和修改后的内容，请严格审查两点：
1. 指令落实：修改后内容是否完整落实了用户指令的全部要求？列出未落实或落实不到位的点
2. 额外更改：是否存在用户指令之外的更改（改动了指令未涉及的内容、措辞、结构、数据）？逐条列出具体位置
输出严格 JSON（无围栏无解释）：
{"instruction_followed": true/false,
 "missing_points": ["未落实点…"],
 "has_unauthorized_changes": true/false,
 "unauthorized_changes": ["指令外更改的具体描述…"]}
审查标准：宁可严格——不确定是否属于指令范围的更改也列出来；两项都通过才输出 true。"""


async def _verify_revision_once(instruction: str, original: str, revised: str) -> dict:
    """单次修改审查（LLM），返回审查 JSON；失败返回空 dict（不阻塞）。"""
    from app.services.minimax import _call_minimax_api_raw

    user_prompt = (
        f"## 用户修改指令\n{instruction}\n\n"
        f"## 修改前原文\n{original[:6000]}\n\n"
        f"## 修改后内容\n{revised[:6000]}\n\n"
        f"请审查并输出 JSON。"
    )

    def _do():
        return _call_minimax_api_raw(
            system_prompt=_VERIFY_REVISION_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=2048,
        )

    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_do), timeout=120.0)
    except Exception as e:
        print(f"[revise_section] 修改审查调用失败（跳过自检）: {e}")
        return {}
    data = _parse_att_map_json(raw or "")
    return data if isinstance(data, dict) else {}


async def _verify_revision_compliance(instruction: str, original: str, revised: str,
                                      revision_system_prompt: str, revision_user_prompt: str,
                                      max_rounds: int = _REVISION_VERIFY_ROUNDS) -> tuple:
    """修改符合性自检闭环：审查 → 未通过带反馈修复 → 再审查，封顶 max_rounds 轮。

    Returns:
        (最终内容, 报告 dict)。报告: {"rounds", "passed"（True/False/None=验证不可用）,
        "missing_points", "unauthorized_changes", "repaired"}。
        验证不可用时返回原内容且不阻塞修改流程。
    """
    content = revised
    report = {"rounds": 0, "passed": None, "missing_points": [],
              "unauthorized_changes": [], "repaired": False}
    try:
        for round_i in range(1, max_rounds + 1):
            report["rounds"] = round_i
            verdict = await _verify_revision_once(instruction, original, content)
            if not verdict:
                return content, report  # 验证不可用，不阻塞

            missing = [str(x).strip() for x in (verdict.get("missing_points") or [])
                       if str(x).strip()]
            unauth = []
            if verdict.get("has_unauthorized_changes"):
                unauth = [str(x).strip() for x in (verdict.get("unauthorized_changes") or [])
                          if str(x).strip()]
            followed = bool(verdict.get("instruction_followed")) and not missing

            if followed and not unauth:
                report["passed"] = True
                print(f"[revise_section] 修改自检通过（第 {round_i} 轮）")
                return content, report

            # 未通过 → 构造审查反馈，带反馈修复后进入下一轮验证
            report["missing_points"] = missing
            report["unauthorized_changes"] = unauth
            feedback_parts = []
            if missing:
                feedback_parts.append(
                    "以下指令要求未落实，必须补充落实：\n- " + "\n- ".join(missing))
            if unauth:
                feedback_parts.append(
                    "以下更改超出了用户指令范围，必须恢复为修改前原文的对应内容"
                    "（只保留指令明确要求的部分）：\n- " + "\n- ".join(unauth))
            repair_user = (
                revision_user_prompt
                + "\n\n# ⚠️ 修改审查反馈（上一版修改未通过审查，本次输出必须同时满足"
                  "原修改指令与以下修正要求）\n" + "\n\n".join(feedback_parts)
            )
            try:
                repaired = await asyncio.wait_for(
                    _stream_llm_to_sink(
                        system_prompt=revision_system_prompt,
                        user_prompt=repair_user,
                        temperature=0.3,
                        max_tokens=8192,
                    ),
                    timeout=180.0,
                )
            except Exception as e:
                print(f"[revise_section] 修复轮调用失败: {e}")
                break
            if repaired and repaired.strip():
                content = repaired
                report["repaired"] = True
                continue  # 修复后再验
            break

        report["passed"] = False
        print(f"[revise_section] 修改自检 {report['rounds']} 轮后仍有待确认项")
        return content, report
    except Exception as e:
        print(f"[revise_section] 修改自检异常（不阻塞）: {e}")
        return content, report


@tool
async def revise_section(section_name: str, instruction: str, doc_type: str = "design_development_plan") -> str:
    """根据用户指令修改指定文档类型的指定章节。

    在现有内容基础上修改，保持与首次生成相同的详细程度和专业深度。
    遵循最小改动原则：只修改指令涉及的内容，未涉及的段落/标题/表格逐字保留，
    保持原章节的结构、格式和措辞风格。修改后展示变更摘要。

    Args:
        section_name: 要修改的章节名称。
        instruction: 用户的具体修改指令，如"将阶段划分从5个阶段调整为7个阶段"。
        doc_type: 文档类型标识，如 "design_development_plan"、"risk_management_plan" 等。
                  从当前会话状态的 doc_type 字段获取，默认为 design_development_plan。

    Returns:
        修改后的章节内容 (Markdown格式)。
    """
    try:
        from app.services.minimax import _call_minimax_api_raw
        from app.services.doc_types import DOC_TYPE_LABELS
        from app.services.prompt_engineer import DOC_TYPE_SPECIFIC_PROMPTS

        doc_label = DOC_TYPE_LABELS.get(doc_type, "设计策划文档")
        expert_prompt = DOC_TYPE_SPECIFIC_PROMPTS.get(doc_type, "")
        expert_section = f"\n\n{expert_prompt}" if expert_prompt else ""

        # ── 获取当前章节内容（容忍章节名带编号/空格等差异）──
        current_section_content = ""
        current_markdown = _current_generated_markdown.get()
        if current_markdown:
            import re

            def _norm_title(s):
                # 去掉编号前缀（"1." "2、" "第3章" 等）与所有空白后再比较
                s = re.sub(r'^(第?[0-9一二三四五六七八九十百]+[.、章节\-．]|\(\d+\)|（\d+）)\s*',
                           '', (s or '').strip())
                return s.replace(' ', '')

            md_lines = current_markdown.split('\n')
            # 收集一级/二级标题（章节正文自带 ## 标题行；_sync_doc_context 另加 # 章节名 行）
            headings = []
            for i, ln in enumerate(md_lines):
                s = ln.strip()
                if re.match(r'^##\s+\S', s):
                    headings.append((i, 2, re.sub(r'^##\s+', '', s)))
                elif re.match(r'^#\s+\S', s):
                    headings.append((i, 1, re.sub(r'^#\s+', '', s)))

            target = None
            for i, level, title in headings:
                if title.strip() == section_name.strip():
                    target = (i, level)
                    break
            if target is None:
                for i, level, title in headings:
                    a, b = _norm_title(title), _norm_title(section_name)
                    if a and b and (a == b or a in b or b in a):
                        target = (i, level)
                        break

            if target:
                start, level = target
                pat = r'^#\s' if level == 1 else r'^#{1,2}\s'  # 二级目标同时截断下一章的 `# 章节名` 标记行
                section_lines = []
                for line in md_lines[start:]:
                    s = line.strip()
                    if section_lines and re.match(pat, s):
                        break
                    section_lines.append(line)
                if section_lines:
                    current_section_content = '\n'.join(section_lines)

        if not current_section_content:
            # 找不到原章节时必须报错并给出可用章节名，
            # 防止在拿不到原文的情况下整篇重写、被当作新章节追加到原文档后
            # （下载时出现「原文档 + 修改稿」两份拼接的 bug）
            avail = []
            for ln in (current_markdown or '').split('\n'):
                s = ln.strip()
                if s.startswith('# ') or s.startswith('## '):
                    t = s.lstrip('#').strip()
                    if t and t not in avail:
                        avail.append(t)
            return (
                f"[错误] 未找到章节「{section_name}」的内容。"
                f"请从以下已有章节中选择准确的章节名后重试: "
                f"{'、'.join(avail) if avail else '（暂无已生成章节，请先用 generate_section 生成）'}"
            )

        # ── RAG 检索：获取相关知识库参考资料 ──
        rag_context = ""
        try:
            rag_query = f"{doc_label} {section_name} {instruction}"
            rag_result = await search_kb.ainvoke({"query": rag_query, "top_k": 15})
            rag_data = json.loads(rag_result)
            if rag_data.get("status") == "ok" and rag_data.get("results"):
                lines = ["\n\n# 知识库参考资料（必须优先依据以下内容进行修改）:"]
                for j, r in enumerate(rag_data["results"], 1):
                    lines.append(
                        f"\n[参考{j}] 来源: {r['source']} (相关度:{r['score']})\n{r['content']}"
                    )
                rag_context = "".join(lines)
        except Exception:
            pass

        # 附件检索：用户上传附件内容为最高优先参考资料（修改时优先依据附件原文）
        att_context = await _attachment_refs_block(
            f"{doc_label} {section_name} {instruction[:100]}", top_k=5, verb="修改"
        )

        # 全文整体风格参照：让修改后的章节与全文既有风格保持一致
        style_reference = _build_style_reference(section_name)
        style_ref_block = f"{style_reference}\n\n" if style_reference else ""

        # ── 构建高质量修订 prompt（复用 write_chapter 的详细质量要求）──
        system_prompt = f"""你是一位贴敷式胰岛素泵RA文档专家。用户要求修改《{doc_label}》文档中「{section_name}」章节。{expert_section}

要求:
- 内容必须极其细致和具体，每个段落都要有实质性内容，不能只写框架标题
- 内容专业、完整，符合NMPA注册申报要求
{_regulation_clause_rule(doc_type)}- 使用Markdown格式，标题层级清晰 (##, ###)
- 技术参数要具体、可测量、有明确的数值范围
- 表格要填写完整，不能留"(描述)"或"待填写"等占位符
{_TABLE_FORMAT_RULE}{_NO_PERSON_NAME_RULE}- 针对贴敷式胰岛素泵产品特性编写{_PRODUCT_PREMISE_RULE}
- 修改后内容的详细程度要与首次生成的其他章节保持一致，像实际可用于注册申报的正式文档一样
- 用中文表述 (标准号和必要缩写除外)

修改规则（最小改动原则，优先级最高）:
- 只修改用户指令涉及的内容；与指令无关的段落、标题、表格必须逐字保留，禁止顺手重写、润色、扩写、合并或重新排序
- 严格保持原章节的整体结构和风格：标题层级、小节顺序、表格列结构、列表编号方式、术语和措辞语气均与原文保持一致
- 修改后的内容在格式、详略程度和语气上与原文无缝衔接，读起来仍像同一份文档，不要让修改处与上下文风格脱节
- 根据用户指令修改内容，修改处的详细程度和专业深度不低于原文对应部分
- 如果用户指令明确要求添加新内容，才展开详细描述（每个要点至少200字）
- 保持Markdown格式和标题层级
- 如果修改影响了其他章节的参数/引用，在回复末尾用"⚠️ 关联影响:"标注
- 用中文回复

{style_ref_block}{_output_structure_requirement(doc_type, is_revision=True)}{_supplementary_block()}{_memory_context_block()}{_attachment_priority_rule()}{_grounding_rule()}{_doc_scope_rule(doc_type)}{_user_requirements_block(instruction)}"""

        user_prompt = f"""请修改《{doc_label}》的「{section_name}」章节，修改指令: {instruction}

请在修改后:
1. 输出修改后的完整章节内容（保持与首次生成相同的详细程度；指令未涉及的内容保持原文不变）
2. 在末尾用"📝 修改摘要:"列出具体变更点"""

        # 注入当前章节内容、附件分配块与 RAG 上下文（附件优先级最高）
        if current_section_content:
            user_prompt += f"\n\n# 当前章节内容（请在此基础上修改）:\n{current_section_content}"
        assigned_context = _assigned_attachment_block(section_name)
        if assigned_context:
            user_prompt += (
                f"\n\n# 附件分配内容（最高优先参考——已通读全部上传附件并判定与本章相关，"
                f"其中的参数、数据、条款与表述必须优先采用）:\n{assigned_context}"
            )
        if att_context:
            user_prompt += f"\n{att_context}"
        if rag_context:
            user_prompt += f"\n{rag_context}"

        response = await asyncio.wait_for(
            _stream_llm_to_sink(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=8192,
            ),
            timeout=180.0,
        )

        # ── 修改符合性自检：确认按用户最新指令修改且无额外更改（未通过则带反馈修复再验）──
        if response:
            response, verify_report = await _verify_revision_compliance(
                instruction, current_section_content, response,
                system_prompt, user_prompt,
            )
            verify_note = ""
            if verify_report.get("passed") is True:
                verify_note = ("\n\n（自检通过：已经 "
                               f"{verify_report.get('rounds')} 轮审查确认——修改完整落实了用户指令，"
                               "且无指令之外的额外更改。）")
            elif verify_report.get("passed") is False:
                verify_note = ("\n\n（⚠️ 自检报告：经 "
                               f"{verify_report.get('rounds')} 轮审查修复后仍有以下待确认项——"
                               f"疑似未落实: {verify_report.get('missing_points') or '无'}；"
                               f"疑似额外更改: {verify_report.get('unauthorized_changes') or '无'}。"
                               "回复用户时必须如实说明这些待确认项，由用户决定是否进一步调整。）")
            return (
                f"[已修改: {section_name}]\n\n{response}\n\n"
                "（系统提示：以上修改后全文已保存进文档。回复用户时不要复述全文，"
                "只输出提炼后的修改摘要：逐条列出变更点，整条回复 ≤200 字。）"
                + verify_note
            )
        else:
            return f"[错误] 无法修改「{section_name}」章节。请稍后重试。"

    except asyncio.TimeoutError:
        return f"[错误] 修改「{section_name}」章节超时（180秒）。请稍后重试。"
    except ImportError:
        return f"[错误] 修订服务暂时不可用。请稍后重试。"
    except Exception as e:
        return f"[错误] 修订「{section_name}」时发生异常: {str(e)}。请稍后重试。"


async def revise_paragraph(section_name: str, anchor_text: str, instruction: str,
                           doc_type: str = "design_development_plan") -> str:
    """精确修改文档中指定章节的某个段落，不影响其他段落。

    与 revise_section 的区别：revise_section 重写整章，可能意外改动未涉及段落；
    revise_paragraph 只修改锚定文本所在的段落，其余内容逐字保留。

    Args:
        section_name: 章节名称（如"风险管理"、"设计验证"）。
        anchor_text: 用于定位目标段落的锚定文本（段落中的一句特征性原文，10-30字即可）。
                     工具会在章节中搜索包含此文本的段落，仅修改该段落。
        instruction: 修改指令，如"将风险等级从B改为C"、"增加EO灭菌的验证要求"。
        doc_type: 文档类型标识，从当前会话状态的 doc_type 字段获取。

    Returns:
        修改后的完整章节内容（仅目标段落被修改，其余不变）。
    """
    try:
        from app.services.minimax import _call_minimax_api_raw
        from app.services.doc_types import DOC_TYPE_LABELS
        from app.services.prompt_engineer import DOC_TYPE_SPECIFIC_PROMPTS

        doc_label = DOC_TYPE_LABELS.get(doc_type, "设计策划文档")
        expert_prompt = DOC_TYPE_SPECIFIC_PROMPTS.get(doc_type, "")
        expert_section = f"\n\n{expert_prompt}" if expert_prompt else ""

        # ── 获取当前章节完整内容 ──
        current_section_content = ""
        current_markdown = _current_generated_markdown.get()
        if current_markdown:
            import re
            pattern = rf'^## \s*{re.escape(section_name)}\s*$'
            lines = current_markdown.split('\n')
            in_section = False
            section_lines = []
            for line in lines:
                if re.match(pattern, line.strip()):
                    in_section = True
                    section_lines.append(line)
                elif in_section and re.match(r'^## ', line.strip()):
                    break
                elif in_section:
                    section_lines.append(line)
            if section_lines:
                current_section_content = '\n'.join(section_lines)

        if not current_section_content:
            return f"[错误] 未找到章节「{section_name}」的内容。请确认章节名称是否正确，或先生成该章节。"

        # ── 定位目标段落 ──
        # 按空行分割段落（保留标题行和子标题）
        paragraphs = re.split(r'\n\n+', current_section_content)
        target_idx = -1
        for i, para in enumerate(paragraphs):
            if anchor_text.strip() in para:
                target_idx = i
                break

        if target_idx == -1:
            # 模糊匹配：尝试部分匹配
            anchor_chars = anchor_text.strip()
            for i, para in enumerate(paragraphs):
                # 检查是否有 70% 以上的字符重叠
                para_clean = para.replace('\n', ' ').replace('  ', ' ')
                common = sum(1 for c in anchor_chars if c in para_clean)
                if len(anchor_chars) > 0 and common / len(anchor_chars) > 0.6:
                    target_idx = i
                    break

        if target_idx == -1:
            return (
                f"[错误] 在章节「{section_name}」中未找到包含「{anchor_text}」的段落。"
                f"请提供段落中更准确的特征文本（10-30字即可），或改用 revise_section 修改整章。"
            )

        target_paragraph = paragraphs[target_idx]

        # ── 构建上下文（前后各一段，给 LLM 提供上下文）──
        context_before = paragraphs[target_idx - 1] if target_idx > 0 else ""
        context_after = paragraphs[target_idx + 1] if target_idx < len(paragraphs) - 1 else ""

        # 全文整体风格参照：让修改后的段落措辞/详略与全文既有风格保持一致
        style_reference = _build_style_reference(section_name)
        style_ref_block = f"{style_reference}\n\n" if style_reference else ""

        # ── 构建精准修订 prompt ──
        system_prompt = f"""你是一位贴敷式胰岛素泵RA文档专家。用户要求修改《{doc_label}》文档中「{section_name}」章节的某一个段落。{expert_section}

要求:
- 只修改目标段落，严格保持其他内容不变
- 修改后段落的格式（标题层级、列表、表格等）与原文一致
- 内容专业、具体，符合NMPA注册申报要求
- 技术参数要具体、可测量
- 用中文表述（标准号除外）
- 修改后段落的措辞语气、详略程度与全文其他章节保持一致

{style_ref_block}输出格式:
只输出修改后的段落文本，不要输出章节标题、不要输出其他段落、不要加"修改摘要"等额外说明。{_supplementary_block()}{_memory_context_block()}{_attachment_priority_rule()}{_grounding_rule()}{_doc_scope_rule(doc_type)}{_user_requirements_block(instruction)}{_PRODUCT_PREMISE_RULE}"""

        user_prompt = f"""## 修改指令
{instruction}

## 目标段落（需要修改的段落）
{target_paragraph}

## 上下文（仅用于理解，不要修改）
前一段: {context_before if context_before else "(无，这是章节开头)"}
后一段: {context_after if context_after else "(无，这是章节末尾)"}

请只输出修改后的目标段落文本："""

        # 附件参考（有附件时注入——段落修改的事实依据，防幻觉）
        try:
            assigned_context = _assigned_attachment_block(section_name)
            if assigned_context:
                user_prompt += (
                    f"\n\n# 附件分配内容（最高优先参考——已通读全部上传附件并判定与本章相关，"
                    f"其中的参数、数据、条款与表述必须优先采用）:\n{assigned_context}"
                )
            att_context = await _attachment_refs_block(
                f"{doc_label} {section_name} {instruction[:100]}", top_k=3, verb="修改"
            )
            if att_context:
                user_prompt += f"\n{att_context}"
        except Exception:
            pass

        response = await asyncio.wait_for(
            _stream_llm_to_sink(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=4096,
            ),
            timeout=120.0,
        )

        if not response:
            return f"[错误] 无法修改段落。请稍后重试。"

        # ── 替换目标段落，组装完整章节 ──
        modified_paragraph = response.strip()
        paragraphs[target_idx] = modified_paragraph
        modified_section = '\n\n'.join(paragraphs)

        # ── 生成变更摘要 ──
        # 计算差异（简单对比）
        old_preview = target_paragraph[:100].replace('\n', ' ')
        new_preview = modified_paragraph[:100].replace('\n', ' ')
        summary = (
            f"📝 段落修改摘要:\n"
            f"- 章节: {section_name}\n"
            f"- 定位: 第{target_idx + 1}段（共{len(paragraphs)}段）\n"
            f"- 原文开头: {old_preview}...\n"
            f"- 修改后开头: {new_preview}..."
        )

        return (
            f"[已修改段落: {section_name}]\n\n{modified_section}\n\n{summary}\n\n"
            "（系统提示：以上修改后全文已保存进文档。回复用户时不要复述全文，"
            "只输出提炼后的修改摘要：逐条列出变更点，整条回复 ≤200 字。）"
        )

    except asyncio.TimeoutError:
        return f"[错误] 修改段落超时（120秒）。请稍后重试。"
    except ImportError:
        return f"[错误] 修订服务暂时不可用。请稍后重试。"
    except Exception as e:
        return f"[错误] 修订段落时发生异常: {str(e)}。请稍后重试。"


# ═══════════════════════════════════════════════════════
# 多代理协作工具 (Option A: Subagents Pattern)
# 将子代理包装为工具，主代理通过工具调用驱动子代理
# ═══════════════════════════════════════════════════════

# 子代理实例（懒加载）
_outline_agent = None
_chapter_agent = None

# Semaphore 控制并行 LLM 调用数，防止 API 限流
_llm_semaphore = asyncio.Semaphore(4)


def _get_outline_agent():
    global _outline_agent
    if _outline_agent is None:
        from app.services.subagents import create_outline_agent
        _outline_agent = create_outline_agent()
    return _outline_agent


def _get_chapter_agent():
    global _chapter_agent
    if _chapter_agent is None:
        from app.services.subagents import create_chapter_agent
        _chapter_agent = create_chapter_agent()
    return _chapter_agent


def _extract_json(text: str) -> str:
    """从子代理输出中提取 JSON 字符串（去除可能的 markdown 代码块标记）"""
    import re
    text = text.strip()
    # 尝试匹配 ```json ... ``` 包裹
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        return match.group(1).strip()
    # 尝试匹配裸 JSON 对象 { ... }
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return match.group(0).strip()
    return text


@tool
async def design_outline(
    doc_type: str = "design_development_plan",
    product_name: str = "贴敷式胰岛素泵",
    special_requirements: str = "",
) -> str:
    """设计文档框架（章节结构）。

    调用子代理A（框架设计师），生成完整的文档章节大纲，包含每章的标题、描述、小节列表。
    应在以下时机调用:
    - 开始生成新文档前（用户尚未确认框架时）
    - 用户要求调整框架结构时

    Args:
        doc_type: 文档类型标识 (如 "design_development_plan", "risk_management_plan" 等)
        product_name: 产品名称
        special_requirements: 用户对框架的特殊要求（可选），如"增加FDA申报内容"

    Returns:
        JSON字符串，包含完整的章节框架结构，每章有 title, description, subsections 等字段。
        格式: {"doc_title": "...", "chapters": [{"id": 1, "title": "...", ...}]}
    """
    agent = _get_outline_agent()

    # ── 强制前置 RAG 检索 ──
    # 用 LLM 基于产品上下文+章节信息生成针对性查询词，替代硬编码 query
    rag_context = ""
    try:
        queries = await _generate_search_queries(
            chapter_name=f"{doc_type} 章节结构设计",
            intent="查找该文档类型的标准章节结构要求和适用法规",
            num_queries=3,
        )
        if not queries:
            queries = [f"{doc_type} 章节结构 标准要求"]
        merged_results = []
        seen_keys = set()
        for q in queries:
            rag_result = await search_kb.ainvoke({"query": q, "top_k": 15})
            rag_data = json.loads(rag_result)
            if rag_data.get("status") == "ok" and rag_data.get("results"):
                for item in rag_data["results"]:
                    key = item.get("content", "")[:100]
                    if key not in seen_keys:
                        seen_keys.add(key)
                        merged_results.append(item)
        if merged_results:
            rag_parts = [
                f"[参考{i}] 来源: {r['source']} (相关度: {r['score']})\n{r['content']}"
                for i, r in enumerate(merged_results, 1)
            ]
            rag_context = "\n\n".join(rag_parts)
            print(f"[agent_tools] RAG for outline: {len(merged_results)} results (from {len(queries)} queries)")
    except Exception as e:
        print(f"[agent_tools] RAG failed for outline: {e}")

    prompt = f"""请为以下文档设计章节框架:

文档类型: {doc_type}
产品名称: {product_name}"""
    if special_requirements:
        prompt += f"\n特殊要求: {special_requirements}"

    # 固定章节结构注入：软件开发计划类文档的用户指定结构，
    # 一级章节必须严格按 DOC_TYPE_SPECIFIC_PROMPTS 中的【章节结构强制要求】设置
    _FIXED_OUTLINE_DOC_TYPES = (
        "software_development_plan", "software_development_plan_di", "software_architecture_doc",
        "software_requirements_spec",
    )
    if doc_type in _FIXED_OUTLINE_DOC_TYPES:
        from app.services.prompt_engineer import DOC_TYPE_SPECIFIC_PROMPTS
        fixed_prompt = DOC_TYPE_SPECIFIC_PROMPTS.get(doc_type, "")
        if fixed_prompt:
            prompt += (
                f"\n\n{fixed_prompt}\n"
                "设计框架时：章节必须严格按照上述【章节结构强制要求】的清单设置，"
                "不得遗漏任何部分、不得调整顺序；可根据内容体量将各部分分配为若干章节/小节，"
                "在各章节下细化节(L2)/小节(L3)层级。带括号说明的部分（如接口设计、数据库详细设计、"
                "系统安全设计）必须按括号内的子项设置对应小节。"
            )

    # 模板章节结构参考：用户上传模板时，优先参照模板的章节结构设计框架
    templates = _current_templates.get()
    if templates:
        template_outline_parts = []
        for tpl in templates:
            tpl_name = tpl.get("name") or tpl.get("filename", "?")
            tpl_text = tpl.get("full_text", "")
            if tpl_text:
                # 截取前 8000 字符供 LLM 识别章节结构
                template_outline_parts.append(
                    f"### 模板「{tpl_name}」原文（前8000字符，用于识别章节结构）\n{tpl_text[:8000]}"
                )
        if template_outline_parts:
            prompt += "\n\n## 用户上传的模板文档（最高优先级：必须参照其章节结构设计框架）\n"
            prompt += "请仔细分析以下模板的章节标题、层级和小节划分，设计的框架应尽量贴近模板的章节结构。\n\n"
            prompt += "\n\n".join(template_outline_parts)

    if rag_context:
        prompt += f"""

## 知识库参考资料（必须优先依据以下内容设计框架）
{rag_context}"""

    prompt += (
        "\n\n## 章节编号规则（必须遵守）\n"
        "- 章节标题必须形如\"第一章 XXX\"、\"第二章 XXX\"\n"
        "- 章节序号从1开始连续递增，不得重复、不得跳号\n"
        "\n请严格按照 JSON 格式输出，不要包含任何 JSON 之外的解释文字。"
    )

    try:
        async with _llm_semaphore:
            result = await agent.ainvoke({
                "messages": [{"role": "user", "content": prompt}]
            })
        content = result["messages"][-1].content
        content = _extract_json(content)
        return content
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"框架设计失败: {str(e)}",
        }, ensure_ascii=False)


def _find_chapter_subsections(outline_json: str, chapter_name: str) -> list[dict]:
    """从框架JSON中查找指定章节的小节列表（支持4级层级 schema）。

    支持两种 schema:
    - 旧 schema: chapters[].subsections[] (2级，仅 ###)
    - 新 schema: chapters[].sections[].subsections[].sub_subsections[] (4级)

    返回扁平化的 leaf 小节列表，每个元素:
    {
        "title": "X.Y.Z 标题",         # 不含 markdown 标记
        "level": 3 | 4 | 5,              # ### / #### / #####
        "content_points": [...],          # 该小节的要点
        "parent_path": "X > X.Y",         # 父级标题路径（用于上下文）
        "markdown_prefix": "### " | "#### " | "##### ",
    }

    支持模糊匹配：去除"第X章"前缀后比较，也支持章节标题包含关系。
    """
    import re
    if not outline_json or not chapter_name:
        return []
    try:
        data = json.loads(outline_json)
        chapters = data.get("chapters", [])
    except (json.JSONDecodeError, TypeError):
        return []

    # 标准化：去除"第X章"前缀
    name_clean = re.sub(r'^第[一二三四五六七八九十\d]+章\s*', '', chapter_name).strip()

    target_chapter = None
    for ch in chapters:
        title = ch.get("title", "")
        title_clean = re.sub(r'^第[一二三四五六七八九十\d]+章\s*', '', title).strip()
        if (name_clean == title_clean
                or name_clean in title_clean
                or title_clean in name_clean
                or chapter_name == title
                or chapter_name in title
                or title in chapter_name):
            target_chapter = ch
            break

    if not target_chapter:
        return []

    # 收集 leaf 小节
    leaf_subs = []

    def _add_leaf(title: str, level: int, content_points: list, parent_path: str):
        prefix_map = {3: "### ", 4: "#### ", 5: "##### "}
        leaf_subs.append({
            "title": title,
            "level": level,
            "content_points": content_points or [],
            "parent_path": parent_path,
            "markdown_prefix": prefix_map.get(level, "### "),
        })

    # 新 schema: chapters[].sections[].subsections[].sub_subsections[]
    sections = target_chapter.get("sections", [])
    if sections:
        for sec in sections:
            sec_title = sec.get("title", "")
            sec_path = sec_title
            subsects = sec.get("subsections", [])
            for sub in subsects:
                sub_title = sub.get("title", "")
                sub_path = f"{sec_path} > {sub_title}" if sec_path else sub_title
                sub_subsects = sub.get("sub_subsections", [])
                if sub_subsects:
                    # 有子小节，sub 是父级，leaf 在 sub_subsections
                    for ssub in sub_subsects:
                        ssub_title = ssub.get("title", "")
                        ssub_path = f"{sub_path} > {ssub_title}" if sub_path else ssub_title
                        _add_leaf(ssub_title, 5, ssub.get("content_points", []), ssub_path)
                else:
                    # 无子小节，sub 本身就是 leaf (level 4)
                    _add_leaf(sub_title, 4, sub.get("content_points", []), sub_path)
        return leaf_subs

    # 旧 schema: chapters[].subsections[]
    old_subsects = target_chapter.get("subsections", [])
    for sub in old_subsects:
        sub_title = sub.get("title", "")
        _add_leaf(sub_title, 3, sub.get("content_points", []), "")
    return leaf_subs

def _template_body_sample(full_text: str, sample_chars: int = 3000) -> str:
    """从模板全文智能截取正文风格样例。

    直接取前 N 字符拿到的往往是封面/修订记录/目录，无文风代表性。
    策略：跳过前置页（检测"目录/修订/版本记录/审批/分发"等关键词的开头连续块），
    从正文起始处截取；再补一段中段样例，覆盖文档中后部的写作风格。
    """
    import re

    text = full_text or ""
    if len(text) <= sample_chars:
        return text

    # 逐段扫描，跳过开头的前置页段落
    paras = text.split("\n")
    front_matter_keywords = (
        "目录", "修订记录", "修订历史", "版本记录", "版本历史", "更改记录",
        "审批", "审核记录", "分发", "封面", "文件编号", "受控状态",
    )
    body_start = 0
    i = 0
    while i < len(paras):
        line = paras[i].strip()
        # 空行跳过
        if not line:
            i += 1
            continue
        # 疑似目录条目行（标题....页码）
        if re.search(r"\.{4,}\s*\d+\s*$", line):
            i += 1
            body_start = i
            continue
        # 前置区中封面表格常见行（短标签行如"编制："）或关键词行（含"目录/修订记录/文件编号"等）
        if (re.match(r"^(编制|审核|批准|日期|版本|编号)[:：]", line)
                or any(kw in line[:30] for kw in front_matter_keywords)):
            i += 1
            body_start = i
            continue
        # 封面/页眉元素：公司名行（含"公司/Co., Ltd"且较短）——仅在开头连续区视为前置
        if i <= 3 and len(line) <= 40 and ("公司" in line or "Co." in line or "Ltd" in line):
            i += 1
            body_start = i
            continue
        break  # 遇到正文段落，停止

    body_text = "\n".join(paras[body_start:]) if body_start < len(paras) else text
    if len(body_text) <= sample_chars:
        return body_text

    # 正文起取样例 + 中段补样（各一半预算），覆盖前中后文风
    half = sample_chars // 2
    head = body_text[:half]
    mid_start = max(0, (len(body_text) - half) // 2)
    mid = body_text[mid_start:mid_start + half]
    return (
        f"{head}\n\n……（中间内容略）……\n\n{mid}"
    )


def _build_template_style_hint() -> str:
    """从当前模板提取写作风格参考片段，供 write_chapter / generate_section 模仿模板风格。

    优先级：
    1. 模板风格总结（analyze_template_style 提炼的结构化风格描述，每轮同步到
       _current_template_style_summary）——精炼、指导性强，优先使用。
    2. 用户通过「添加模板」上传的模板原文片段（full_text），
       由 _sync_template_context 每轮同步到 _current_templates。
    3. 无用户模板时，验证/测试类文档（报告或方案）回退到内置默认模板
       （见 app.services.default_templates）。
    均无时返回空字符串，此时沿用默认写作风格。
    """
    # 优先：提炼后的风格总结（更精炼，避免把整段模板原文塞进生成 prompt）
    style_summary = (_current_template_style_summary.get() or "").strip()
    if style_summary:
        return (
            "## 模板写作风格（已提炼总结，最高优先级）\n"
            "以下是从用户上传模板中分析提炼出的写作风格总结，"
            "请在满足上述内容与格式要求的前提下，**严格遵循该风格总结**写作：\n"
            f"{style_summary}"
        )

    templates = _current_templates.get()
    if templates:
        samples = []
        for tpl in templates:
            ft = tpl.get("full_text", "")
            if not ft or not ft.strip():
                continue
            fn = tpl.get("filename", "unknown")
            # 智能截取正文风格样例（跳过封面/目录/修订记录等前置页），
            # 兼顾 token 消耗与文风代表性
            samples.append(f"【模板「{fn}」原文样例】\n{_template_body_sample(ft)}")
        if samples:
            joined = "\n\n".join(samples)
            return (
                "## 模板写作风格模仿（最高优先级）\n"
                "用户上传了参考模板，以下是模板的原文片段。"
                "请在满足上述内容与格式要求的前提下，**严格模仿模板的写作风格**：\n"
                "- 句式长短、段落密度、列表项与表格的使用习惯\n"
                "- 措辞语气、术语表达、编号方式\n"
                "- 参数的罗列方式与详略程度\n\n"
                f"{joined}"
            )
        # 用户模板存在但均无文本 → 继续回退到内置默认（如适用）

    # 无用户模板（或用户模板无文本）时：按 doc_type 匹配内置默认模板（报告/方案/风险管理计划）
    from app.services.default_templates import get_default_template_style, get_default_template_label
    doc_type = _current_doc_type.get()
    default_style = get_default_template_style(doc_type)
    if default_style:
        label = get_default_template_label(doc_type)
        return (
            "## 默认模板写作风格参照（内置默认模板）\n"
            f"当前文档类型匹配内置默认模板{label}，且用户未上传自定义模板。"
            f"请以下方{label}原文片段为风格参照，"
            "在满足上述内容与格式要求的前提下，**模仿其写作风格**：\n"
            "- 句式长短、段落密度、列表项与表格的使用习惯\n"
            "- 措辞语气、术语表达、编号方式\n"
            "- 参数的罗列方式与详略程度\n\n"
            f"【默认模板原文样例】\n{default_style}"
        )
    return ""


@tool
async def write_chapter(
    chapter_name: str,
    outline_json: str,
    doc_type: str = "design_development_plan",
) -> str:
    """编写指定章节的完整内容（逐小节生成）。

    从框架中提取本章的小节列表，每个小节独立调用LLM生成内容，
    最后按小节顺序组装为完整章节。

    可并行调用——主代理在一次回复中同时发起多个 write_chapter 调用，
    系统会自动并行执行它们。

    应在以下时机调用:
    - 框架已确认，需要生成某章节内容时
    - 一次可同时对多个章节发起调用（每个章节一次调用）

    Args:
        chapter_name: 章节名称，如 "目的和范围"、"风险管理计划"
        outline_json: 完整的文档框架JSON（由 design_outline 工具生成）。
                      必须包含所有章节信息，让子代理了解全局结构后再写单章。
        doc_type: 文档类型标识

    Returns:
        Markdown格式的章节完整内容，可直接拼接进最终文档。
    """

    # ── 获取 doc_type 的可读标签 ──
    from app.services.minimax import _call_minimax_api_raw
    doc_label = doc_type
    expert_prompt = ""
    try:
        from app.services.doc_types import DOC_TYPE_LABELS
        from app.services.prompt_engineer import DOC_TYPE_SPECIFIC_PROMPTS
        doc_label = DOC_TYPE_LABELS.get(doc_type, doc_type)
        expert_prompt = DOC_TYPE_SPECIFIC_PROMPTS.get(doc_type, "")
    except ImportError:
        pass
    expert_section = f"\n\n{expert_prompt}" if expert_prompt else ""

    # 已覆盖内容摘要（排除本章），注入每个小节提示词避免跨章节内容重复
    covered_digest = _build_covered_digest(chapter_name)
    covered_block = f"- 已覆盖内容（请勿重复，引用用\"详见第X章\"）:\n{covered_digest}" if covered_digest else ""

    # 模板写作风格参考：用户上传模板时注入，让章节模仿模板风格而非默认风格
    template_style_block = _build_template_style_hint()
    style_section = f"{template_style_block}\n\n" if template_style_block else ""
    # 用户模板在场时，默认风格段让位（两者叠加会互相矛盾，如模板长段落 vs 默认"禁止长段落"）
    has_user_template = bool(_current_templates.get()) and "模板写作风格模仿" in template_style_block

    # 全文整体风格参照：从已生成章节提取结构概览 + 文风范本，让新章节与全文风格一致
    style_reference = _build_style_reference(chapter_name)
    style_ref_block = f"{style_reference}\n\n" if style_reference else ""

    # 轻量去重: 对同一小节的检索结果做 Jaccard 相似度去重
    def _dedup_results(results: list, threshold: float = 0.6) -> list:
        if len(results) <= 1:
            return results
        kept = []
        for r in results:
            dup = False
            r_words = set(r.get("content", "")[:200].split())
            if not r_words:
                kept.append(r)
                continue
            for k in kept:
                k_words = set(k.get("content", "")[:200].split())
                if not k_words:
                    continue
                intersection = len(r_words & k_words)
                union = len(r_words | k_words)
                jaccard = intersection / union if union > 0 else 0
                if jaccard > threshold:
                    dup = True
                    break
            if not dup:
                kept.append(r)
        return kept

    # ── 强制前置 RAG 检索（逐小节粒度）──
    # 从框架中提取本章的小节列表，每个小节单独检索
    subsections = _find_chapter_subsections(outline_json, chapter_name)
    sub_rag_map = {}  # sub_title -> rag_context_string

    # ── 附件→章节预分配映射（懒加载）──
    # 首次调用时 LLM 通读全部附件并分配块到章节（随 state 持久化），
    # 后续章节直接复用；outline/附件集合变化时自动重建
    try:
        await _get_or_build_attachment_map(outline_json)
    except Exception as e:
        print(f"[agent_tools] 附件映射构建失败（降级为关键词检索）: {e}")

    # ── 模板贴近增强（懒加载）──
    # ① 风格总结：主 agent 未调 analyze_template_style 时自动补齐，保证
    #    _build_template_style_hint 始终有提炼总结可用（不再依赖 LLM 自觉）
    # ② 分节对位映射：LLM 通读模板，为本章找到模板中最值得参照的节
    try:
        if _current_templates.get() and not (_current_template_style_summary.get() or "").strip():
            style_summary = await _analyze_template_style_core()
            if style_summary:
                _current_template_style_summary.set(style_summary)
                _pending_template_style_summary["summary"] = style_summary
                print(f"[agent_tools] 模板风格总结已懒加载 ({len(style_summary)} chars)")
    except Exception as e:
        print(f"[agent_tools] 模板风格总结懒加载失败（降级原文样例）: {e}")
    try:
        await _get_or_build_template_map(outline_json)
    except Exception as e:
        print(f"[agent_tools] 模板对位映射构建失败（降级全局风格）: {e}")

    if subsections:
        _rag_sem = asyncio.Semaphore(6)
        async def _search_subsection(sub: dict):
            sub_title = sub.get("title", "")
            content_points = sub.get("content_points", [])
            # 用 LLM 基于产品上下文+章节信息生成针对性查询词（替代硬编码拼接）
            queries = await _generate_search_queries(
                chapter_name=chapter_name,
                sub_title=sub_title,
                content_points=content_points,
                num_queries=3,
            )
            if not queries:
                # 回退到简单拼接
                fallback = " ".join(filter(None, [doc_type, chapter_name, sub_title]))
                if content_points:
                    fallback += " " + " ".join(content_points[:3])
                queries = [fallback] if fallback else []

            # 对每条查询词调用 search_kb，合并去重结果
            merged_results = []
            seen_sources = set()
            try:
                async with _rag_sem:
                    for q in queries:
                        r = await search_kb.ainvoke({"query": q, "top_k": 15})
                        data = json.loads(r)
                        if data.get("status") == "ok" and data.get("results"):
                            for item in data["results"]:
                                # 按内容前100字符去重
                                key = item.get("content", "")[:100]
                                if key not in seen_sources:
                                    seen_sources.add(key)
                                    merged_results.append(item)
            except Exception:
                pass

            # 附件检索：用户上传附件内容为最高优先参考资料（参数/数据/条款优先采用）。
            # 检索词用章节+小节+内容要点（关键词检索口径），不与 KB 结果互相去重。
            att_terms = [t for t in (chapter_name, sub_title) if t]
            if content_points:
                att_terms.extend(content_points[:2])
            att_results = await _retrieve_attachment_refs(" ".join(att_terms), top_k=5)

            return (sub_title, merged_results, att_results)

        tasks = [asyncio.create_task(_search_subsection(s)) for s in subsections]
        await asyncio.gather(*tasks)

        for task in tasks:
            sub_title, results, att_results = task.result()
            lines = [f"### 小节「{sub_title}」参考资料:"]
            # 附件命中置于知识库结果之前（最高优先）
            if att_results:
                for j, r in enumerate(att_results, 1):
                    lines.append(
                        f"  [附件·最高优先] {r.get('source')} (相关度:{r.get('score')})\n  {r.get('content')}"
                    )
            if results:
                results = _dedup_results(results)
                for j, r in enumerate(results, 1):
                    lines.append(
                        f"  [源] {r['source']} (相关度:{r['score']})\n  {r['content']}"
                    )
            if len(lines) > 1:
                sub_rag_map[sub_title] = "\n".join(lines)
            else:
                sub_rag_map[sub_title] = ""

        rag_hit_count = sum(1 for v in sub_rag_map.values() if v)
        print(f"[agent_tools] Subsection RAG for '{chapter_name}': "
              f"{rag_hit_count}/{len(subsections)} subsections matched")

        # ── 逐小节生成内容 ──
        async def _gen_subsection(sub: dict) -> tuple:
            sub_title = sub.get("title", "")
            content_points = sub.get("content_points", [])
            rag = sub_rag_map.get(sub_title, "")

            points_hint = ""
            if content_points:
                points_hint = "\n请重点覆盖以下内容要点:\n" + "\n".join(
                    f"- {p}" for p in content_points
                )

            parent_path = sub.get("parent_path", "")
            level = sub.get("level", 3)
            markdown_prefix = sub.get("markdown_prefix", "### ")

            context_hint = ""
            if parent_path:
                context_hint = f"（层级位置：{parent_path}）"

            if has_user_template:
                style_rules = (
                    f"## 写作风格（以用户模板风格为准，最高优先级）\n"
                    f"用户上传了参考模板，**严格模仿模板的写作风格**（句式长短、段落密度、"
                    f"列表/表格使用习惯、措辞语气、术语表达、详略程度），"
                    f"模板是长段落就写长段落，模板是短句列表就写短句列表，"
                    f"不受任何默认文风约束。\n"
                    f"\n"
                    f"要求:\n"
                    f"{_regulation_clause_rule(doc_type)}"
                    f"- 技术参数要具体、可测量、有明确的数值范围\n"
                    f"- 表格要填写完整，不能留\"(描述)\"或\"待填写\"等占位符\n"
                    f"{_TABLE_FORMAT_RULE}{_NO_PERSON_NAME_RULE}"
                    f"- 针对贴敷式胰岛素泵产品特性编写{_PRODUCT_PREMISE_RULE}"
                    f"- 用中文表述 (标准号和必要缩写除外)\n"
                    f"- 只生成本小节正文，不要添加章节标题（如 ## 或 ###）\n"
                    f"\n"
                    f"## 去重要求（避免跨章节内容重复）\n"
                    f"- 产品通用参数（尺寸、储药量、输注精度、BLE、IPX8、灭菌方式、Class C等）"
                    f"只在最相关章节写全，其他章节引用时用\"见第X章\"简述，不重复罗列\n"
                    f"- 标准总则类描述（\"本部分适用于…\"\"本标准规定…\"）全文档只出现一次\n"
                    f"- 同一法规条款仅在与本节直接相关处展开，不在多节重复相同说明\n"
                )
                tail_rules = (
                    f"{covered_block}\n"
                    f"{style_ref_block}"
                    f"{style_section}"
                )
            else:
                style_rules = (
                    f"## 写作风格（参考《产品技术要求》和《软件需求规范》：精简+短句）\n"
                    f"\n"
                    f"要求:\n"
                    f"- **每个要点 1-3 句话，单句 30-80 字，绝对不写长段落**\n"
                    f"- 大量使用 `- 项目符号` 列表项表达并列规则/参数\n"
                    f"- 每个要点风格如 \"支持X功能\"/\"参数：Y\"/\"协议：Z\"\n"
                    f"- 涉及多个数值参数时用小表格呈现（2-10 行 × 2-6 列），不要写大表格\n"
                    f"{_regulation_clause_rule(doc_type)}"
                    f"- 技术参数要具体、可测量、有明确的数值范围\n"
                    f"- 表格要填写完整，不能留\"(描述)\"或\"待填写\"等占位符\n"
                    f"{_TABLE_FORMAT_RULE}{_NO_PERSON_NAME_RULE}"
                    f"- 针对贴敷式胰岛素泵产品特性编写{_PRODUCT_PREMISE_RULE}"
                    f"- 用中文表述 (标准号和必要缩写除外)\n"
                    f"- 只生成本小节正文，不要添加章节标题（如 ## 或 ###）\n"
                    f"\n"
                    f"## 禁止事项\n"
                    f"- **禁止写概述段、引入段、铺垫段**\n"
                    f"- **禁止写总结段、归纳段、结尾段**\n"
                    f"- **禁止写\"本小节将介绍...\"/\"综上所述...\"等过渡句**\n"
                    f"- **禁止把同一要点展开成完整段落**\n"
                    f"- **禁止以\"本章依据XX标准编制\"/\"本节依据...\"等冗余前缀行开头**\n"
                    f"\n"
                    f"## 去重要求（避免跨章节内容重复）\n"
                    f"- 产品通用参数（尺寸、储药量、输注精度、BLE、IPX8、灭菌方式、Class C等）"
                    f"只在最相关章节写全，其他章节引用时用\"见第X章\"简述，不重复罗列\n"
                    f"- 标准总则类描述（\"本部分适用于…\"\"本标准规定…\"）全文档只出现一次\n"
                    f"- 同一法规条款仅在与本节直接相关处展开，不在多节重复相同说明\n"
                )
                tail_rules = (
                    f"{covered_block}\n"
                    f"{style_ref_block}"
                    f"{style_section}"
                    f"\n"
                    f"## 输出结构示例（参考《产品技术要求》风格）\n"
                    f"直接写要点/列表/小表格，第一行就是实质内容（不是标题）。\n"
                    f"\n"
                    f"## 字数约束\n"
                    f"本小节总字数控制在 200-500 字之间。**宁少勿多**。"
                )

            system_prompt = (
                f"你是一位贴敷式胰岛素泵RA文档专家。"
                f"请编写《{doc_label}》文档中「{chapter_name}」章节下「{sub_title}」小节的内容{context_hint}。"
                f"{expert_section}\n\n"
                f"{style_rules}"
                f"{tail_rules}"
                f"{_supplementary_block()}"
                f"{_memory_context_block()}"
                f"{_attachment_priority_rule()}"
                f"{_grounding_rule()}"
                f"{_doc_scope_rule(doc_type)}"
                f"{_user_requirements_block()}"
            )

            user_prompt = (
                f"请编写「{chapter_name}」->「{sub_title}」小节的内容。"
                f"{points_hint}\n\n"
                f"文档框架参考:\n{outline_json}"
            )

            # 附件分配内容（预分配映射，最高优先参考——LLM 已通读全部附件并判定与本章相关）
            assigned = _assigned_attachment_block(chapter_name, sub_title)
            if assigned:
                user_prompt += (
                    f"\n\n# 附件分配内容（最高优先参考——已通读全部上传附件并判定与本章/本小节相关，"
                    f"其中的参数、数据、条款与表述必须优先采用）:\n{assigned}"
                )

            # 模板对应节样例（分节对位参照——本章参照模板对应节的写法）
            tmpl_sample = _assigned_template_block(chapter_name)
            if tmpl_sample:
                user_prompt += (
                    f"\n\n# 模板对应节样例（写法参照——本章的结构组织、编号方式、句式与表格用法"
                    f"优先模仿此样例的写法；但内容仍按本框架与上述参考资料编写，"
                    f"不要照抄样例中的具体内容）:\n{tmpl_sample}"
                )

            if rag:
                user_prompt += (
                    f"\n\n参考资料（必须优先依据以下内容编写；[附件·最高优先] 为用户上传文档原文，"
                    f"其中的参数、数据、条款与表述必须优先采用）:\n{rag}"
                )

            try:
                async with _llm_semaphore:
                    response = await asyncio.wait_for(
                        _stream_llm_to_sink(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            temperature=0.3,
                            max_tokens=2048,
                        ),
                        timeout=300.0,
                    )
                if response:
                    return (sub_title, markdown_prefix, response)
                else:
                    return (sub_title, markdown_prefix, "[错误] 无法生成小节内容。")
            except asyncio.TimeoutError:
                return (sub_title, markdown_prefix, "[错误] 生成小节超时（300秒）。")
            except Exception as e:
                return (sub_title, markdown_prefix, f"[错误] 生成小节异常: {str(e)}")

        gen_tasks = [asyncio.create_task(_gen_subsection(s)) for s in subsections]
        await asyncio.gather(*gen_tasks)

        # 组装章节完整内容（按 level 使用 ### / #### / #####）
        parts = [f"## {chapter_name}\n\n"]
        for task in gen_tasks:
            sub_title, markdown_prefix, content = task.result()
            parts.append(f"{markdown_prefix}{sub_title}\n\n{content}\n\n")
        full_content = "".join(parts)

        # 统计小节生成结果
        success_count = sum(1 for t in gen_tasks if not str(t.result()[1]).startswith("[错误]"))
        subsection_names = [s.get("title", "") for s in subsections]

        # 完整内容通过 contextvar 旁路传给 _after_tools_node，
        # 工具返回值只包含简短摘要，避免大段内容进入 LLM 对话历史
        _pending_chapter_contents[chapter_name] = full_content

        print(f"[agent_tools] write_chapter '{chapter_name}': "
              f"{success_count}/{len(subsections)} subsections generated")
        return json.dumps({
            "status": "ok",
            "chapter_name": chapter_name,
            "subsections_count": len(subsections),
            "success_count": success_count,
            "subsections": subsection_names,
            "preview": full_content[:300] + ("..." if len(full_content) > 300 else ""),
        }, ensure_ascii=False)

    else:
        # ── 回退：框架无小节信息时，整体生成章节 ──
        # 用 LLM 生成针对性查询词，替代硬编码 query
        rag_context = ""
        try:
            queries = await _generate_search_queries(
                chapter_name=chapter_name,
                intent=f"查找 {doc_type} 文档中 {chapter_name} 章节的标准要求和法规依据",
                num_queries=3,
            )
            if not queries:
                queries = [f"{doc_type} {chapter_name}"]
            merged_results = []
            seen_keys = set()
            for q in queries:
                rag_result = await search_kb.ainvoke({"query": q, "top_k": 15})
                rag_data = json.loads(rag_result)
                if rag_data.get("status") == "ok" and rag_data.get("results"):
                    for item in rag_data["results"]:
                        key = item.get("content", "")[:100]
                        if key not in seen_keys:
                            seen_keys.add(key)
                            merged_results.append(item)
            if merged_results:
                rag_parts = [
                    f"[参考{i}] 来源: {r['source']} (相关度: {r['score']})\n{r['content']}"
                    for i, r in enumerate(merged_results, 1)
                ]
                rag_context = "\n\n".join(rag_parts)
                print(f"[agent_tools] Fallback RAG for '{chapter_name}': "
                      f"{len(merged_results)} results (from {len(queries)} queries)")
        except Exception as e:
            print(f"[agent_tools] RAG failed for '{chapter_name}': {e}")

        if has_user_template:
            fallback_style_rules = (
                f"## 写作风格（以用户模板风格为准，最高优先级）\n"
                f"用户上传了参考模板，**严格模仿模板的写作风格**（句式长短、段落密度、"
                f"列表/表格使用习惯、措辞语气、术语表达、详略程度），"
                f"模板是长段落就写长段落，模板是短句列表就写短句列表，"
                f"不受任何默认文风约束。\n"
                f"\n"
                f"要求:\n"
                f"- 使用 4 级层级 Markdown: ## (章) -> ### (节) -> #### (小节) -> ##### (子小节)\n"
                f"{_regulation_clause_rule(doc_type)}"
                f"- 技术参数要具体、可测量、有明确的数值范围\n"
                f"- 表格要填写完整，不能留\"(描述)\"或\"待填写\"等占位符\n"
                f"{_TABLE_FORMAT_RULE}{_NO_PERSON_NAME_RULE}"
                f"- 针对贴敷式胰岛素泵产品特性编写{_PRODUCT_PREMISE_RULE}"
                f"- 用中文表述 (标准号和必要缩写除外)\n"
                f"\n"
            )
        else:
            fallback_style_rules = (
                f"## 写作风格（参考《产品技术要求》和《软件需求规范》：精简+短句+多层结构）\n"
                f"\n"
                f"要求:\n"
                f"- **每个要点 1-3 句话，单句 30-80 字，绝对不写长段落**\n"
                f"- 大量使用 `- 项目符号` 列表项表达并列规则/参数\n"
                f"- 每个要点风格如 \"支持X功能\"/\"参数：Y\"/\"协议：Z\"\n"
                f"- 涉及多个数值参数时用小表格呈现（2-10 行 × 2-6 列）\n"
                f"- 使用 4 级层级 Markdown: ## (章) -> ### (节) -> #### (小节) -> ##### (子小节)\n"
                f"{_regulation_clause_rule(doc_type)}"
                f"- 技术参数要具体、可测量、有明确的数值范围\n"
                f"- 表格要填写完整，不能留\"(描述)\"或\"待填写\"等占位符\n"
                f"{_TABLE_FORMAT_RULE}{_NO_PERSON_NAME_RULE}"
                f"- 针对贴敷式胰岛素泵产品特性编写{_PRODUCT_PREMISE_RULE}"
                f"- 用中文表述 (标准号和必要缩写除外)\n"
                f"\n"
                f"## 禁止事项\n"
                f"- **禁止写概述段、引入段、铺垫段**\n"
                f"- **禁止写总结段、归纳段、结尾段**\n"
                f"- **禁止把同一要点展开成完整段落**\n"
                f"\n"
            )

        system_prompt = (
            f"你是一位贴敷式胰岛素泵RA文档专家。"
            f"请编写《{doc_label}》文档中「{chapter_name}」章节的完整内容。"
            f"{expert_section}\n\n"
            f"{fallback_style_rules}"
            f"{style_ref_block}"
            f"{style_section}"
            f"## 字数约束\n"
            f"整章总字数控制在 800-2000 字之间。**宁少勿多**。"
            f"{_supplementary_block()}"
            f"{_memory_context_block()}"
            f"{_attachment_priority_rule()}"
            f"{_grounding_rule()}"
            f"{_doc_scope_rule(doc_type)}"
            f"{_user_requirements_block()}"
        )

        user_prompt = (
            f"请编写「{chapter_name}」章节的完整内容。\n\n"
            f"文档框架:\n{outline_json}"
        )

        if rag_context:
            user_prompt += f"\n\n知识库参考资料:\n{rag_context}"

        user_prompt += (
            f"\n\n注意:\n"
            f"- 只输出本章内容，不要输出其他章节\n"
            f"- 第一行以 `## {chapter_name}` 开头"
        )

        try:
            async with _llm_semaphore:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        _call_minimax_api_raw,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=0.3,
                        max_tokens=4096,
                    ),
                    timeout=300.0,
                )
            if response:
                # 完整内容通过 dict 旁路传递，返回值仅含摘要
                _pending_chapter_contents[chapter_name] = response
                return json.dumps({
                    "status": "ok",
                    "chapter_name": chapter_name,
                    "subsections_count": 0,
                    "success_count": 1,
                    "subsections": [],
                    "preview": response[:300] + ("..." if len(response) > 300 else ""),
                }, ensure_ascii=False)
            else:
                return f"[错误] 章节「{chapter_name}」编写失败: API 返回空结果。"
        except asyncio.TimeoutError:
            return f"[错误] 章节「{chapter_name}」编写超时（300秒）。"
        except Exception as e:
            return f"[错误] 章节「{chapter_name}」编写失败: {str(e)}。请重试。"


@tool
async def update_outline(
    outline_json: str,
    instruction: str,
) -> str:
    """根据用户指令修改文档框架。

    当用户要求调整章节结构（增删章节、调整顺序、修改标题）时调用。
    如果修改幅度很小（如仅改一个章节标题），主代理可以直接修改JSON，
    不需要调用此工具。

    Args:
        outline_json: 当前完整的文档框架JSON
        instruction: 用户的修改指令，如"删除第3章，将第5章移到第2章"

    Returns:
        修改后的完整框架JSON
    """
    agent = _get_outline_agent()

    prompt = f"""当前框架如下:
```json
{outline_json}
```

用户要求: {instruction}

请输出修改后的完整 JSON 框架。保持一样的格式和字段，只修改用户要求的部分。

## 章节编号规则（必须遵守）
- 章节标题序号必须连续递增（"第一章"→"第二章"→...），不得重复、不得跳号
- 新增章节的序号必须接在现有最大章节序号之后（顺延），例如现有最后一章为"第六章"时，新增章节应为"第七章"
- 删除或插入章节后，必须对后续章节重新连续编号

只输出 JSON，不要包含其他文字。"""

    try:
        async with _llm_semaphore:
            result = await agent.ainvoke({
                "messages": [{"role": "user", "content": prompt}]
            })
        content = result["messages"][-1].content
        content = _extract_json(content)
        return content
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"框架更新失败: {str(e)}",
        }, ensure_ascii=False)


# ── Tool 6b: summarize_section ──
# 小节精简工具：对已生成章节中的每个 ### 小节内容做 LLM 精简，
# 用精简后内容替换原小节。支持字数模式（按原字数比例分配预算）和比例模式。
# 完整内容通过 _pending_chapter_contents 旁路传递，避免大段内容进入 LLM 对话历史。

# 摘要子代理实例（懒加载）
_summary_agent = None


def _get_summary_agent():
    """懒加载摘要子代理实例"""
    global _summary_agent
    if _summary_agent is None:
        from app.services.subagents import create_summary_agent
        _summary_agent = create_summary_agent()
    return _summary_agent


def _split_chapter_into_subsections(chapter_content: str) -> list[dict]:
    """将章节内容按 ### / #### / ##### 小节拆分（支持4级层级）

    Args:
        chapter_content: 章节完整内容，以 `## {章节名}` 开头

    Returns:
        list of {"header": "## 章节名", "subsections": [{"title": "### 小节标题", "body": "小节正文"}]}
        每遇到 ### / #### / ##### 开头的行即开启一个新小节（保持向后兼容：
        仅含 ### 的旧文档行为不变；含 #### / ##### 的新4级结构会被拆分为更细粒度小节）
        若无任何小节标题，subsections 为空列表（调用方应走整章节精简回退路径）
    """
    if not chapter_content:
        return [{"header": "", "subsections": []}]

    lines = chapter_content.split("\n")
    header_lines = []      # ## 章节标题及其后的空行
    subsections = []

    # 提取章节标题（## 开头）部分
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            # 章节标题行
            header_lines.append(line)
            i += 1
            # 收集章节标题后的空行（直到第一个 ### / #### / ##### 或正文开始）
            while i < len(lines):
                s = lines[i].strip()
                if s == "":
                    header_lines.append(lines[i])
                    i += 1
                elif s.startswith("### ") or s.startswith("#### ") or s.startswith("##### "):
                    break
                else:
                    # 章节标题后直接是正文（无小节），整体作为单一小节
                    break
            break
        else:
            # 非 ## 开头（异常情况），作为 header 保留
            header_lines.append(line)
            i += 1

    # 收集 ### / #### / ##### 小节
    body_lines = lines[i:]
    current_title = None
    current_body = []

    for line in body_lines:
        stripped = line.strip()
        is_subsection_heading = (
            stripped.startswith("### ")
            or stripped.startswith("#### ")
            or stripped.startswith("##### ")
        )

        if is_subsection_heading:
            # 新小节开始，保存前一小节
            if current_title is not None:
                subsections.append({
                    "title": current_title,
                    "body": "\n".join(current_body).strip(),
                })
            current_title = stripped
            current_body = []
        else:
            if current_title is not None:
                current_body.append(line)
            else:
                # ### 之前的非空行（已在 header 收集过空行），忽略
                pass

    # 收集最后一个小节
    if current_title is not None:
        subsections.append({
            "title": current_title,
            "body": "\n".join(current_body).strip(),
        })

    return [{
        "header": "\n".join(header_lines).rstrip(),
        "subsections": subsections,
    }]


def _count_chinese_chars(text: str) -> int:
    """统计有效字符数（中文+英文字符，排除空白和markdown标记）

    用于估算小节内容长度，作为字数预算分配依据。
    """
    if not text:
        return 0
    import re
    # 去除 markdown 标记符号和空白
    cleaned = re.sub(r'[#*_`>\-\[\]\(\)\|]', '', text)
    cleaned = re.sub(r'\s+', '', cleaned)
    return len(cleaned)


def _validate_readability(text: str, orig_text: str = "") -> dict:
    """校验精简后文本的可读性与语义完整性。

    保守检测精简过程中常见的可读性问题，返回问题列表供 LLM 修复参考。
    只标记明确的违规模式，避免误报。

    Args:
        text: 精简后的文本
        orig_text: 原始文本（用于引用有效性校验，可选）

    Returns:
        {"is_valid": bool, "issues": [str]} - is_valid 为 True 表示通过校验
    """
    import re

    if not text or not text.strip():
        return {"is_valid": False, "issues": ["精简后内容为空"]}

    issues = []
    cleaned = text.strip()

    # 1. 残句结尾：以逗号/顿号/分号等收尾，说明被截断
    bad_end_punct = ('，', '、', '；', ',', ';', '：', ':')
    # 去除末尾的空白和 markdown 标记后再判断
    stripped_end = cleaned.rstrip()
    while stripped_end and stripped_end[-1] in (' ', '\n', '\t'):
        stripped_end = stripped_end.rstrip()
    if stripped_end and stripped_end[-1] in bad_end_punct:
        issues.append(f"末尾以标点'{stripped_end[-1]}'收尾，疑似残句被截断")

    # 2. 残句结尾：以连词/介词收尾（"和/或/与/而/则"等），后无内容
    if stripped_end:
        last_char = stripped_end[-1]
        if last_char in ('和', '或', '与', '而', '则', '把', '被', '将', '由'):
            issues.append(f"末尾以连词/介词'{last_char}'收尾，疑似残句")

    # 3. 残句开头：以结论词开头但主句过短
    first_line = cleaned.split('\n', 1)[0].lstrip('#-*>` \t')
    bad_start_words = ('因此', '综上', '所以', '从而', '可见', '由此')
    for bw in bad_start_words:
        if first_line.startswith(bw):
            # 若结论词后没有完整主句（去除标点后少于 4 字），标记为残句
            rest = first_line[len(bw):]
            rest_content = re.sub(r'[。！？，、；：,.!?;:\s]', '', rest)
            if len(rest_content) < 4:
                issues.append(f"开头以'{bw}'起始但主句不完整，疑似残句")
            break

    # 4. 悬空引用：引用对象（表/图/章节）在精简结果中找不到
    # 移除引用本身后再检查 ref_id 是否仍存在，避免引用自身导致误判
    ref_checks = [
        (r'如\s*表\s*([\d\-\.]+)\s*所示', '表', 'table'),
        (r'见\s*表\s*([\d\-\.]+)', '表', 'table'),
        (r'见\s*图\s*([\d\-\.]+)', '图', 'figure'),
        (r'参见\s*§\s*([\d\.]+)', '章节', 'section'),
        (r'见\s*§\s*([\d\.]+)', '章节', 'section'),
    ]
    has_any_table = '|' in cleaned  # 是否存在任何 markdown 表格
    for pat, label, kind in ref_checks:
        for m in re.finditer(pat, cleaned):
            ref_id = m.group(1)
            full_match = m.group(0).strip()
            # 移除所有匹配的引用后，检查 ref_id 是否仍存在
            text_without_refs = re.sub(pat, '', cleaned)
            if kind == 'table':
                # 表格引用：文本中需要存在 markdown 表格（|）或独立的"表 {id}"标题
                has_ref = has_any_table or (f'表 {ref_id}' in text_without_refs)
                if not has_ref:
                    issues.append(f"引用'{full_match}'在精简结果中找不到对应表格")
            elif kind == 'figure':
                has_ref = (f'图 {ref_id}' in text_without_refs or f'图{ref_id}' in text_without_refs)
                if not has_ref:
                    issues.append(f"引用'{full_match}'在精简结果中找不到对应图")
            elif kind == 'section':
                has_ref = (f'§{ref_id}' in text_without_refs or f'§ {ref_id}' in text_without_refs
                           or ref_id in text_without_refs)
                if not has_ref:
                    issues.append(f"引用'{full_match}'在精简结果中找不到对应章节")

    # 5. 表格完整性：表格列数不一致（跳过分隔行 |---|---|）
    # 分隔行只包含 -、:、|、空白，且至少含一个 - 和一个 |
    def _is_separator_row(s: str) -> bool:
        return bool(re.match(r'^[\s\-:|]+$', s)) and '-' in s and '|' in s

    table_lines = [l for l in cleaned.split('\n')
                   if l.strip().startswith('|') and l.strip().endswith('|')]
    if len(table_lines) >= 2:
        col_counts = set()
        for line in table_lines:
            s = line.strip()
            if _is_separator_row(s):
                continue  # 分隔行
            cols = s.count('|') - 1
            if cols > 0:
                col_counts.add(cols)
        if len(col_counts) > 1:
            issues.append(f"表格列数不一致：{sorted(col_counts)}")

        # 表格缺少表头分隔行：第一行数据行后未紧跟 |---| 分隔行
        first_data_idx = None
        for i, line in enumerate(table_lines):
            if not _is_separator_row(line.strip()):
                first_data_idx = i
                break
        if first_data_idx is not None and first_data_idx + 1 < len(table_lines):
            next_line = table_lines[first_data_idx + 1].strip()
            if not _is_separator_row(next_line):
                issues.append("表格缺少表头分隔行（|---|）")

    # 6. 空列表项：列表符号后无内容
    for line in cleaned.split('\n'):
        s = line.strip()
        if s in ('-', '*') or re.match(r'^[-*]\s*$', s):
            issues.append("存在空列表项（'-' 后无内容）")
            break

    # 7. 表格单元格残句：单元格内文本以连词/助词/逗号等收尾
    # 仅校验表格数据行（跳过分隔行），提取单元格内容并检查末尾字符
    if len(table_lines) >= 2:
        cell_dangling_chars = ('，', '、', '；', ',', ';', '：', ':',
                               '和', '或', '与', '而', '则', '把', '被', '将', '由', '的')
        cell_issues_found = []
        for line in table_lines:
            s = line.strip()
            if _is_separator_row(s):
                continue  # 跳过分隔行
            # 提取单元格内容：去掉首尾 | 后按 | 切分
            inner = s[1:-1] if s.startswith('|') and s.endswith('|') else s
            cells = inner.split('|')
            for cell_idx, cell in enumerate(cells):
                cell_text = cell.strip()
                if not cell_text:
                    continue
                # 去除单元格末尾的 markdown 标记后再判断
                stripped_cell = cell_text.rstrip('*_`~ ')
                if stripped_cell and stripped_cell[-1] in cell_dangling_chars:
                    cell_issues_found.append(
                        f"表格单元格'{stripped_cell[:12]}...'以'{stripped_cell[-1]}'收尾，疑似残句")
                    break  # 每行只报一次，避免噪音
            if cell_issues_found:
                break  # 整体只报一次，避免噪音
        if cell_issues_found:
            issues.append(cell_issues_found[0])

    # 8. 表格上下文衔接：表格前应有引出句或表号标注（保守校验）
    # 仅当表格前 2 行内无任何引出词/表号时才标记，避免误报
    # 例外：表格在小节正文起始位置（tstart==0）时，### 小节标题已提供上下文，不标记
    if len(table_lines) >= 2:
        # 找到表格块在原文中的起始位置
        lines_all = cleaned.split('\n')
        table_start_indices = []
        for i, line in enumerate(lines_all):
            s = line.strip()
            if s.startswith('|') and s.endswith('|') and not _is_separator_row(s):
                # 检查是否是表格块的第一行（前一行不是表格行）
                if i == 0 or not (lines_all[i-1].strip().startswith('|')
                                  and lines_all[i-1].strip().endswith('|')):
                    table_start_indices.append(i)

        intro_patterns = [
            r'如下表', r'如下所示', r'见下表', r'如表所示', r'详见下表',
            r'如下表所示', r'如表\s*[\d\-\.]+', r'表\s*\d', r'下表\s*列',
            r'下表\s*给', r'下表\s*展', r'下表\s*汇总',
        ]
        for tstart in table_start_indices:
            # 表格在小节正文起始位置，### 小节标题已提供上下文，跳过
            if tstart == 0:
                continue
            # 检查表格前 2 行（含表格首行）是否有引出词或表号
            has_intro = False
            check_start = max(0, tstart - 2)
            for j in range(check_start, tstart + 1):
                if re.search('|'.join(intro_patterns), lines_all[j]):
                    has_intro = True
                    break
            if not has_intro:
                issues.append("表格缺少引出上下文（表格前应有引出句或表号标注）")
                break  # 整体只报一次

    return {"is_valid": len(issues) == 0, "issues": issues}


def _extract_mermaid_blocks(text: str) -> list:
    """提取文本中的 mermaid 流程图代码块（```mermaid ... ```）。"""
    import re as _re
    return _re.findall(r"```mermaid.*?```", text or "", _re.S)


def _ensure_mermaid_preserved(original: str, condensed: str) -> str:
    """流程图保护硬保障：精简结果若丢失原文中的 mermaid 块，追加回缺失的块。

    提示词已要求保留流程图，但 LLM 偶发不遵守（精简时丢代码块常见），
    此处在返回前做代码级校验兜底。
    """
    missing = [b for b in _extract_mermaid_blocks(original)
               if b not in (condensed or "")]
    if not missing:
        return condensed
    restored = (condensed or "").rstrip() + "\n\n" + "\n\n".join(missing)
    print(f"[condense] 已恢复被精简丢失的 {len(missing)} 个流程图块")
    return restored


async def _summarize_one_subsection(
    sub_title: str,
    sub_body: str,
    target_chars: int,
    chapter_name: str,
    doc_label: str,
    is_ratio_mode: bool = False,
    aggressive: bool = False,
) -> tuple[str, str, dict]:
    """对单个小节调用 LLM 精简

    Args:
        sub_title: 小节标题行（含 ### 前缀）
        sub_body: 小节正文（不含标题行）
        target_chars: 目标字数
        chapter_name: 所属章节名（用于 prompt 上下文）
        doc_label: 文档类型标签
        is_ratio_mode: 是否为比例模式（影响 max_tokens 计算，避免小目标时 LLM 输出过大）
        aggressive: 是否为激进模式（二次精简时启用，更严格的 prompt 和 max_tokens）

    Returns:
        (sub_title, 精简后正文, 统计信息dict)
        失败时返回 (sub_title, 原sub_body, {"status": "error", ...})
    """
    from app.services.minimax import _call_minimax_api_raw

    orig_chars = _count_chinese_chars(sub_body)
    # 比例化保底：下限 40（避免被压成 0），但不超过原文 90%（避免扩展破坏比例）
    # 修复固定 80 字保底对短小节导致 ratio 反向扩展的问题
    if target_chars < 40:
        target_chars = min(40, int(orig_chars * 0.9)) if orig_chars > 0 else 40
    hard_limit = int(target_chars * 1.15)  # 硬上限：目标+15%（修复：原 1.15×→1.3× 区间太宽）

    system_prompt = f"""你是医疗器械注册文档的小节内容精简专家。

## 核心原则（按优先级，优先级高的优先保证）
1. **意思不变**：保留原文所有核心观点、结论、法规条款号、技术参数，不编造、不篡改
2. **逻辑通顺**：精简后必须自然流畅可读，语句完整、段落连贯，无残句、断链、悬空引用。
   **宁可超出字数上限 10%，也不得输出残句、断句或语义不完整的句子**——删内容时整句删、整段删，禁止在句子中间截断
3. **字数控制**：目标约 {target_chars} 字（允许 ±15% 浮动，最多 {hard_limit} 字），字数服从前两项

本小节属于《{doc_label}》文档「{chapter_name}」章节。

## 精简规则

### 必须保留（不可删除/篡改）
- 所有法规标准条款号（如 "ISO 13485 §7.3.2"、"GB 9706.224-2021 第4章"）
- 所有具体技术参数和数值（如 "0.05 U/h"、"IPX8"、"3-7天"）
- **流程图必须完整保留**：所有 mermaid 代码块（```mermaid ... ``` 围栏）原样保留，不得删除、改写、精简或截断；流程图前后的引出句与结论句一并保留
- 表格结构必须完整保留：不得删除任何表格、表头，不得删除整列、整行或任何数据行，也不得合并行列（行数列数与顺序不变）；但**表格单元格内的文字可以精简**——压缩冗长描述、删除修饰性措辞、长句改短句，每格须保持语法完整、语义不变、可读通顺；单元格中的数值、参数、单位、标准号不得改变
- 核心结论和合规判定语句
- 关键术语首次出现时的定义

### 可以精简
- 重复表述的同一观点（合并为一句）
- 过度展开的背景介绍（压缩为一句）
- 冗长的过渡句和铺垫（删除）
- 同一标准的多条引用（合并为一条带多个条款号）
- 非关键的示例和说明性文字
- 涉及法规/标准的过程性、描述性语言（如"根据 GB XXXX 第 X 章规定……该条款要求……因此……"这类层层分析推导的叙述），直接精简为结论，删除分析推导过程；只保留条款号和最终结论

### 禁止
- 编造原文没有的数据、条款号或参数
- 删除任何法规标准引用
- 改变技术参数的数值或单位
- 增加原文没有的新观点或新结论

### 可读性要求（精简后必须保持）
- **语句完整**：每个句子必须语法完整，禁止中途截断、保留主谓宾结构；不要出现"主语后突然断句""以逗号收尾"等残句
- **段落连贯**：精简后必须保持段落内部逻辑连贯，避免话题跳脱；先说原因后说结论、先说前提后说要求等叙述顺序要保留
- **避免悬空引用**：
  - 禁止使用「如前所述」「如上所述」「见下表」「如下表所示」「上述内容」「详见后续」「前面提到」等悬空引用词
  - 若原文有指向具体内容（如"如表4-1所示""见§3.2"），精简后该引用必须仍然有效（指向的内容必须在精简结果中可找到）
  - 若引用的具体内容在精简中被删除，必须改写为完整描述或删除该引用
- **表格单元格完整**：表格单元格内文本必须语法完整、语义通顺；禁止单元格以"的/和/或/与/而/则/把/被/将/由"等连词/助词收尾的残句；单元格内应是一个完整的词组、短语或句子
- **表格上下文衔接**：保留引出表格的句子（如"主要参数如下表所示"）和解释表格的关键结论句；若表格独立成段且有明确表号（如"表 4-1"），可无引出句但需有表号标注；禁止表格前后均无任何引出或解释文字的悬空表格
- **上下文衔接**：精简后的小节首尾应能自然衔接上下文，不要出现"前文/后文"等断裂感
- **格式完整**：保留必要的 Markdown 结构（列表项、表格行列、加粗、引用块），不要因为精简而破坏列表/表格的完整结构
- **首尾完整**：精简后的小节应是一个完整的语义单元，开头和结尾都要自然；不要因为字数限制而把"因此""综上"等结论词截掉

## 输出格式
- 直接输出精简后的 Markdown 正文
- 不要输出小节标题（### XXX），只输出正文
- 不要输出任何解释、前言、总结
- 保留原有的 Markdown 格式（表格、列表、加粗等）""" + (
    f"""

## ⚠️ 紧急要求：必须严格控制字数
你之前的精简尝试未达标，现在需要更紧凑地精简。
- 在不损伤语义前提下合并同义句、压缩冗长背景、删除过渡性描述
- 表格结构必须完整保留：不得删除任何表格、表头，不得删除整列、整行或任何数据行，也不得合并行列（行数列数与顺序不变）；但**表格单元格内的文字可以精简**——压缩冗长描述、删除修饰性措辞、长句改短句，每格须保持语法完整、语义不变、可读通顺；单元格中的数值、参数、单位、标准号不得改变
- 表格单元格内文本必须保持语法完整、语义通顺，禁止单元格残句
- 法规条款号保留，但删除其后的过程性展开说明和层层分析推导，直接写结论
- 目标约 {target_chars} 字（最多 {hard_limit} 字）
- **可读性约束仍然适用**：即使精简也必须保持语句完整、段落连贯，禁止悬空引用；如要删除被引用的内容，必须同时改写或删除引用本身"""
    if aggressive else ""
)

    user_prompt = f"""请精简以下小节内容（目标约 {target_chars} 字，最多 {hard_limit} 字，优先保证意思不变和逻辑通顺）：

{sub_body}"""

    try:
        # qwen3.5:122b 模型存在 thinking tokens 占用：实测 num_predict < 16384 时
        # 模型会消耗所有 tokens 但 content 为空，done_reason="length"。
        # 因此下限和上限都至少 16384，否则空响应 → 精简失败。
        # 比例模式小目标时：max_tok 应 = target*3 (中文字 1字≈1.5 token) + 16384 thinking 预算
        # 非比例模式：max_tok 应 = target*3 + 16384 thinking 预算
        if is_ratio_mode:
            max_tok = min(max(int(target_chars * 3), 16384), 16384)
        else:
            max_tok = min(max(target_chars * 3, 16384), 16384)
        async with _llm_semaphore:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    _call_minimax_api_raw,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.2 if not aggressive else 0.1,
                    max_tokens=max_tok,
                ),
                timeout=180.0,
            )

        if not response:
            print(f"[summarize_section] LLM空响应: 小节='{sub_title}', "
                  f"目标={target_chars}字, 原文={orig_chars}字 "
                  f"(检查 Ollama {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11435')} "
                  f"模型 {os.getenv('OLLAMA_MODEL', 'qwen3.5:122b')} 是否正常)")
            return (sub_title, sub_body, {
                "status": "error", "reason": "LLM空响应",
                "orig_chars": orig_chars, "new_chars": orig_chars,
            })

        # 清理响应：移除可能误加的 ### 标题行
        cleaned = response.strip()
        # 若 LLM 误加了 ### 开头，移除第一行
        if cleaned.startswith("### "):
            lines = cleaned.split("\n", 1)
            cleaned = lines[1].strip() if len(lines) > 1 else cleaned

        # 清理悬空引用兜底：若 LLM 输出结尾包含明显悬空引用（无明确目标对象），
        # 截断到该引用所在句子的开头，避免留下"如前所述……"等半句话
        import re as _re_dangling
        dangling_patterns = [
            r"如前所述[，。；,.;\s]*$",
            r"如上所述[，。；,.;\s]*$",
            r"见下表[，。；,.;\s]*$",
            r"如下表所示[，。；,.;\s]*$",
            r"上述内容[，。；,.;\s]*$",
            r"详见后续[，。；,.;\s]*$",
            r"前面提到[，。；,.;\s]*$",
            r"参见附录[，。；,.;\s]*$",
        ]
        if cleaned:
            for pat in dangling_patterns:
                m = _re_dangling.search(pat, cleaned)
                if m:
                    # 截断到该悬空引用所在句子的开头
                    cut_pos = m.start()
                    # 找到 cut_pos 之前的最近一个句号/换行
                    last_boundary = max(
                        cleaned.rfind("。", 0, cut_pos),
                        cleaned.rfind("\n", 0, cut_pos),
                    )
                    if last_boundary > 0:
                        cleaned = cleaned[:last_boundary + 1].rstrip()
                        print(f"[summarize_section] 清理悬空引用 (匹配 '{pat}'): "
                              f"保留前 {len(cleaned)} 字符")
                    break

        new_chars = _count_chinese_chars(cleaned)

        # ── 后置可读性校验：检测残句、悬空引用、表格列表完整性问题 ──
        # 不达标触发 1 次修复重试，将 issues 反馈给 LLM 主动修复（比 regex 硬删更安全）
        readability_warnings = []
        validation = _validate_readability(cleaned, sub_body)
        if not validation["is_valid"]:
            print(f"[summarize_section] 可读性校验发现 {len(validation['issues'])} 个问题: "
                  f"{validation['issues']}，触发修复重试")
            fix_user_prompt = f"""你刚才精简的内容存在以下可读性问题：
{chr(10).join(f'- {issue}' for issue in validation['issues'])}

请修复上述所有问题，重新输出精简后的内容。要求：
1. 修复上述所有可读性问题（补全残句、改写或删除悬空引用、修复表格列表结构）
2. 保持语义不变，保留所有法规条款号和技术参数
3. 目标约 {target_chars} 字（最多 {hard_limit} 字）
4. 直接输出修复后的 Markdown 正文，不要输出标题和解释

待修复内容：
{cleaned}"""
            try:
                async with _llm_semaphore:
                    fix_response = await asyncio.wait_for(
                        asyncio.to_thread(
                            _call_minimax_api_raw,
                            system_prompt=system_prompt,
                            user_prompt=fix_user_prompt,
                            temperature=0.2,
                            max_tokens=max_tok,
                        ),
                        timeout=180.0,
                    )
                if fix_response:
                    fix_cleaned = fix_response.strip()
                    if fix_cleaned.startswith("### "):
                        lines_fc = fix_cleaned.split("\n", 1)
                        fix_cleaned = lines_fc[1].strip() if len(lines_fc) > 1 else fix_cleaned
                    # 重新校验修复结果
                    revalidation = _validate_readability(fix_cleaned, sub_body)
                    if revalidation["is_valid"]:
                        print(f"[summarize_section] 可读性修复成功: 修复 {len(validation['issues'])} 个问题")
                        cleaned = fix_cleaned
                    elif _count_chinese_chars(fix_cleaned) <= new_chars:
                        # 修复后仍有问题但未变长，接受修复结果并记录剩余警告
                        print(f"[summarize_section] 可读性修复部分成功: 剩余 {len(revalidation['issues'])} 个问题")
                        cleaned = fix_cleaned
                        readability_warnings = revalidation["issues"]
                    else:
                        # 修复后变长且仍有问题，保留原 cleaned，记录原警告
                        readability_warnings = validation["issues"]
                new_chars = _count_chinese_chars(cleaned)
            except Exception as e:
                print(f"[summarize_section] 可读性修复重试失败: {e}")
                readability_warnings = validation["issues"]

        # 迭代精简：若结果超目标 15%，最多重试 2 轮（共 3 轮），每轮更紧凑
        # 修复：原 1.2× 阈值过宽，比例模式下允许 20% 偏差导致总比例偏离目标
        max_rounds = 3
        for round_idx in range(1, max_rounds):
            if new_chars <= target_chars * 1.15:
                break  # 已达标（目标+15%以内）
            print(f"[summarize_section] 第{round_idx}轮精简不足: "
                  f"{new_chars}字 > 目标{target_chars}字×1.15={int(target_chars*1.15)}字，重试")
            retry_user_prompt = f"""上一轮精简后为 {new_chars} 字，仍超出目标 {target_chars} 字。
请在保持语义完整和可读性的前提下，进一步精简以下内容，目标约 {target_chars} 字（最多 {hard_limit} 字）：
合并重复表述、压缩冗长背景、删除非必要过渡句；表格结构完整保留（行列不增删不合并），但单元格内文字同样精简（语义不变、可读通顺，数值/参数/单位不得改变）；涉及法规的过程性描述直接写结论、删除分析推导；保留核心结论、法规条款号和技术参数：

{cleaned}"""
            try:
                async with _llm_semaphore:
                    retry_response = await asyncio.wait_for(
                        asyncio.to_thread(
                            _call_minimax_api_raw,
                            system_prompt=system_prompt,
                            user_prompt=retry_user_prompt,
                            temperature=0.1,
                            max_tokens=max_tok,
                        ),
                        timeout=180.0,
                    )
                if retry_response:
                    retry_cleaned = retry_response.strip()
                    if retry_cleaned.startswith("### "):
                        lines = retry_cleaned.split("\n", 1)
                        retry_cleaned = lines[1].strip() if len(lines) > 1 else retry_cleaned
                    retry_chars = _count_chinese_chars(retry_cleaned)
                    # 只在比上一轮更好的时候接受
                    if retry_chars < new_chars:
                        cleaned = retry_cleaned
                        new_chars = retry_chars
            except Exception as e:
                print(f"[summarize_section] 第{round_idx}轮重试失败: {e}")
                break

        # 硬截断兜底已移除（用户要求）：3 轮 LLM 精简后仍超目标时，
        # 保留 LLM 的最佳结果（不再按句子边界物理裁剪，避免内容缺失/段落断裂）

        # 流程图保护硬保障：精简结果若丢失原文 mermaid 块，追加回缺失的块
        cleaned = _ensure_mermaid_preserved(sub_body, cleaned)
        new_chars = _count_chinese_chars(cleaned)

        return (sub_title, cleaned, {
            "status": "ok",
            "orig_chars": orig_chars,
            "new_chars": new_chars,
            "target_chars": target_chars,
            "readability_warnings": readability_warnings,
        })

    except asyncio.TimeoutError:
        print(f"[summarize_section] LLM超时(180秒): 小节='{sub_title}', 目标={target_chars}字")
        return (sub_title, sub_body, {
            "status": "error", "reason": "LLM超时（180秒）",
            "orig_chars": orig_chars, "new_chars": orig_chars,
        })
    except Exception as e:
        print(f"[summarize_section] LLM调用异常: 小节='{sub_title}', "
              f"错误={type(e).__name__}: {e}")
        return (sub_title, sub_body, {
            "status": "error", "reason": str(e),
            "orig_chars": orig_chars, "new_chars": orig_chars,
        })


def _split_full_markdown(markdown: str) -> list[dict]:
    """将完整文档 markdown 拆分为章节列表。

    文档格式（由 _sync_doc_context 生成）：每个章节为
        # {章节名}
        {正文，以 ## 章节名开头，含 ### / #### / ##### 小节}
    返回 [{"name": 章节名, "content": 该章正文, "header": "## 章节名"行,
            "subsections": [{"title": "### ...", "body": "..."}]}]。
    章节内无 ### 小节时，整章作为单一小节（与 summarize_section 回退一致）。
    """
    import re
    sections = []
    cur_name = None
    cur_lines = []

    def _flush():
        if cur_name is None:
            return
        content = "\n".join(cur_lines).strip()
        parsed = _split_chapter_into_subsections(content)
        header = parsed[0]["header"] if parsed else ""
        subsections = parsed[0]["subsections"] if parsed else []
        if not subsections and content:
            subsections = [{"title": "### 概述", "body": content}]
        sections.append({
            "name": cur_name,
            "content": content,
            "header": header,
            "subsections": subsections,
        })

    for line in markdown.split("\n"):
        m = re.match(r'^#\s+(.+?)\s*$', line)
        if m:
            _flush()
            cur_name = m.group(1).strip()
            cur_lines = []
        elif cur_name is not None:
            cur_lines.append(line)
    _flush()
    return sections


def _reassemble_full_markdown(sections: list[dict], bodies: list[str]) -> str:
    """按 sections 结构 + 新的小节正文 bodies 重组完整 markdown。

    bodies 顺序与 sections 中各 subsections 展平顺序一致。
    保留 `# 章节名` + `## 章节名` + `### 小节` 结构。
    """
    idx = 0
    parts = []
    for sec in sections:
        parts.append(f"# {sec['name']}\n\n")
        if sec.get("header"):
            parts.append(sec["header"] + "\n\n")
        for sub in sec["subsections"]:
            new_body = bodies[idx]
            idx += 1
            parts.append(f"{sub['title']}\n\n{new_body}\n\n")
    return "\n".join(parts).rstrip() + "\n"


# ── 法规引用剥离（导出前后处理）──
# 生成过程中提示词仍要求引用法规条款（防幻觉、保证内容有据）；导出呈现前
# 再由 LLM 剥离法规引用语句，只保留根据法规得出的实质内容描述。
# 可用 env STRIP_REGULATIONS_ON_EXPORT=false 关闭。

_STRIP_REGULATIONS_ENABLED = os.getenv("STRIP_REGULATIONS_ON_EXPORT", "true").lower() in (
    "1", "true", "yes", "on")

_STRIP_REGULATION_SYSTEM = """你是医疗器械文档编辑。给定文档的一个小节，请去除其中所有法规/标准引用表述，只保留根据法规得出的实质内容描述。

必须去除：
- 标准编号与条款号引用（如 "ISO 13485 §7.3.2"、"GB 9706.224-2021 第4章"、"IEC 62304 §5.7"、"依据XX标准"、"按照XX要求"、"符合XX规定"）
- 引用法规的从句与叙述（"本节依据…编制"、"根据…规定"）——把句子改写为不含法规引用但内容完整的表述
- 表格中的标准号引用改为对应要求的简述（表格结构、行列不得删除）

改写必须保持语句通顺和完整：去除法规引用后的每个句子必须语法完整、语义通顺、自然衔接上下文；禁止残句、断句、以连词/助词收尾的不完整表述

必须保留（不可删改）：
- 根据法规得出的所有实质内容：参数、指标、措施、流程、要求、结论
- 技术参数、数值、单位一律不变
- 小节标题与 Markdown 结构（标题层级、列表、表格）保持不变

输出：只输出处理后的小节内容，第一行保持原小节标题行，不要任何解释或总结。"""


async def _strip_regulation_subsection(sub_title: str, sub_body: str) -> str:
    """剥离单个小节中的法规引用语句（LLM 后处理，失败保留原文）。"""
    from app.services.minimax import _call_minimax_api_raw

    user_prompt = f"{sub_title}\n\n{sub_body}"

    def _do():
        return _call_minimax_api_raw(
            system_prompt=_STRIP_REGULATION_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=8192,
        )

    try:
        resp = await asyncio.wait_for(asyncio.to_thread(_do), timeout=180.0)
    except Exception:
        return sub_body  # 静默降级：保留原文
    resp = (resp or "").strip()
    if not resp:
        return sub_body
    # LLM 可能重复输出标题行；重组时自行拼接标题，剥掉响应中的首行标题
    lines = resp.split("\n")
    first = lines[0].strip() if lines else ""
    title_plain = sub_title.lstrip("#").strip()
    if first.lstrip("#").strip() == title_plain:
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines)


async def _strip_regulations_from_document(markdown: str) -> tuple[str, int]:
    """整篇文档法规引用剥离：拆章分节 → 并行逐小节处理 → 重组。

    Returns:
        (剥离后全文, 处理的小节数)。各小节失败保留原文，不中断整体。
    """
    sections = _split_full_markdown(markdown)
    tasks = [
        asyncio.create_task(_strip_regulation_subsection(sub["title"], sub["body"]))
        for sec in sections for sub in sec["subsections"]
    ]
    bodies = await asyncio.gather(*tasks) if tasks else []
    return _reassemble_full_markdown(sections, list(bodies)), len(bodies)


# ── 可精简度预判：先判断哪些小节已无精简空间，只精简仍有空间的部分 ──

_CONDENSABILITY_SYSTEM = """你是文档精简预判专家。给定各小节的标题、字数与内容预览，判断每个小节是否还有精简空间。
判定标准：
- 已高度精炼（要点式短句/列表/表格为主、无冗余叙述）→ 无精简空间（condensable=false），继续压缩会丢失信息
- 仍有冗余叙述、重复表述、长段落铺垫、过程性推导 → 可精简（condensable=true）
宁可保守：不确定时判 true（可精简）。
输出严格 JSON（无围栏无解释）：
{"judgments": [{"title": "小节标题原文", "condensable": true, "reason": "≤20字"}]}"""


async def _judge_condensable_subsections(subsections: list) -> set:
    """预判各小节可精简度（一次 LLM 调用批量判断）。

    Returns:
        「不可精简」的小节标题集合（已 lstrip # 归一）。
        LLM 失败/解析失败返回空集（全部视为可精简，即原有行为），不阻塞精简。
    """
    from app.services.minimax import _call_minimax_api_raw

    items = [s for s in (subsections or []) if (s.get("body") or "").strip()]
    if len(items) <= 1:
        return set()  # 单小节无需预判

    lines = []
    for s in items:
        plain = s["title"].lstrip("#").strip()
        preview = (s["body"] or "")[:120].replace("\n", " ")
        lines.append(f"- 标题: {plain} | 字数: {_count_chinese_chars(s['body'])} | 预览: {preview}")
    user_prompt = f"待精简文档的小节清单：\n" + "\n".join(lines) + "\n\n请输出各小节可精简度判断 JSON。"

    def _do():
        return _call_minimax_api_raw(
            system_prompt=_CONDENSABILITY_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=2048,
        )

    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_do), timeout=90.0)
    except Exception as e:
        print(f"[condense] 可精简度预判失败（退化为全量精简）: {e}")
        return set()
    data = _parse_att_map_json(raw or "")
    non_cond = set()
    for j in (data.get("judgments") or []):
        if isinstance(j, dict) and j.get("condensable") is False:
            t = str(j.get("title") or "").strip()
            if t:
                non_cond.add(t)
    # 与实际小节标题宽松匹配（预判返回的标题可能略有出入）
    result = set()
    for s in items:
        plain = s["title"].lstrip("#").strip()
        if plain in non_cond or any(_same_chapter(plain, t) for t in non_cond):
            result.add(plain)
    if result:
        print(f"[condense] 预判 {len(result)}/{len(items)} 个小节无精简空间，保持原文")
    return result


async def _condense_document_to_limit(
    markdown: str,
    doc_label: str = "",
    target_chars: int = _DOC_WORD_LIMIT,
    max_iterations: int = _DOC_WORD_LIMIT_MAX_ITERATIONS,
) -> tuple[str, dict]:
    """整篇文档迭代精简到目标字数以内（软收敛，不硬截断）。

    循环：统计整篇字数 → 超限则按小节当前长度比例分配预算、并行精简各小节
    （复用 _summarize_one_subsection，其内部已做小节级迭代收敛 + 可读性校验）→
    重组 → 再统计。上限 max_iterations 轮；仍超限则返回最后一轮（最佳）结果。

    Args:
        markdown: 完整文档 markdown（`# 章节名` 段落结构）
        doc_label: 文档类型中文标签（用于精简 prompt 上下文）
        target_chars: 目标字数上限（有效字符数，与 _count_chinese_chars 口径一致）
        max_iterations: 最大迭代轮数

    Returns:
        (最终 markdown, 统计 dict)。统计含 original_chars / final_chars /
        iterations / converged。
    """
    current = markdown
    total = _count_chinese_chars(current)
    stats = {
        "original_chars": total,
        "final_chars": total,
        "iterations": 0,
        "converged": False,
    }
    if not current or total <= target_chars:
        stats["converged"] = total <= target_chars
        return current, stats

    for it in range(1, max_iterations + 1):
        sections = _split_full_markdown(current)
        flat = [(sec, sub) for sec in sections for sub in sec["subsections"]]
        if not flat:
            break

        # ── 可精简度预判：只精简仍有空间的小节，已高度精炼的保持原文 ──
        non_condensable = await _judge_condensable_subsections([sub for _, sub in flat])
        condensable_idx = [
            i for i, (_, sub) in enumerate(flat)
            if sub["title"].lstrip("#").strip() not in non_condensable
        ]
        if not condensable_idx:
            print(f"[condense] 第 {it} 轮预判：全部小节已无精简空间，停止迭代")
            break

        orig_lens = [_count_chinese_chars(sub["body"]) for _, sub in flat]
        # 预算只在可精简小节间分配（不可精简的保持原文，不占预算；保底 40 字）
        condensable_len = sum(orig_lens[i] for i in condensable_idx) or 1
        targets = [0] * len(flat)
        for i in condensable_idx:
            targets[i] = max(int(target_chars * orig_lens[i] / condensable_len), 40)

        tasks = [None] * len(flat)
        for i in condensable_idx:
            sec, sub = flat[i]
            tasks[i] = asyncio.create_task(_summarize_one_subsection(
                sub_title=sub["title"],
                sub_body=sub["body"],
                target_chars=targets[i],
                chapter_name=sec["name"],
                doc_label=doc_label,
            ))
        await asyncio.gather(*[t for t in tasks if t])

        bodies = []
        for i, (sec, sub) in enumerate(flat):
            if tasks[i] is None:
                bodies.append(sub["body"])  # 预判无精简空间，保持原文
                continue
            _, new_body, stat = tasks[i].result()
            bodies.append(new_body if stat.get("status") == "ok" else sub["body"])

        new_md = _reassemble_full_markdown(sections, bodies)
        new_total = _count_chinese_chars(new_md)

        stats["iterations"] = it
        stats["final_chars"] = new_total

        if new_total <= target_chars:
            stats["converged"] = True
            current = new_md
            break
        if new_total >= total:
            # 本轮无进展（精简未缩短），停止迭代，保留已有最佳结果
            break
        current = new_md
        total = new_total

    stats["final_chars"] = _count_chinese_chars(current)
    return current, stats


@tool
async def summarize_section(
    section_name: str,
    mode: str = "ratio",
    target: float = 0.5,
    doc_type: str = "",
) -> str:
    """对已生成章节中的每个小节内容进行精简，用精简后内容替换原小节。

    支持两种模式：
    - 字数模式 (mode="words"): target 为目标字数（int），按各小节原字数比例分配预算
    - 比例模式 (mode="ratio"): target 为压缩比例（float 0.1~1.0），每小节按原字数×比例精简

    精简由 LLM 完成，严格保留法规条款号、技术参数、表格数据和核心结论。
    单个小节精简失败时保留原文，不影响其他小节。

    调用时机:
    - 用户说"精简/总结/压缩 XX 章节内容"时
    - 用户要求"把这一章缩短到 XXX 字"时
    - 文档生成完成后用户要求缩短整体内容时

    Args:
        section_name: 要精简的章节名称（必须已存在于 generated_sections 中）
        mode: 精简模式，"words"（字数模式）或 "ratio"（比例模式）
        target: 目标值。mode="words" 时为 int 字数；mode="ratio" 时为 float 比例（0.1~1.0）
        doc_type: 文档类型标识，用于prompt上下文。为空时自动从上下文获取。

    Returns:
        JSON格式结果，包含精简前后字数对比、各小节状态。完整精简内容通过旁路传递给
        _after_tools_node，不进入LLM对话历史。
    """
    try:
        from app.services.doc_types import DOC_TYPE_LABELS

        # 从上下文获取 doc_type 和当前 generated_sections
        if not doc_type:
            doc_type = _current_doc_type.get()
        doc_label = DOC_TYPE_LABELS.get(doc_type, doc_type) if doc_type else "设计策划文档"

        # 参数校验
        if mode not in ("words", "ratio"):
            return json.dumps({
                "status": "error",
                "message": f'参数 mode 必须为 "words" 或 "ratio"，当前为 "{mode}"',
            }, ensure_ascii=False)

        if mode == "ratio":
            if not (0.1 <= float(target) <= 1.0):
                return json.dumps({
                    "status": "error",
                    "message": f"比例模式下 target 应在 0.1~1.0 之间，当前为 {target}",
                }, ensure_ascii=False)
        else:
            if int(target) < 100:
                return json.dumps({
                    "status": "error",
                    "message": f"字数模式下 target 应不小于 100 字，当前为 {target}",
                }, ensure_ascii=False)

        # 读取当前章节内容
        current_markdown = _current_generated_markdown.get()
        if not current_markdown:
            return json.dumps({
                "status": "error",
                "message": "当前没有已生成的文档内容。请先生成至少一个章节。",
            }, ensure_ascii=False)

        # 从完整 markdown 中提取指定章节内容
        # 章节内容格式：# {章节名}\n\n{章节正文}\n\n
        # 其中章节正文以 ## {章节名} 开头
        import re
        chapter_pattern = rf'^# \s*{re.escape(section_name)}\s*$'
        lines = current_markdown.split("\n")
        in_chapter = False
        chapter_lines = []
        for line in lines:
            if re.match(chapter_pattern, line.strip()):
                in_chapter = True
                continue  # 跳过 # 章节名 这一行（generated_sections 存的是 ## 开头的内容）
            elif in_chapter and re.match(r'^# ', line.strip()):
                # 遇到下一个 # 章节，结束
                break
            elif in_chapter:
                chapter_lines.append(line)

        chapter_content = "\n".join(chapter_lines).strip()
        if not chapter_content:
            return json.dumps({
                "status": "error",
                "message": f'未找到章节「{section_name}」。请确认章节名称正确，且该章节已生成。',
                "available_sections": list(_get_section_names_from_markdown(current_markdown)),
            }, ensure_ascii=False)

        # 拆分小节
        parsed = _split_chapter_into_subsections(chapter_content)
        if not parsed or not parsed[0]["subsections"]:
            # 回退：无 ### 小节，整体作为一个小节精简
            header = chapter_content.split("\n", 1)[0] if "\n" in chapter_content else ""
            subsections = [{"title": "### 概述", "body": chapter_content}]
            parsed = [{"header": header, "subsections": subsections}]
            print(f"[summarize_section] No ### subsections found in '{section_name}', "
                  f"treating whole chapter as single subsection")

        subsections = parsed[0]["subsections"]
        header = parsed[0]["header"]
        sub_count = len(subsections)

        # ── 可精简度预判：只精简仍有空间的小节，已高度精炼的保持原文 ──
        non_condensable = await _judge_condensable_subsections(subsections)
        skipped_count = sum(1 for s in subsections
                            if s["title"].lstrip("#").strip() in non_condensable)

        # 计算每个小节的目标字数
        orig_chars_list = [_count_chinese_chars(s["body"]) for s in subsections]
        orig_total = sum(orig_chars_list) or 1  # 避免除0

        targets = []
        ratio = float(target) if mode == "ratio" else None
        if mode == "ratio":
            # 比例化保底：下限 40（避免小节被压成 0），但不超过原文 90%（防扩展破坏比例）
            # 修复：原固定 80 字保底对短小节导致 ratio 反向扩展（如 50 字小节 ratio=0.5 → 实际 160%）
            for oc in orig_chars_list:
                raw_target = int(oc * ratio)
                if raw_target < 40 and oc > 0:
                    targets.append(min(40, int(oc * 0.9)))
                else:
                    targets.append(max(raw_target, 40))
        else:  # words
            total_target = int(target)
            # 预算只分配给可精简小节（不可精简的保持原文不占预算）
            condensable_total = sum(
                oc for oc, s in zip(orig_chars_list, subsections)
                if s["title"].lstrip("#").strip() not in non_condensable) or orig_total
            for oc, s in zip(orig_chars_list, subsections):
                if s["title"].lstrip("#").strip() in non_condensable:
                    targets.append(oc)  # 不参与分配（占位，实际保持原文）
                    continue
                # 按原字数比例分配，保底80字
                allocated = max(int(total_target * oc / condensable_total), 80)
                targets.append(allocated)

        print(f"[summarize_section] '{section_name}': {sub_count} subsections, "
              f"mode={mode}, target={target}, orig_total={orig_total}"
              + (f"，预判 {skipped_count} 个小节无精简空间保持原文" if skipped_count else ""))

        # 并行精简各小节（不可精简的直接保持原文，不调 LLM）
        async def _condense_or_keep(i, s):
            if s["title"].lstrip("#").strip() in non_condensable:
                return (s["title"], s["body"], {
                    "title": s["title"],
                    "orig_chars": orig_chars_list[i],
                    "new_chars": orig_chars_list[i],
                    "target_chars": targets[i],
                    "status": "skipped",
                    "reason": "预判无精简空间，保持原文",
                })
            return await _summarize_one_subsection(
                sub_title=s["title"],
                sub_body=s["body"],
                target_chars=targets[i],
                chapter_name=section_name,
                doc_label=doc_label,
                is_ratio_mode=(mode == "ratio"),
            )

        gen_tasks = [
            asyncio.create_task(_condense_or_keep(i, s))
            for i, s in enumerate(subsections)
        ]
        await asyncio.gather(*gen_tasks)

        # 组装精简后章节内容（暂存以便失败再平衡）
        assembled = []  # [(sub_title, new_body, stat_dict, subsection_ref)]
        new_total = 0
        for i, task in enumerate(gen_tasks):
            sub_title, new_body, stat = task.result()
            new_total += stat["new_chars"]
            if stat["status"] == "ok":
                assembled.append((sub_title, new_body, {
                    "title": sub_title,
                    "orig_chars": stat["orig_chars"],
                    "new_chars": stat["new_chars"],
                    "target_chars": stat.get("target_chars", targets[i]),
                    "status": "ok",
                }, subsections[i]))
            else:
                # 失败/预判跳过均保留原文（skipped 状态保留标记供结果统计展示）
                assembled.append((sub_title, subsections[i]["body"], {
                    "title": sub_title,
                    "orig_chars": stat["orig_chars"],
                    "new_chars": stat["orig_chars"],
                    "target_chars": targets[i],
                    "status": stat.get("status") if stat.get("status") == "skipped" else "error",
                    "reason": stat.get("reason", "unknown"),
                }, subsections[i]))

        # ────────── 比例模式失败再平衡 ──────────
        # 修复：失败小节和超目标小节会拉高总比例，超出目标 15% 时触发二次精简
        if mode == "ratio" and ratio is not None and new_total > orig_total * ratio * 1.15:
            need_retry = [
                (i, t, b, s) for i, (t, b, s, _) in enumerate(assembled)
                if s.get("status") == "ok" and s.get("new_chars", 0) > s.get("target_chars", 0) * 1.15
            ]
            if need_retry:
                print(f"[summarize_section] 比例模式触发再平衡: "
                      f"new_total={new_total}, orig_total={orig_total}, "
                      f"当前比例={new_total/orig_total:.1%} > 目标 {ratio:.1%}×1.15="
                      f"{ratio*1.15:.1%}, 二次精简 {len(need_retry)} 节")
                # 收集"原文"和"上次精简结果"用于二次精简
                retry_tasks = [
                    asyncio.create_task(_summarize_one_subsection(
                        sub_title=t,
                        sub_body=b,  # 用上次精简结果继续精简（已经是较短版本）
                        target_chars=s.get("target_chars", targets[i]),
                        chapter_name=section_name,
                        doc_label=doc_label,
                        is_ratio_mode=True,
                        aggressive=True,  # 启用激进模式
                    ))
                    for i, t, b, s in need_retry
                ]
                await asyncio.gather(*retry_tasks)
                # 合并二次精简结果
                for (i, t, _, s), task in zip(need_retry, retry_tasks):
                    sub_title, new_body, stat = task.result()
                    if stat["status"] == "ok":
                        assembled[i] = (sub_title, new_body, {
                            "title": sub_title,
                            "orig_chars": s.get("orig_chars", stat["orig_chars"]),
                            "new_chars": stat["new_chars"],
                            "target_chars": stat.get("target_chars", s.get("target_chars")),
                            "status": "ok",
                        }, subsections[i])
                # 重新计算 new_total
                new_total = sum(item[2].get("new_chars", 0) for item in assembled)
                print(f"[summarize_section] 再平衡完成: new_total={new_total}, "
                      f"新比例={new_total/orig_total:.1%}")

        # 最终组装 parts / sub_stats
        parts = [header + "\n\n"] if header else []
        success_count = 0
        failed_count = 0
        sub_stats = []
        for sub_title, new_body, stat, _ in assembled:
            if stat.get("status") == "ok":
                success_count += 1
            else:
                failed_count += 1
            parts.append(f"{sub_title}\n\n{new_body}\n\n")
            sub_stats.append(stat)

        full_content = "".join(parts).rstrip() + "\n"

        # 通过旁路传递完整精简后内容（避免进入LLM对话历史）
        _pending_chapter_contents[section_name] = full_content

        print(f"[summarize_section] '{section_name}': "
              f"{success_count}/{sub_count} subsections summarized, "
              f"{orig_total} -> {new_total} chars "
              f"({(new_total/orig_total*100) if orig_total else 0:.1f}%)")

        return json.dumps({
            "status": "ok",
            "section_name": section_name,
            "mode": mode,
            "target": target,
            "subsections_count": sub_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "orig_total_chars": orig_total,
            "new_total_chars": new_total,
            "compression_ratio": round(new_total / orig_total, 3) if orig_total else 0,
            "subsections": sub_stats,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"精简章节「{section_name}」时异常: {str(e)}",
        }, ensure_ascii=False)


def _get_section_names_from_markdown(markdown: str) -> list[str]:
    """从完整 markdown 中提取所有 # 一级章节名"""
    import re
    if not markdown:
        return []
    names = []
    for line in markdown.split("\n"):
        m = re.match(r'^#\s+(.+?)\s*$', line)
        if m:
            names.append(m.group(1).strip())
    return names


@tool
async def summarize_document(
    mode: str = "ratio",
    target: float = 0.5,
    doc_type: str = "",
) -> str:
    """对已生成的所有章节进行批量精简（每章每小节分别精简）。

    内部循环调用 summarize_section 处理每个章节。失败章节不影响其他章节。

    调用时机:
    - 用户说"精简整个文档"/"压缩整篇文档"时
    - 用户要求"把全文缩短到 XXXX 字"时

    Args:
        mode: 精简模式，"words"（字数模式）或 "ratio"（比例模式）
        target: 目标值。words 模式为总目标字数（按章节小节数比例分配）；
                ratio 模式为压缩比例（0.1~1.0）
        doc_type: 文档类型标识，为空时自动从上下文获取

    Returns:
        JSON格式结果，包含每个章节的精简状态汇总。
    """
    try:
        current_markdown = _current_generated_markdown.get()
        if not current_markdown:
            return json.dumps({
                "status": "error",
                "message": "当前没有已生成的文档内容。请先生成至少一个章节。",
            }, ensure_ascii=False)

        section_names = _get_section_names_from_markdown(current_markdown)
        if not section_names:
            return json.dumps({
                "status": "error",
                "message": "未找到任何章节。请先生成文档。",
            }, ensure_ascii=False)

        # 字数模式下，按章节数平均分配总字数预算
        section_targets = []
        if mode == "words":
            total_target = int(target)
            per_section = max(int(total_target / len(section_names)), 200)
            for name in section_names:
                section_targets.append((name, per_section))
        else:
            for name in section_names:
                section_targets.append((name, target))

        # 顺序处理各章节（避免并发过多导致API限流）
        results = []
        success_count = 0
        for name, t in section_targets:
            summary_result = await summarize_section.ainvoke({
                "section_name": name,
                "mode": mode,
                "target": t,
                "doc_type": doc_type,
            })
            try:
                data = json.loads(summary_result)
                if data.get("status") == "ok":
                    success_count += 1
                results.append({
                    "section_name": name,
                    "status": data.get("status", "error"),
                    "orig_chars": data.get("orig_total_chars", 0),
                    "new_chars": data.get("new_total_chars", 0),
                    "subsections_count": data.get("subsections_count", 0),
                    "success_count": data.get("success_count", 0),
                    "failed_count": data.get("failed_count", 0),
                    "message": data.get("message", "") if data.get("status") != "ok" else "",
                })
            except json.JSONDecodeError:
                results.append({
                    "section_name": name,
                    "status": "error",
                    "message": "工具返回非JSON",
                })

        return json.dumps({
            "status": "ok" if success_count > 0 else "error",
            "mode": mode,
            "target": target,
            "total_sections": len(section_names),
            "success_count": success_count,
            "failed_count": len(section_names) - success_count,
            "results": results,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"批量精简异常: {str(e)}",
        }, ensure_ascii=False)



# ── Tool: set_document_format（用户文档格式/字体要求）──

@tool
async def set_document_format(
    body_font: str = "",
    heading_font: str = "",
    body_size_pt: float = 0,
    heading_size_pt: float = 0,
    line_spacing: float = 0,
    margin_cm: float = 0,
) -> str:
    """设置文档导出的字体与格式要求（持久化到会话，后续导出自动应用）。

    当用户对 agent 提出字体或文档格式要求时调用，如：
    - "正文用仿宋"（body_font=仿宋_GB2312）
    - "标题用黑体、正文用宋体小四"（heading_font=黑体, body_font=宋体, body_size_pt=12）
    - "行距 1.5 倍"（line_spacing=1.5）
    - "页边距 2.5 厘米"（margin_cm=2.5）

    常用字号对照（用户说字号时换算为 pt）：初号=42、小初=36、一号=26、小一=24、
    二号=22、小二=18、三号=16、小三=15、四号=14、小四=12、五号=10.5、小五=9。
    常用中文字体：宋体、黑体、仿宋_GB2312（或仿宋）、楷体_GB2312（或楷体）。

    Args:
        body_font: 正文中文字体名（如 宋体/仿宋_GB2312/楷体_GB2312）。空=不改
        heading_font: 标题中文字体名（如 黑体）。空=不改
        body_size_pt: 正文字号（pt）。0=不改
        heading_size_pt: 一级标题字号（pt，二~五级依次递减1pt）。0=不改
        line_spacing: 行距倍数（如 1.5）。0=不改
        margin_cm: 页边距（厘米，四边统一）。0=不改

    Returns:
        JSON：status、updated（本次修改项）、current_format（当前生效的完整设置）。
        设置在下一次 build_docx 导出及「下载文档」时自动应用。
    """
    fmt = dict(_current_document_format.get() or {})
    updated = []

    if (body_font or "").strip():
        fmt["body_font"] = body_font.strip()
        updated.append(f"正文字体={body_font.strip()}")
    if (heading_font or "").strip():
        fmt["heading_font"] = heading_font.strip()
        updated.append(f"标题字体={heading_font.strip()}")
    if body_size_pt and float(body_size_pt) > 0:
        fmt["body_size_pt"] = float(body_size_pt)
        updated.append(f"正文字号={body_size_pt}pt")
    if heading_size_pt and float(heading_size_pt) > 0:
        fmt["heading_size_pt"] = float(heading_size_pt)
        updated.append(f"标题字号={heading_size_pt}pt")
    if line_spacing and float(line_spacing) > 0:
        fmt["line_spacing"] = float(line_spacing)
        updated.append(f"行距={line_spacing}倍")
    if margin_cm and float(margin_cm) > 0:
        fmt["margin_cm"] = float(margin_cm)
        updated.append(f"页边距={margin_cm}cm")

    if not updated:
        return json.dumps({
            "status": "ok",
            "message": "未传入任何修改项，格式保持不变。",
            "current_format": fmt,
        }, ensure_ascii=False)

    _current_document_format.set(fmt)
    _pending_document_format["format"] = fmt
    return json.dumps({
        "status": "ok",
        "updated": updated,
        "current_format": fmt,
        "message": "文档格式要求已设置，将在下次导出文档时自动应用（含顶部「下载文档」入口）。",
    }, ensure_ascii=False)


# ── Tool: find_kb_reference_files / add_kb_files_as_attachment ──
# 生成文档前自主检索知识库中最接近目标的文件 → 向用户展示候选并询问 →
# 确认后添加为会话附件（自动接入附件最高优先参考的整套生成链路）。

# 旁路：add 工具写入 → _after_tools_node 合并进 state attachments
_pending_kb_attachments: dict = {}


def pop_pending_kb_attachments() -> list:
    """读取并清除待合并进 state 的知识库附件（无则空列表）。"""
    return _pending_kb_attachments.pop("files", [])


@tool
async def find_kb_reference_files(doc_type: str = "", instruction: str = "", top_n: int = 3) -> str:
    """在知识库中检索与待生成文档目标最接近的文件，供添加为附件参考。

    调用时机: 用户要求生成/编写某类文档时，生成前自主调用一次，找出知识库中与该
    文档目标最相关的参考文件。找到后**必须先向用户展示候选清单（文件名、相关度、
    内容摘要）并询问是否添加为附件**，用户确认后再调用 add_kb_files_as_attachment。
    知识库无文件时返回 no_kb_files。

    Args:
        doc_type: 待生成文档类型标识（用于构造检索目标）
        instruction: 用户的生成要求原文（可选，与 doc_type 共同构造检索目标）
        top_n: 返回候选数上限，默认3，最多5

    Returns:
        JSON: candidates=[{source_file, file_id, score, hits, sample}]
    """
    from app.services.doc_types import DOC_TYPE_LABELS
    label = DOC_TYPE_LABELS.get(doc_type, "") if doc_type else ""
    goal = " ".join(x for x in (label, (instruction or "").strip()) if x) or "设计开发文档"
    try:
        from app.services.rag.vector_store import VectorStore
        store = VectorStore(collection_name="uploads")
        if store.collection.count() == 0:
            return json.dumps({
                "status": "no_kb_files",
                "message": "知识库中暂无文件，跳过参考文件检索。",
                "candidates": [],
            }, ensure_ascii=False)
        query_embedding = store.embedder.encode_single(goal)
        raw = store.collection.query(
            query_embeddings=[query_embedding], n_results=24,
            include=["documents", "metadatas", "distances"],
        )
        # 按 source_file 聚合：最高相关度 + 命中数 + 首条摘要
        agg = {}
        if raw and raw.get("ids") and raw["ids"][0]:
            for i in range(len(raw["ids"][0])):
                meta = raw["metadatas"][0][i] or {}
                src = meta.get("source_file", "未知文件")
                sim = max(0.0, 1.0 - raw["distances"][0][i] / 2.0)
                e = agg.setdefault(src, {"score": 0.0, "hits": 0,
                                         "sample": "", "file_id": meta.get("file_id", "")})
                e["score"] = max(e["score"], sim)
                e["hits"] += 1
                if not e["sample"]:
                    e["sample"] = (raw["documents"][0][i] or "")[:120]
        ranked = sorted(agg.items(), key=lambda kv: kv[1]["score"], reverse=True)
        ranked = ranked[:max(1, min(int(top_n or 3), 5))]
        candidates = [{
            "source_file": src,
            "file_id": v["file_id"],
            "score": round(v["score"], 3),
            "hits": v["hits"],
            "sample": v["sample"],
        } for src, v in ranked]
        if not candidates:
            return json.dumps({
                "status": "no_match",
                "message": "知识库中未检索到与文档目标相关的内容。",
                "candidates": [],
            }, ensure_ascii=False)
        return json.dumps({
            "status": "ok",
            "goal": goal,
            "count": len(candidates),
            "candidates": candidates,
            "message": "已找到候选参考文件。请向用户展示候选清单（文件名+相关度+摘要）"
                       "并询问是否添加为附件，确认后调用 add_kb_files_as_attachment。",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"知识库检索失败: {e}",
            "candidates": [],
        }, ensure_ascii=False)


@tool
async def add_kb_files_as_attachment(source_files: str) -> str:
    """将知识库文件添加为当前会话附件（仅在用户确认后调用）。

    与 find_kb_reference_files 配套使用：find 返回候选 → 向用户展示并询问 →
    用户确认后用本工具添加。添加后文件立即成为会话附件，生成文档时将作为
    最高优先参考（附件分配/检索注入链路自动生效）。

    Args:
        source_files: 要添加的知识库文件 source_file 列表，多个用英文逗号分隔。
                      必须来自 find_kb_reference_files 的候选且经用户确认。

    Returns:
        JSON: added（已添加文件名）/ skipped（跳过及原因）/ char_counts
    """
    from app.services.rag.vector_store import VectorStore

    files = [s.strip() for s in (source_files or "").split(",") if s.strip()]
    if not files:
        return json.dumps({
            "status": "error",
            "message": "未提供文件名。source_files 应为逗号分隔的文件名列表。",
        }, ensure_ascii=False)
    try:
        store = VectorStore(collection_name="uploads")
        existing_ids = {a.get("file_id") for a in (_current_attachments.get() or [])}
        added, skipped, pending = [], [], []
        for src in files:
            full_text = store.get_text_by_source(src) or ""
            if not full_text.strip():
                skipped.append(f"{src}（知识库中无内容）")
                continue
            file_id = src  # 与 from-kb 端点回退策略一致：以 source_file 为附件标识
            if file_id in existing_ids:
                skipped.append(f"{src}（已在附件列表）")
                continue
            pending.append({
                "file_id": file_id,
                "filename": os.path.basename(src) or src,
                "char_count": len(full_text),
                "preview": full_text[:500] + ("..." if len(full_text) > 500 else ""),
                "full_text": full_text,
                "toc": "",
                "status": "completed",
            })
            existing_ids.add(file_id)
            added.append(src)
        if pending:
            _pending_kb_attachments["files"] = _pending_kb_attachments.get("files", []) + pending
        return json.dumps({
            "status": "ok",
            "added": added,
            "skipped": skipped,
            "char_counts": {p["filename"]: p["char_count"] for p in pending},
            "message": (f"已添加 {len(added)} 个知识库文件为附件" if added
                        else "未添加任何文件") +
                       ("。" if not skipped else f"；跳过: {'；'.join(skipped)}"),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"添加附件失败: {e}",
        }, ensure_ascii=False)


# ── Tool 7: web_search ──

# 医疗器械/文档生成类关键词：命中则走医疗专用搜索（Agent SDK 深度研究），
# 未命中则视为通用实时问题（天气、新闻等），直接对原始关键词做真实网络搜索。
# 列表保持高精度（宁可少放，避免把实时问题误判为医疗问题）。
_MEDICAL_DOC_KEYWORDS = (
    "医疗器械", "医疗", "器械", "药监", "NMPA", "FDA", "CE", "ISO", "GB/T", "GB ",
    "YY/T", "YY ", "法规", "标准", "注册", "审评", "风险", "FMEA", "验证", "确认",
    "设计输入", "设计输出", "设计开发", "开发策划", "研发", "生产质量", "质量体系",
    "胰岛素", "血糖", "泵", "贴敷", "临床", "患者", "无源", "有源", "体外诊断",
    "说明书", "标签", "SOP", "作业指导书", "工艺", "检验", "检测", "灭菌",
    "第X章", "章节", "概述", "目的和范围", "产品描述", "职责", "里程碑",
    "符合性", "资源规划", "风险分析", "风险评估", "风险控制", "受益",
)

# 实时话题关键词：命中则 LLM 未调用工具时，代码层强制触发 web_search
_REALTIME_TOPIC_KEYWORDS = (
    "天气", "气温", "温度", "降雨", "降水", "台风", "地震", "新闻", "最新",
    "实时", "今日", "今天", "明天", "汇率", "股市", "股票", "金价", "疫情",
    "政策", "油价", "空气质量", "限行", "放假", "节日",
)

# 实时信息缺失的拒绝性回答特征词
_REALTIME_REFUSAL_PATTERNS = (
    "无法获取", "不能获取", "无法提供", "没有实时", "无法访问", "不能访问",
    "没有权限获取", "获取不了", "查询不了", "无法查询",
)


def _is_general_query(query: str) -> bool:
    """判断是否为通用（非医疗器械/非文档生成）查询。

    命中任一医疗/文档关键词 → 医疗路径；否则 → 通用实时路径。
    空查询视为通用（交给真实搜索），保持简单。
    """
    if not query:
        return True
    return not any(kw in query for kw in _MEDICAL_DOC_KEYWORDS)


def _looks_like_realtime_refusal(response_text: str) -> bool:
    """检测 LLM 最终回答是否为"无法获取实时信息"式的拒绝。"""
    if not response_text:
        return False
    return any(p in response_text for p in _REALTIME_REFUSAL_PATTERNS)


def _user_asks_realtime(user_text: str) -> bool:
    """检测用户问题是否涉及实时/最新信息话题。"""
    if not user_text:
        return False
    return any(kw in user_text for kw in _REALTIME_TOPIC_KEYWORDS)


def _user_asks_attachment_process(user_text: str) -> str | None:
    """检测用户消息是否要求处理（修改/补全/精简）上传的附件文档。

    用于 agent_engine._agent_node 的代码级兜底：当本地 LLM 未遵循提示词、
    没有调用 modify_attachment / enrich_attachment / summarize_attachment 工具，
    而是直接口头回答（甚至伪造"已生成/已下载"）时，据此强制触发对应工具调用。

    返回 "modify" / "enrich" / "summarize"，未命中返回 None。
    """
    if not user_text:
        return None
    # 精简/压缩 → summarize（方向最明确，先判断）
    if any(kw in user_text for kw in ("精简", "压缩", "删冗余", "删掉冗余", "缩短")):
        return "summarize"
    # 补全/补充/完善/缺失表格 → enrich（覆盖"补充缺失表格"场景）
    if any(kw in user_text for kw in (
        "补全", "补充", "完善", "扩写", "更完整", "更详细", "加表格", "加个表格",
        "补个表格", "补充表格", "补全表格", "缺失", "缺表格", "缺了表格",
    )):
        return "enrich"
    # 修改/改写/更新 → modify
    if any(kw in user_text for kw in (
        "修改", "改写", "更新", "改为", "改成", "调整", "修订", "帮我改",
    )):
        return "modify"
    return None


@tool
async def web_search(query: str, doc_type: str = "design_development_plan") -> str:
    """搜索互联网获取最新信息。

    与 search_kb 的区别: search_kb 搜索本地预置知识库，web_search 搜索互联网最新内容。
    当本地知识库找不到需要的信息，或需要查询最新法规动态、实时信息（天气、新闻等）时使用此工具。

    Args:
        query: 搜索查询关键词。医疗/文档类问题应为标准号、法规名或技术问题；
               通用实时问题（如天气、新闻）可直接使用自然语言描述。
        doc_type: 文档类型标识，用于优化搜索策略。

    Returns:
        JSON格式的搜索结果，包含网页摘要和相关法规/实时信息。
    """
    import concurrent.futures

    web_info = ""
    search_method = "none"

    # 从上下文获取当前产品名称，避免硬编码
    product_name = _current_product_name.get() or "贴敷式胰岛素泵"

    if _is_general_query(query):
        # ── 通用实时查询（天气、新闻等）→ 直接对原始关键词做真实网络搜索 ──
        # 不经过 Agent SDK 的医疗专用研究提示（它会过滤掉非医疗主题），
        # 也不做章节→医疗查询改写，避免把"今天天气"变成"医疗器械 法规 天气"。
        try:
            from app.services.web_search import SyncWebSearchService
            general_search = SyncWebSearchService()
            if general_search.playwright_available:
                web_info, _ = general_search.search_general(
                    query=query, max_results=3, enable_deep_scrape=True,
                )
                if web_info:
                    search_method = "ddgs"
                    print(f"[agent_tools] web_search(general): {len(web_info)} chars via raw web search")
        except Exception as e:
            print(f"[agent_tools] general search failed: {e}")

        if not web_info:
            return json.dumps({
                "status": "no_results",
                "message": f'未找到与"{query}"相关的网络信息。请尝试使用不同关键词。',
                "results": [],
            }, ensure_ascii=False)
    else:
        # ── 医疗器械/文档类查询 → Agent SDK 深度研究，失败降级 ddgs/Playwright ──
        try:
            from app.services.agent_search import SyncAgentSearchService
            agent_search = SyncAgentSearchService()
            if agent_search.available:
                web_info, _ = agent_search.search_regulations(
                    chapter_name=query,
                    product_type=product_name,
                    max_results=3,
                    enable_deep_scrape=True,
                    enable_file_download=False,
                    doc_type=doc_type,
                )
                if web_info:
                    search_method = "agent_sdk"
                    print(f"[agent_tools] web_search: {len(web_info)} chars via Agent SDK")
        except Exception as e:
            print(f"[agent_tools] Agent SDK search failed: {e}")

        # Agent SDK 不可用或失败时回退到通用搜索
        if not web_info:
            try:
                from app.services.web_search import SyncWebSearchService
                playwright_search = SyncWebSearchService()
                if playwright_search.playwright_available:
                    web_info, _ = playwright_search.search_general(
                        query=query, max_results=3, enable_deep_scrape=True,
                    )
                    if web_info:
                        search_method = "ddgs"
                        print(f"[agent_tools] web_search: {len(web_info)} chars via raw web search (fallback)")
            except Exception as e:
                print(f"[agent_tools] Playwright search failed: {e}")

    if not web_info:
        return json.dumps({
            "status": "no_results",
            "message": f'未找到与"{query}"相关的网络信息。请尝试使用不同关键词，或用 search_kb 检索本地知识库。',
            "results": [],
        }, ensure_ascii=False)

    print(f"[agent_tools] web_search: {len(web_info)} chars via {search_method}")
    return json.dumps({
        "status": "ok",
        "query": query,
        "search_method": search_method,
        "content": web_info[:3000],
    }, ensure_ascii=False)


# ── Tool 8: analyze_document_structure ──

@tool
async def analyze_document_structure(file_id: str = "") -> str:
    """分析用户上传文档的章节结构和内容概要。

    将文档全文直接送给大模型，让大模型自主识别章节标题、层级关系和内容摘要。

    当用户询问以下问题时必须调用此工具:
    - "这个文档有哪些章节？"
    - "第三章讲了什么？"
    - "帮我梳理一下这个文档的结构"
    - 任何涉及文档章节、结构、内容概要的问题

    Args:
        file_id: 可选，指定要分析的附件file_id。为空时分析所有已上传的附件。

    Returns:
        JSON格式的章节结构，包含每章标题、层级、内容摘要。
    """
    from app.services.minimax import _call_minimax_api_raw

    attachments = _current_attachments.get()
    if not attachments:
        return json.dumps({
            "status": "no_attachments",
            "message": "当前没有上传附件。请先上传Word或PDF文档。",
            "structures": [],
        }, ensure_ascii=False)

    # 筛选目标附件
    target_attachments = attachments
    if file_id:
        target_attachments = [a for a in attachments if a.get("file_id") == file_id]
        if not target_attachments:
            return json.dumps({
                "status": "not_found",
                "message": f"未找到 file_id={file_id} 的附件。可用附件: {_attachments_hint(attachments)}",
                "structures": [],
            }, ensure_ascii=False)

    all_structures = []

    for att in target_attachments:
        filename = att.get("filename", "unknown")
        full_text = att.get("full_text", "")

        if not full_text:
            all_structures.append({
                "filename": filename,
                "file_id": att.get("file_id", ""),
                "status": "no_text",
                "message": "该文件无文本内容可供分析",
            })
            continue

        # 截取前 12000 字符送给 LLM（兼顾 token 消耗与覆盖范围）
        text_sample = full_text[:12000]

        system_prompt = """你是一位文档结构分析专家，专精于医疗器械注册文档的章节结构分析。

请分析以下文档全文，直接识别其章节结构。你需要:
1. 识别所有章节标题及其正确的层级（1-4级）
2. 修正不规范的编号（如"一."→"一、"、"1 概述"→"1. 概述"）
3. 对每个章节，用一句话概括其核心内容
4. 按文档中的出现顺序排列

输出必须为严格JSON格式，不要包含任何其他文字。"""

        user_prompt = f"""请分析文档「{filename}」的章节结构。

文档全文:
{text_sample}

请输出以下JSON格式:
```json
{{
  "document_title": "文档标题（从内容推断）",
  "chapters": [
    {{
      "level": 1,
      "title": "章节标题",
      "summary": "一句话概括本章核心内容（不超过40字）"
    }}
  ]
}}
```

要求:
- level: 1=章, 2=节, 3=小节, 4=子小节
- summary: 用中文，不超过40字
- 章节按文档中的出现顺序排列
- 如果文档有目录（TOC），优先参照目录结构"""

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    _call_minimax_api_raw,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.2,
                    max_tokens=8192,
                ),
                timeout=180.0,
            )

            if response:
                # 提取 JSON
                import re as _re
                json_text = response.strip()
                match = _re.search(r'```(?:json)?\s*([\s\S]*?)```', json_text)
                if match:
                    json_text = match.group(1).strip()
                else:
                    match = _re.search(r'\{[\s\S]*\}', json_text)
                    if match:
                        json_text = match.group(0).strip()

                try:
                    parsed = json.loads(json_text)
                    parsed["filename"] = filename
                    parsed["file_id"] = att.get("file_id", "")
                    parsed["status"] = "ok"
                    all_structures.append(parsed)
                except json.JSONDecodeError:
                    all_structures.append({
                        "filename": filename,
                        "file_id": att.get("file_id", ""),
                        "status": "parse_error",
                        "raw_response": response[:1000],
                    })
            else:
                all_structures.append({
                    "filename": filename,
                    "file_id": att.get("file_id", ""),
                    "status": "empty_response",
                    "message": "LLM 返回空结果",
                })

        except asyncio.TimeoutError:
            all_structures.append({
                "filename": filename,
                "file_id": att.get("file_id", ""),
                "status": "timeout",
                "message": "章节分析超时（180秒）",
            })
        except Exception as e:
            all_structures.append({
                "filename": filename,
                "file_id": att.get("file_id", ""),
                "status": "error",
                "message": f"章节分析异常: {str(e)}",
            })

    return json.dumps({
        "status": "ok",
        "analyzed_count": len(all_structures),
        "structures": all_structures,
    }, ensure_ascii=False)


# ── 章节结构提取共享助手 (outline_from_attachment / outline_from_template 复用) ──

class _OutlineExtractError(Exception):
    """文档章节结构提取失败（含超时/解析错误）"""


async def _extract_outline_from_text(
    text_sample: str,
    filename_display: str,
    doc_label: str,
    doc_type: str,
) -> str:
    """从文档全文识别章节结构并补全 subsections/content_points，返回 design_outline 兼容 JSON。

    供 outline_from_attachment / outline_from_template 复用。失败时抛出
    _OutlineExtractError，由调用方格式化为带降级指引的错误 JSON。
    """
    from app.services.minimax import _call_minimax_api_raw

    system_prompt = f"""你是医疗器械注册文档框架分析专家。请分析附件全文，识别其完整的章节结构，
并输出与 design_outline 兼容的框架JSON（支持4级层级）。

## 任务
1. 通读附件全文，识别所有章节标题及其**完整层级关系**（章→节→小节→子小节）
2. 按文档中的出现顺序，提取每一章（level=1 的标题）
3. 为每章补全 sections（节）、subsections（小节）、sub_subsections（子小节，可选）和 content_points
4. 小节从附件原文中识别（如 1.1、1.2 等子标题），无明确子标题时根据内容归纳

## 关键约束
- **必须保留附件原始章节顺序与标题**，不得增删章节或重命名
- 章节标题序号必须连续递增（"第一章"→"第二章"→...），不得重复、不得跳号
- 必须识别出附件的**所有**章节，不得遗漏（即使章节在文档末尾）
- **必须完整保留附件的全部层级深度**：附件有三级标题（如 2.1.1）时输出到 subsections，
  有四级标题（如 2.1.1.1）时输出到 sub_subsections，不得把深层标题拍平或丢弃
- **必须完整保留每章的全部小节**，不得删减小节数量（体系文档一章 5-10 个小节很常见）；
  仅当某一层级小节超过 12 个时，才允许合并语义高度相近的相邻小节并在 title 中注明
- 每个 subsection/sub_subsection 至少2条 content_points，最多6条（从原文提炼，不得编造）
- content_points 应从附件全文中提炼具体要点，不得编造
- 目标文档类型为「{doc_label}」（doc_type={doc_type}），description 中可注明与该文档类型的关联
- description 控制在1-2句话，概括本章主要内容
- key_standards 从全文推断引用的标准，无则留空数组

## 章节识别策略
1. 优先识别明确的章节编号（如"1."、"第一章"、"一、"等），层级由编号深度判断
   （"2"为章、"2.1"为节、"2.1.1"为小节、"2.1.1.1"为子小节）
2. 识别 Markdown 标题（# ## ### #### #####，井号数即层级）
3. 识别 Word 样式标题（如"1.1 目的"）
4. 如有目录（TOC），优先参照目录的层级缩进
5. 合并连续无标题段落为"概述"小节

## 输出格式（严格JSON，无其他文字）
{{
  "doc_title": "附件推断的文档标题",
  "chapters": [{{
    "id": 1,
    "title": "第X章 章节标题（保留附件原标题）",
    "description": "本章主要内容概括",
    "key_standards": ["GB XXXX", "ISO XXXX"],
    "sections": [
      {{
        "title": "X.1 节标题",
        "subsections": [
          {{
            "title": "X.1.1 小节标题",
            "content_points": ["要点1", "要点2"],
            "sub_subsections": [
              {{"title": "X.1.1.1 子小节标题", "content_points": ["要点1", "要点2"]}}
            ]
          }}
        ]
      }}
    ]
  }}]
}}

说明：
- 附件仅两级结构时 sections 可省略，直接用 chapters[].subsections（向后兼容旧格式）
- 附件无四级标题时 sub_subsections 省略或置空数组
- 层级映射：章→chapters，节→sections，小节→subsections，子小节→sub_subsections

只输出 JSON 对象，不要包含 markdown 代码块标记（```）或任何其他文字。"""

    user_prompt = f"""请分析以下附件全文，识别完整的章节结构并补全 subsections 和 content_points。

## 附件文件名
{filename_display}

## 附件全文
{text_sample}"""

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                _call_minimax_api_raw,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=16384,
            ),
            timeout=300.0,
        )
    except asyncio.TimeoutError:
        raise _OutlineExtractError("章节结构识别超时（300秒）。")
    except Exception as e:
        raise _OutlineExtractError(f"章节结构识别失败: {str(e)}。")

    if not response:
        raise _OutlineExtractError("LLM 返回空结果，章节结构识别失败。")

    # 复用 _extract_json 提取并清理 JSON
    outline_str = _extract_json(response)

    # 校验输出可解析
    try:
        parsed = json.loads(outline_str)
        if not parsed.get("chapters"):
            raise ValueError("输出缺少 chapters 字段")
    except (json.JSONDecodeError, ValueError) as e:
        raise _OutlineExtractError(f"章节结构识别输出格式无效: {str(e)}。")

    return outline_str


# ── Tool 8b: outline_from_attachment ──

@tool
async def outline_from_attachment(
    file_id: str = "",
    doc_type: str = "design_development_plan",
    product_name: str = "贴敷式胰岛素泵",
) -> str:
    """基于上传附件的章节结构生成文档框架（附件优先路径）。

    当用户上传参考文档并希望按附件结构生成新文档时调用。
    输出与 design_outline 完全兼容的格式，后续可直接调用 write_chapter 逐章生成。

    与 design_outline 的区别:
    - design_outline 由 LLM 自主设计框架（基于标准法规）
    - outline_from_attachment 复用附件原有章节结构，LLM 仅补全小节和内容要点

    何时用: 用户上传了附件 + 明确选择"按附件结构生成"时。
    降级: 附件无可识别章节时返回 error，Agent 应回退到 design_outline。

    Args:
        file_id: 可选，指定要参照的附件 file_id。为空时自动取第一个有章节结构的附件。
        doc_type: 目标文档类型标识，用于调整小节以适配目标文档类型特有维度。
        product_name: 产品名称，用于生成 doc_title。

    Returns:
        JSON 字符串，格式与 design_outline 一致:
        {"doc_title": "...", "chapters": [{"id", "title", "description",
         "key_standards", "subsections": [{"title", "content_points"}]}]}
        失败时返回 {"status": "error", "message": "..."}
    """
    from app.services.doc_types import DOC_TYPE_LABELS

    doc_label = DOC_TYPE_LABELS.get(doc_type, doc_type)

    # Step 1: 从 _current_attachments 取目标附件
    attachments = _current_attachments.get()
    if not attachments:
        return json.dumps({
            "status": "error",
            "message": "当前没有上传附件。请先上传参考文档，或改用 design_outline 自主设计框架。",
        }, ensure_ascii=False)

    # 确定要使用的附件列表
    if file_id:
        # 指定 file_id: 只用该附件（向后兼容）
        target_att = next((a for a in attachments if a.get("file_id") == file_id), None)
        if not target_att:
            return json.dumps({
                "status": "error",
                "message": f"未找到 file_id={file_id} 的附件。可用附件: {_attachments_hint(attachments)}。请改用 design_outline。",
            }, ensure_ascii=False)
        target_attachments = [target_att]
    else:
        # 未指定 file_id: 使用所有有 full_text 的附件
        target_attachments = [a for a in attachments if a.get("full_text")]

    if not target_attachments:
        return json.dumps({
            "status": "error",
            "message": "未找到可用的附件（所有附件均无文本内容）。请改用 design_outline。",
        }, ensure_ascii=False)

    # Step 2: 截取附件全文送给 LLM
    # 多附件时等额分配 50000 字符预算，确保每个附件都有代表
    TOTAL_BUDGET = 50000
    n = len(target_attachments)
    per_budget = TOTAL_BUDGET // n if n > 0 else TOTAL_BUDGET

    text_parts = []
    filenames = []
    for att in target_attachments:
        fn = att.get("filename", "unknown")
        ft = att.get("full_text", "")
        if not ft or not ft.strip():
            continue
        sample = ft[:per_budget]
        if len(ft) > per_budget:
            print(f"[agent_tools] outline_from_attachment: full_text truncated "
                  f"({len(ft)} -> {per_budget} chars) for '{fn}'")
        text_parts.append(f"=== 附件: {fn} ===\n{sample}")
        filenames.append(fn)

    if not text_parts:
        return json.dumps({
            "status": "error",
            "message": "所有附件均无文本内容。请改用 design_outline。",
        }, ensure_ascii=False)

    text_sample = "\n\n".join(text_parts)
    filename_display = ", ".join(filenames)

    # Step 3: 共享助手一步 LLM 调用，从附件全文识别章节结构并补全 subsections + content_points
    try:
        outline_str = await _extract_outline_from_text(
            text_sample, filename_display, doc_label, doc_type
        )
    except _OutlineExtractError as e:
        return json.dumps({
            "status": "error",
            "message": f"{e}请改用 design_outline。",
        }, ensure_ascii=False)

    parsed = json.loads(outline_str)
    print(f"[agent_tools] outline_from_attachment: "
          f"{len(parsed.get('chapters', []))} chapters from attachment '{att.get('filename', '?')}'")
    return outline_str


# ── Tool 8c: outline_from_template (添加模板功能) ──

@tool
async def outline_from_template(
    template_id: str = "",
    doc_type: str = "design_development_plan",
    product_name: str = "贴敷式胰岛素泵",
) -> str:
    """基于用户添加的模板文档的章节结构生成文档框架（模板优先路径）。

    当用户添加了模板并希望按模板的章节结构和写作风格生成文档时调用。
    输出与 design_outline 完全兼容的格式，后续可直接调用 write_chapter 逐章生成。

    与 outline_from_attachment 的区别:
    - outline_from_attachment 参照的是普通上传附件
    - outline_from_template 参照的是用户通过「添加模板」功能登记的结构/风格模板，
      应同时遵循模板的写作风格（短句、列表、小表格、参数化表达等）

    何时用: 用户添加了模板 + 明确要求"按模板生成/参照模板"时。
    降级: 模板无可识别章节时返回 error，Agent 应回退到 design_outline 或 outline_from_attachment。

    Args:
        template_id: 可选，指定要参照的模板 ID。为空时自动取第一个有章节结构的模板。
        doc_type: 目标文档类型标识，用于调整小节以适配目标文档类型特有维度。
        product_name: 产品名称，用于生成 doc_title。

    Returns:
        JSON 字符串，格式与 design_outline 一致:
        {"doc_title": "...", "chapters": [{"id", "title", "description",
         "key_standards", "subsections": [{"title", "content_points"}]}]}
        失败时返回 {"status": "error", "message": "..."}
    """
    from app.services.doc_types import DOC_TYPE_LABELS

    doc_label = DOC_TYPE_LABELS.get(doc_type, doc_type)

    templates = _current_templates.get()
    if not templates:
        return json.dumps({
            "status": "error",
            "message": "当前没有添加模板。请先通过「添加模板」上传参考文档，"
                       "或改用 design_outline 自主设计框架。",
        }, ensure_ascii=False)

    # 确定要使用的模板列表
    if template_id:
        target = next((t for t in templates if t.get("template_id") == template_id), None)
        if not target:
            return json.dumps({
                "status": "error",
                "message": f"未找到 template_id={template_id} 的模板。可用模板: {_templates_hint(templates)}。请改用 design_outline。",
            }, ensure_ascii=False)
        target_templates = [target]
    else:
        # 未指定 template_id: 使用所有有 full_text 的模板
        target_templates = [t for t in templates if t.get("full_text")]

    if not target_templates:
        return json.dumps({
            "status": "error",
            "message": "未找到可用的模板（所有模板均无文本内容）。请改用 design_outline。",
        }, ensure_ascii=False)

    # 截取模板全文送给 LLM（等额分配 50000 字符预算，确保每个模板都有代表）
    TOTAL_BUDGET = 50000
    n = len(target_templates)
    per_budget = TOTAL_BUDGET // n if n > 0 else TOTAL_BUDGET

    text_parts = []
    names = []
    for tpl in target_templates:
        fn = tpl.get("filename", "unknown")
        ft = tpl.get("full_text", "")
        if not ft or not ft.strip():
            continue
        sample = ft[:per_budget]
        if len(ft) > per_budget:
            print(f"[agent_tools] outline_from_template: full_text truncated "
                  f"({len(ft)} -> {per_budget} chars) for '{fn}'")
        text_parts.append(f"=== 模板: {fn} ===\n{sample}")
        names.append(fn)

    if not text_parts:
        return json.dumps({
            "status": "error",
            "message": "所有模板均无文本内容。请改用 design_outline。",
        }, ensure_ascii=False)

    text_sample = "\n\n".join(text_parts)
    name_display = ", ".join(names)

    # 共享助手一步 LLM 调用，从模板全文识别章节结构并补全 subsections + content_points
    try:
        outline_str = await _extract_outline_from_text(
            text_sample, name_display, doc_label, doc_type
        )
    except _OutlineExtractError as e:
        return json.dumps({
            "status": "error",
            "message": f"{e}请改用 design_outline 或 outline_from_attachment。",
        }, ensure_ascii=False)

    parsed = json.loads(outline_str)
    print(f"[agent_tools] outline_from_template: "
          f"{len(parsed.get('chapters', []))} chapters from template "
          f"'{target_templates[0].get('filename', '?')}'")
    return outline_str


# ── Tool 9: ingest_attachment_to_kb ──

@tool
async def ingest_attachment_to_kb(file_id: str = "") -> str:
    """将用户上传的附件文档转为向量写入主知识库，使其可被 search_kb 检索。

    调用时机:
    - 用户说"把这个文档导入知识库"
    - 用户说"记住这个文档的内容"
    - 用户上传了重要参考资料，希望后续生成文档时能引用
    - Agent 判断附件内容对后续工作有价值时，主动建议导入

    Args:
        file_id: 可选，指定要导入的附件file_id。为空时导入所有已上传的附件。

    Returns:
        JSON格式的导入结果，包含每个文件的chunk数量和导入状态。
    """
    from app.services.rag.ingest import chunk_text
    from app.services.rag.vector_store import VectorStore

    attachments = _current_attachments.get()
    if not attachments:
        return json.dumps({
            "status": "no_attachments",
            "message": "当前没有上传附件。请先上传Word或PDF文档。",
            "results": [],
        }, ensure_ascii=False)

    # 筛选目标附件
    target_attachments = attachments
    if file_id:
        target_attachments = [a for a in attachments if a.get("file_id") == file_id]
        if not target_attachments:
            return json.dumps({
                "status": "not_found",
                "message": f"未找到 file_id={file_id} 的附件。可用附件: {_attachments_hint(attachments)}",
                "results": [],
            }, ensure_ascii=False)

    results = []

    for att in target_attachments:
        filename = att.get("filename", "unknown")
        full_text = att.get("full_text", "")

        if not full_text:
            results.append({
                "filename": filename,
                "file_id": att.get("file_id", ""),
                "status": "no_text",
                "message": "该文件无文本内容，无法导入",
            })
            continue

        # 按段落切分（full_text 已包含 ## 标题标记）
        paragraphs = []
        section_title = ""
        for line in full_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("## "):
                section_title = line.lstrip("#").strip()
            else:
                paragraphs.append((section_title, line))

        if not paragraphs:
            paragraphs = [("", full_text)]

        # 复用现有的分块函数
        chunks = chunk_text(paragraphs)

        # 标记来源
        for i, chunk in enumerate(chunks):
            chunk["doc_type"] = "agent_attachment"
            chunk["source_file"] = filename
            chunk["chunk_id"] = f"att_{att.get('file_id', '?')}_{i}"

        # 写入主知识库
        try:
            vector_store = VectorStore(collection_name="insulin_pump_kb")
            vector_store.add_chunks(chunks)
            # 使 BM25 缓存失效
            VectorStore.invalidate_bm25_cache()

            results.append({
                "filename": filename,
                "file_id": att.get("file_id", ""),
                "status": "ok",
                "chunk_count": len(chunks),
                "message": f"「{filename}」已导入知识库，{len(chunks)} 个分块。后续可通过 search_kb 检索到此文档内容。",
            })
            print(f"[agent_tools] Ingested '{filename}' → insulin_pump_kb ({len(chunks)} chunks)")
        except Exception as e:
            results.append({
                "filename": filename,
                "file_id": att.get("file_id", ""),
                "status": "error",
                "message": f"导入失败: {str(e)}",
            })

    success_count = sum(1 for r in results if r["status"] == "ok")
    return json.dumps({
        "status": "ok",
        "total": len(results),
        "success_count": success_count,
        "results": results,
    }, ensure_ascii=False)


# ── 本地文件系统工具 ──

_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024   # 最大可读取文件大小 (10 MB)
_MAX_READ_LINES = 500                      # 默认最大读取行数


def _safe_resolve_path(user_path: str) -> str:
    """安全解析用户提供的路径，展开 ~ 并转为绝对路径。

    检查路径遍历攻击，拒绝访问文件系统根目录。

    Args:
        user_path: 用户提供的原始路径字符串

    Returns:
        规范化后的绝对路径

    Raises:
        ValueError: 路径为空或指向文件系统根目录
    """
    if not user_path or not user_path.strip():
        raise ValueError("路径不能为空")

    resolved = os.path.abspath(os.path.expanduser(user_path.strip()))

    if resolved == os.path.abspath(os.sep):
        raise ValueError("不允许访问文件系统根目录")

    return resolved


@tool
async def list_local_directory(directory_path: str) -> str:
    """列出指定本地目录的内容（文件与子目录）。

    遍历目录路径，返回所有文件和子目录的列表，包含名称、类型（文件/目录）、
    文件大小（字节）等信息。结果按名称排序，目录优先于文件。

    何时用:
    - 用户在对话中指定了一个本地目录路径，需要查看其内容
    - 用户说"列出这个目录下的文件"、"看看这个文件夹里有什么"
    - 需要选择要读取的文件时，先用此工具浏览目录

    Args:
        directory_path: 要列出内容的本地目录的绝对路径。用户对话中提供的路径。

    Returns:
        JSON格式，包含:
        - status: "ok" | "error" | "not_found"
        - directory_path: 规范化后的绝对路径
        - entries: 条目列表，每项含 name, type, size_bytes
        - total_files: 文件总数
        - total_dirs: 目录总数
    """
    try:
        resolved = _safe_resolve_path(directory_path)

        if not os.path.exists(resolved):
            return json.dumps({
                "status": "not_found",
                "message": f"目录不存在: {resolved}",
                "directory_path": resolved,
            }, ensure_ascii=False)

        if not os.path.isdir(resolved):
            return json.dumps({
                "status": "error",
                "message": (
                    f"路径指向的是一个文件，不是目录，"
                    f"请使用 read_local_file 读取: {resolved}"
                ),
                "directory_path": resolved,
            }, ensure_ascii=False)

        entries = []
        try:
            with os.scandir(resolved) as it:
                for entry in it:
                    item = {
                        "name": entry.name,
                        "type": "dir" if entry.is_dir() else "file",
                    }
                    if entry.is_file():
                        try:
                            item["size_bytes"] = entry.stat().st_size
                        except OSError:
                            item["size_bytes"] = -1
                    entries.append(item)
        except PermissionError:
            return json.dumps({
                "status": "error",
                "message": f"权限不足，无法读取目录: {resolved}",
                "directory_path": resolved,
            }, ensure_ascii=False)

        # 排序: 目录优先，同类按名称排序 (不区分大小写)
        entries.sort(key=lambda e: (0 if e["type"] == "dir" else 1, e["name"].lower()))

        files = [e for e in entries if e["type"] == "file"]
        dirs = [e for e in entries if e["type"] == "dir"]

        return json.dumps({
            "status": "ok",
            "directory_path": resolved,
            "entries": entries,
            "total_files": len(files),
            "total_dirs": len(dirs),
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"读取目录时发生异常: {str(e)}",
        }, ensure_ascii=False)


@tool
async def read_local_file(
    file_path: str,
    start_line: int = 0,
    max_lines: int = 500,
    encoding: str = "utf-8",
) -> str:
    """读取指定本地文件的文本内容。

    支持任意类型的文本文件（代码、文档、配置、日志等），自动检测编码。
    对于大文件，可通过 start_line 和 max_lines 参数控制读取范围，
    避免返回过长内容。

    何时用:
    - 用户在对话中指定了一个本地文件路径，需要读取其内容
    - 用户说"读取这个文件"、"看看这个文件内容"、"打开XXX"
    - 先用 list_local_directory 浏览目录，再用此工具读取具体文件

    Args:
        file_path: 要读取的本地文件的绝对路径。用户对话中提供的路径。
        start_line: 起始行号（从0开始），默认0表示从第一行开始。
        max_lines: 最大读取行数，默认500行。超过此限制会截断并提示。
        encoding: 文件编码，默认 "utf-8"。如读取失败会自动尝试 "gbk" 编码。

    Returns:
        JSON格式，包含:
        - status: "ok" | "error" | "not_found"
        - file_path: 规范化后的绝对路径
        - file_name: 文件名
        - content: 文件文本内容
        - total_lines: 文件总行数
        - start_line: 实际起始行号
        - end_line: 实际结束行号
        - truncated: 是否因超过 max_lines 而被截断
        - size_bytes: 文件大小（字节）
        - encoding_used: 实际使用的编码
    """
    try:
        resolved = _safe_resolve_path(file_path)
        file_name = os.path.basename(resolved)

        if not os.path.exists(resolved):
            return json.dumps({
                "status": "not_found",
                "message": f"文件不存在: {resolved}",
                "file_path": resolved,
            }, ensure_ascii=False)

        if os.path.isdir(resolved):
            return json.dumps({
                "status": "error",
                "message": (
                    f"路径指向的是一个目录，不是文件，"
                    f"请使用 list_local_directory 列出目录内容: {resolved}"
                ),
                "file_path": resolved,
            }, ensure_ascii=False)

        # 文件大小检查
        try:
            file_size = os.path.getsize(resolved)
        except OSError:
            file_size = -1

        if file_size > _MAX_FILE_SIZE_BYTES:
            return json.dumps({
                "status": "error",
                "message": (
                    f"文件过大 ({file_size:,} bytes)，"
                    f"超过最大读取限制 ({_MAX_FILE_SIZE_BYTES:,} bytes ≈ 10 MB)"
                ),
                "file_path": resolved,
                "size_bytes": file_size,
            }, ensure_ascii=False)

        # 编码尝试链
        encodings_to_try = [encoding, "gbk", "latin-1"]
        seen = set()
        encodings_to_try = [e for e in encodings_to_try if not (e in seen or seen.add(e))]

        all_lines = None
        encoding_used = None
        last_error = None

        for enc in encodings_to_try:
            try:
                with open(resolved, "r", encoding=enc) as f:
                    all_lines = f.readlines()
                encoding_used = enc
                break
            except (UnicodeDecodeError, UnicodeError) as e:
                last_error = str(e)
                continue
            except PermissionError:
                return json.dumps({
                    "status": "error",
                    "message": f"权限不足，无法读取文件: {resolved}",
                    "file_path": resolved,
                }, ensure_ascii=False)

        if all_lines is None:
            return json.dumps({
                "status": "error",
                "message": (
                    f"无法解码文件内容，尝试了 {', '.join(encodings_to_try)} 编码均失败。"
                    f"最后错误: {last_error}"
                ),
                "file_path": resolved,
                "size_bytes": file_size if file_size >= 0 else None,
            }, ensure_ascii=False)

        total_lines = len(all_lines)

        # 行范围截取
        actual_start = max(0, min(start_line, total_lines - 1)) if total_lines > 0 else 0
        actual_end = min(actual_start + max_lines, total_lines)
        selected_lines = all_lines[actual_start:actual_end]
        content = "".join(selected_lines)
        truncated = (actual_end < total_lines)

        return json.dumps({
            "status": "ok",
            "file_path": resolved,
            "file_name": file_name,
            "content": content,
            "total_lines": total_lines,
            "start_line": actual_start,
            "end_line": actual_end,
            "truncated": truncated,
            "size_bytes": file_size if file_size >= 0 else None,
            "encoding_used": encoding_used,
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"读取文件时发生异常: {str(e)}",
        }, ensure_ascii=False)


@tool
async def read_folder_file(file_path: str) -> str:
    """读取已上传文件夹中的指定文件完整内容。

    当需要查看文件夹中某个特定文件的完整代码或内容时使用此工具。
    与 search_attachment 的区别：
    - search_attachment 在所有附件中做关键词搜索，适合查找包含特定信息的文件
    - read_folder_file 精确读取指定路径的文件全文，适合需要完整上下文的场景

    使用前建议先查看系统提示中的目录树结构，确认文件路径。

    Args:
        file_path: 文件在文件夹中的相对路径，如 "src/utils/helper.py"。
                   必须与系统提示目录树中的路径一致。

    Returns:
        JSON格式，包含文件完整内容、字符数、文件名等信息。
    """
    attachments = _current_attachments.get()
    if not attachments:
        return json.dumps({
            "status": "no_attachments",
            "message": "当前项目没有已上传的文件夹或附件",
        }, ensure_ascii=False)

    normalized = file_path.strip().lstrip("/").replace("\\", "/")

    # 精确匹配 relative_path
    for att in attachments:
        att_path = (att.get("relative_path", "") or "").replace("\\", "/")
        if att_path == normalized:
            full_text = att.get("full_text", "")
            if not full_text:
                return json.dumps({
                    "status": "no_content",
                    "file_path": normalized,
                    "filename": att.get("filename"),
                    "message": (
                        "该文件为二进制文件或内容为空，无法读取文本内容。"
                        f"状态: {att.get('status', 'unknown')}"
                    ),
                }, ensure_ascii=False)
            return json.dumps({
                "status": "ok",
                "file_path": normalized,
                "filename": att.get("filename"),
                "char_count": len(full_text),
                "content": full_text,
            }, ensure_ascii=False)

    # 模糊匹配: 路径结尾匹配
    candidates = []
    for att in attachments:
        att_path = (att.get("relative_path", "") or "").replace("\\", "/")
        if att_path.endswith(normalized) or normalized in att_path:
            candidates.append(att_path)

    if len(candidates) == 1:
        return await read_folder_file.ainvoke({"file_path": candidates[0]})
    elif len(candidates) > 1:
        return json.dumps({
            "status": "ambiguous",
            "message": f"找到多个匹配路径: {candidates}。请提供更精确的路径。",
        }, ensure_ascii=False)

    return json.dumps({
        "status": "not_found",
        "file_path": normalized,
        "message": (
            f"未找到路径为 '{normalized}' 的文件。"
            "可用路径见系统提示中的目录树，或使用 search_attachment 搜索。"
        ),
    }, ensure_ascii=False)


# ── SQL 数据库查询工具（内置贴敷式胰岛素泵领域库） ──

@tool
async def sql_db_list_tables() -> str:
    """列出内置领域数据库（贴敷式胰岛素泵）中的所有表名。

    何时用: 需要从数据库查询结构化数据（产品/标准/材料/组件/参数/风险）时，
           应最先调用此工具了解数据库有哪些表，再按需查表结构。

    Returns:
        JSON: {"status": "ok", "tables": ["products", ...]}
    """
    try:
        from app.services.sql_db import list_tables
        tables = list_tables()
        return json.dumps({"status": "ok", "tables": tables}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


@tool
async def sql_db_schema(table_names: str) -> str:
    """查看指定表的建表结构与前3行示例数据。

    何时用: 调用 sql_db_list_tables 拿到表名后，在编写 SQL 查询之前，
           先用本工具确认目标表的列名、类型和示例内容，避免查询不存在的列。

    Args:
        table_names: 逗号分隔的表名列表，如 "products, standards"。
           最多展示 6 张表。

    Returns:
        str: 每张表的 CREATE TABLE 语句 + 前3行示例数据，或错误信息。
    """
    try:
        from app.services.sql_db import get_schema
        return get_schema(table_names)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


@tool
async def sql_db_query(query: str) -> str:
    """执行只读 SQL 查询并返回结果（内置贴敷式胰岛素泵领域数据库）。

    何时用: 用户询问结构化数据（如"哪些标准适用于贴敷式胰岛素泵"、
           "哪种材料符合生物相容性要求"、"输注精度限值是多少"）时，
           先 sql_db_list_tables → 再 sql_db_schema → 最后用本工具执行查询。

    Args:
        query: 只读 SQL 查询语句，必须以 SELECT/WITH/EXPLAIN 开头。

    Rules:
        - 只读数据库：INSERT/UPDATE/DELETE/DROP/PRAGMA 等写操作一律被拒绝
        - 结果最多返回 50 行，请用 LIMIT 控制行数
        - 若返回"表不存在"错误，先用 sql_db_schema 查看正确的表名/列名
        - 若返回列名错误，先用 sql_db_schema 查询该表的真实字段

    Returns:
        str: 表头 + 数据行，或明确的错误信息。
    """
    try:
        from app.services.sql_db import run_query
        return run_query(query)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


# ── PostgreSQL 数据库查询工具（用户自有 PG 库，与内置 SQLite 并存） ──

@tool
async def pgsql_list_tables() -> str:
    """列出 PostgreSQL 数据库中的所有用户表名。

    何时用: 用户提到要查询 PostgreSQL/PG 数据库里的数据，或需要从用户自有
           业务库查询结构化数据时，最先调用此工具了解有哪些表。
    与 sql_db_list_tables 的区别: sql_db_* 查内置贴敷式胰岛素泵领域 SQLite 库，
           pgsql_* 查用户配置的 PostgreSQL 库（连接信息在 .env 的 PGSQL_* 变量）。

    Returns:
        str: 表名列表，或"未启用/无表"提示。
    """
    try:
        from app.services.pgsql_client import list_tables
        return await list_tables()
    except Exception as e:
        return f"[pgsql] 列出表失败: {str(e)}"


@tool
async def pgsql_schema(table_names: str) -> str:
    """查看 PostgreSQL 指定表的列名、类型与示例数据。

    何时用: 调用 pgsql_list_tables 拿到表名后，在编写 SQL 查询之前，
           先用本工具确认目标表的列名和示例内容，避免查询不存在的列。

    Args:
        table_names: 逗号分隔的表名列表，如 "orders, customers"。
           最多展示 6 张表。

    Returns:
        str: 每张表的列信息（Markdown 表格）+ 前3行示例数据，或错误信息。
    """
    try:
        from app.services.pgsql_client import get_schema
        return await get_schema(table_names)
    except Exception as e:
        return f"[pgsql] 获取表结构失败: {str(e)}"


@tool
async def pgsql_query(query: str) -> str:
    """对 PostgreSQL 数据库执行只读 SQL 查询（SELECT/WITH/EXPLAIN）。

    何时用: 已通过 pgsql_list_tables + pgsql_schema 确认表名和列名后，
           需要执行具体查询获取数据时。
    规则:
    - 仅允许 SELECT/WITH/EXPLAIN，拒绝任何写操作
    - 单次最多返回 50 行，超出自动截断
    - 查询超时 10 秒

    Args:
        query: SQL 查询语句（SELECT 开头）。

    Returns:
        str: Markdown 表格格式的查询结果，或明确的错误信息。
    """
    try:
        from app.services.pgsql_client import run_query
        return await run_query(query)
    except Exception as e:
        return f"[pgsql] 查询执行失败: {str(e)}"


# ── 计算/统计工具 ──
# 纯函数计算（无 LLM / 无 I/O），为验证/测试报告、可靠性评估等场景
# 提供真实、可追溯的数值，避免 LLM 编造数据。

def _parse_numbers(text) -> list:
    """将数字列表输入解析为 float 列表，兼容 JSON 数组/逗号/空格/分号/换行分隔。"""
    if isinstance(text, (int, float)):
        return [float(text)]
    if isinstance(text, (list, tuple)):
        vals = []
        for v in text:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        return vals
    s = str(text).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            arr = json.loads(s)
            return _parse_numbers(arr)
        except Exception:
            pass
    import re
    parts = re.split(r"[,\s;，；\n]+", s)
    vals = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        try:
            vals.append(float(p))
        except ValueError:
            continue
    return vals


def _z_two_tailed(confidence: float) -> float:
    """根据置信水平返回双侧 z 值（近似查表）。"""
    table = {0.90: 1.645, 0.95: 1.960, 0.975: 2.241, 0.99: 2.576, 0.999: 3.291}
    if confidence in table:
        return table[confidence]
    best = min(table, key=lambda c: abs(c - confidence))
    return table[best]


def _z_one_tailed(power: float) -> float:
    """根据统计功效返回单侧 z 值（近似查表）。"""
    table = {0.80: 0.842, 0.85: 1.036, 0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
    if power in table:
        return table[power]
    best = min(table, key=lambda c: abs(c - power))
    return table[best]


def _normal_cdf(x: float) -> float:
    """标准正态分布 CDF（用误差函数计算）。"""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _t_test_pvalue(t_stat: float, df: float) -> float:
    """计算 t 检验双侧 p 值；优先用 scipy（精确 t 分布），否则正态近似。"""
    try:
        from scipy import stats
        return 2 * (1 - stats.t.cdf(abs(t_stat), df))
    except Exception:
        return 2 * (1 - _normal_cdf(abs(t_stat)))


@tool
def calculate_sample_size(
    method: str,
    confidence: float = 0.95,
    margin: float = 0.0,
    sigma: float = 0.0,
    proportion: float = 0.5,
    delta: float = 0.0,
    power: float = 0.80,
) -> str:
    """计算样本量（验证/测试报告、临床试验、抽样检验等场景）。

    方法 method 取值：
    - "estimate_mean": 估计总体均值，n = (z·σ/E)²，需 sigma（标准差）与 margin（允许误差 E）
    - "estimate_proportion": 估计总体比例，n = z²·p(1-p)/E²，需 proportion（预期比例，默认 0.5 最保守）与 margin
    - "compare_means": 两样本均值比较，每组 n = 2(z_α+z_β)²σ²/Δ²，需 sigma、delta（最小可检出差异）、power（功效）

    何时用: 文档要求说明"样本量如何确定"时（如输注精度测试测多少个样品、
    加速老化测多少个批次），用本工具给出可追溯的样本量依据，而非凭空写一个数。

    Args:
        method: 计算方法（estimate_mean / estimate_proportion / compare_means）
        confidence: 置信水平（0.90 / 0.95 / 0.99），默认 0.95
        margin: 允许误差 E（estimate_mean / estimate_proportion 用）
        sigma: 总体标准差 σ（estimate_mean / compare_means 用）
        proportion: 预期比例 p（estimate_proportion 用，默认 0.5）
        delta: 最小可检出差异 Δ（compare_means 用）
        power: 统计功效（compare_means 用，默认 0.80）

    Returns:
        str: 含计算公式、代入值与结果的说明文本。
    """
    method = (method or "").strip().lower()
    z = _z_two_tailed(confidence)
    if method == "estimate_mean":
        if sigma <= 0 or margin <= 0:
            return "参数错误：estimate_mean 需要 sigma>0 且 margin>0。"
        n = (z * sigma / margin) ** 2
        return (
            "样本量计算结果（估计总体均值）\n"
            f"- 公式: n = (z·σ/E)²\n"
            f"- 置信水平: {confidence:.0%} → z = {z:.3f}\n"
            f"- 标准差 σ = {sigma}\n"
            f"- 允许误差 E = {margin}\n"
            f"- 所需样本量 n = {n:.2f} → 向上取整 **{math.ceil(n)}**"
        )
    if method == "estimate_proportion":
        if not (0 < proportion < 1) or margin <= 0:
            return "参数错误：estimate_proportion 需要 0<proportion<1 且 margin>0。"
        n = (z ** 2) * proportion * (1 - proportion) / (margin ** 2)
        return (
            "样本量计算结果（估计总体比例）\n"
            f"- 公式: n = z²·p(1-p)/E²\n"
            f"- 置信水平: {confidence:.0%} → z = {z:.3f}\n"
            f"- 预期比例 p = {proportion}\n"
            f"- 允许误差 E = {margin}\n"
            f"- 所需样本量 n = {n:.2f} → 向上取整 **{math.ceil(n)}**"
        )
    if method == "compare_means":
        if sigma <= 0 or delta <= 0:
            return "参数错误：compare_means 需要 sigma>0 且 delta>0。"
        zb = _z_one_tailed(power)
        n = 2 * ((z + zb) ** 2) * (sigma ** 2) / (delta ** 2)
        return (
            "样本量计算结果（两样本均值比较）\n"
            f"- 公式: n/组 = 2(z_α + z_β)²σ²/Δ²\n"
            f"- 置信水平: {confidence:.0%} → z_α = {z:.3f}\n"
            f"- 功效: {power:.0%} → z_β = {zb:.3f}\n"
            f"- 标准差 σ = {sigma}\n"
            f"- 最小可检出差异 Δ = {delta}\n"
            f"- 每组样本量 n = {n:.2f} → 向上取整 **{math.ceil(n)}**"
        )
    return f"参数错误：未知 method '{method}'。可选: estimate_mean / estimate_proportion / compare_means。"


@tool
def calculate_process_capability(measurements: str, usl: float, lsl: float) -> str:
    """计算过程能力指数 Cp/Cpk（输注精度、尺寸等关键质量特性的过程能力评估）。

    何时用: 文档要求评估某关键参数的过程能力（如输注精度 Cpk、关键尺寸 Cpk）时，
    用本工具根据实测数据计算 Cp/Cpk，而非凭经验写一个值。

    Args:
        measurements: 测量数据，用逗号/空格/分号分隔，如 "12.3, 12.5, 12.4, 12.6, 12.5"
        usl: 规格上限 USL
        lsl: 规格下限 LSL

    Returns:
        str: 均值、标准差、Cp、Cpk 及是否达标（Cpk≥1.33 为常用接受准则）。
    """
    data = _parse_numbers(measurements)
    if len(data) < 2:
        return "参数错误：measurements 至少需要 2 个数值。"
    if usl <= lsl:
        return "参数错误：usl 必须大于 lsl。"
    mu = statistics.mean(data)
    s = statistics.stdev(data)
    if s == 0:
        return "参数错误：数据标准差为 0，无法计算过程能力（数据全相同）。"
    cp = (usl - lsl) / (6 * s)
    cpu = (usl - mu) / (3 * s)
    cpl = (mu - lsl) / (3 * s)
    cpk = min(cpu, cpl)
    verdict = "达标（Cpk ≥ 1.33）" if cpk >= 1.33 else "未达标（Cpk < 1.33）"
    return (
        "过程能力计算结果\n"
        f"- 样本量 n = {len(data)}\n"
        f"- 均值 μ = {mu:.4f}\n"
        f"- 标准差 σ = {s:.4f}\n"
        f"- Cp = (USL-LSL)/(6σ) = {cp:.3f}\n"
        f"- Cpu = {cpu:.3f}, Cpl = {cpl:.3f}\n"
        f"- Cpk = min(Cpu, Cpl) = **{cpk:.3f}**\n"
        f"- 结论: {verdict}"
    )


@tool
def calculate_reliability(
    method: str,
    total_time: float = 0.0,
    failures: int = 0,
    ea_ev: float = 0.0,
    temp_use_c: float = 0.0,
    temp_accel_c: float = 0.0,
    accel_days: float = 0.0,
    mtbf: float = 0.0,
    time: float = 0.0,
) -> str:
    """可靠性计算（MTBF、Arrhenius 加速老化、可靠度）。

    方法 method 取值：
    - "mtbf": MTBF = 累计运行时间 / 故障数；λ = 1/MTBF。需 total_time、failures
    - "arrhenius": 加速老化换算，AF = exp[(Ea/k)·(1/T_use - 1/T_accel)]。需 ea_ev（活化能 eV）、
      temp_use_c（实际使用温度℃）、temp_accel_c（加速温度℃）、accel_days（加速天数）
    - "reliability": 可靠度 R(t) = exp(-t/MTBF)。需 mtbf、time

    何时用: 可靠性文档、加速老化验证、有效期评估等需要给出 MTBF / 加速因子 / 可靠度时。

    Args:
        method: 计算方法（mtbf / arrhenius / reliability）
        total_time: 累计运行时间（小时，mtbf 用）
        failures: 故障数（mtbf 用）
        ea_ev: 活化能 Ea（eV，arrhenius 用，常见 0.5~1.0）
        temp_use_c: 实际使用温度（℃，arrhenius 用）
        temp_accel_c: 加速老化温度（℃，arrhenius 用）
        accel_days: 加速老化天数（arrhenius 用）
        mtbf: MTBF（小时，reliability 用）
        time: 目标时间（小时，reliability 用）

    Returns:
        str: 含公式、代入值与结果的说明文本。
    """
    method = (method or "").strip().lower()
    k = 8.617333e-5  # 玻尔兹曼常数 eV/K
    if method == "mtbf":
        if failures <= 0:
            return "参数错误：mtbf 需要 failures>0。"
        mtbf_val = total_time / failures
        lam = failures / total_time
        return (
            "可靠性计算结果（MTBF）\n"
            f"- 公式: MTBF = 累计运行时间 / 故障数\n"
            f"- 累计运行时间 = {total_time} 小时\n"
            f"- 故障数 = {failures}\n"
            f"- MTBF = **{mtbf_val:.2f} 小时**\n"
            f"- 失效率 λ = {lam:.6f} /小时"
        )
    if method == "arrhenius":
        if ea_ev <= 0 or accel_days <= 0:
            return "参数错误：arrhenius 需要 ea_ev>0 且 accel_days>0。"
        t_use = temp_use_c + 273.15
        t_accel = temp_accel_c + 273.15
        if t_use <= 0 or t_accel <= t_use:
            return "参数错误：温度需合理（加速温度应高于使用温度）。"
        af = math.exp((ea_ev / k) * (1 / t_use - 1 / t_accel))
        real_days = accel_days * af
        return (
            "可靠性计算结果（Arrhenius 加速老化）\n"
            f"- 公式: AF = exp[(Ea/k)·(1/T_use - 1/T_accel)]\n"
            f"- 活化能 Ea = {ea_ev} eV\n"
            f"- 使用温度 T_use = {t_use:.1f} K（{temp_use_c}℃）\n"
            f"- 加速温度 T_accel = {t_accel:.1f} K（{temp_accel_c}℃）\n"
            f"- 加速因子 AF = **{af:.2f}**\n"
            f"- 加速 {accel_days} 天 ≈ 等效实际 **{real_days:.1f} 天**（{real_days / 365:.2f} 年）"
        )
    if method == "reliability":
        if mtbf <= 0 or time < 0:
            return "参数错误：reliability 需要 mtbf>0 且 time≥0。"
        r = math.exp(-time / mtbf)
        return (
            "可靠性计算结果（可靠度）\n"
            f"- 公式: R(t) = exp(-t/MTBF)\n"
            f"- MTBF = {mtbf} 小时\n"
            f"- 目标时间 t = {time} 小时\n"
            f"- 可靠度 R(t) = **{r:.6f}**（{r:.2%}）"
        )
    return f"参数错误：未知 method '{method}'。可选: mtbf / arrhenius / reliability。"


@tool
def calculate_statistics(
    method: str,
    data: str = "",
    sample1: str = "",
    sample2: str = "",
    alpha: float = 0.05,
) -> str:
    """描述统计与假设检验。

    方法 method 取值：
    - "descriptive": 描述统计（均值/中位数/标准差/极差/95%置信区间）。需 data
    - "t_test": 独立两样本 t 检验（Welch 校正，比较两组均值差异是否显著）。需 sample1、sample2

    何时用: 需要汇总一组测量数据的统计量，或比较两组测试数据是否有显著差异时。

    Args:
        method: 计算方法（descriptive / t_test）
        data: 数据（descriptive 用，逗号/空格/分号分隔）
        sample1: 第一组样本（t_test 用）
        sample2: 第二组样本（t_test 用）
        alpha: 显著性水平（t_test 用，默认 0.05）

    Returns:
        str: 统计结果说明。
    """
    method = (method or "").strip().lower()
    if method == "descriptive":
        d = _parse_numbers(data)
        if not d:
            return "参数错误：descriptive 需要至少 1 个数值。"
        n = len(d)
        mu = statistics.mean(d)
        med = statistics.median(d)
        if n >= 2:
            s = statistics.stdev(d)
            z = _z_two_tailed(0.95)
            ci = z * s / math.sqrt(n)
        else:
            s = 0.0
            ci = 0.0
        return (
            "描述统计结果\n"
            f"- 样本量 n = {n}\n"
            f"- 均值 = {mu:.4f}\n"
            f"- 中位数 = {med:.4f}\n"
            f"- 标准差 = {s:.4f}\n"
            f"- 最小值 = {min(d):.4f}, 最大值 = {max(d):.4f}\n"
            f"- 极差 = {max(d) - min(d):.4f}\n"
            f"- 95% 置信区间: [{mu - ci:.4f}, {mu + ci:.4f}]"
        )
    if method == "t_test":
        a = _parse_numbers(sample1)
        b = _parse_numbers(sample2)
        if len(a) < 2 or len(b) < 2:
            return "参数错误：t_test 需要两组样本各至少 2 个数值。"
        ma = statistics.mean(a)
        mb = statistics.mean(b)
        va = statistics.variance(a)
        vb = statistics.variance(b)
        na = len(a)
        nb = len(b)
        se = math.sqrt(va / na + vb / nb)
        if se == 0:
            return "参数错误：两组数据方差为 0，无法进行 t 检验。"
        t = (ma - mb) / se
        df = ((va / na + vb / nb) ** 2) / (
            (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
        )
        p = _t_test_pvalue(t, df)
        sig = "显著" if p < alpha else "不显著"
        return (
            "独立两样本 t 检验结果（Welch 校正）\n"
            f"- 组1: n={na}, 均值={ma:.4f}, 方差={va:.4f}\n"
            f"- 组2: n={nb}, 均值={mb:.4f}, 方差={vb:.4f}\n"
            f"- 均值差 = {ma - mb:.4f}\n"
            f"- t 统计量 = {t:.4f}\n"
            f"- 自由度 df ≈ {df:.2f}\n"
            f"- p 值 ≈ {p:.4f}\n"
            f"- 显著性水平 α = {alpha}\n"
            f"- 结论: 在 α={alpha} 水平下，两组均值差异**{sig}**"
        )
    return f"参数错误：未知 method '{method}'。可选: descriptive / t_test。"


# ── 补充提示词生成工具 ──
# 当用户提出编写文档的具体要求或对当前文档的修改意见时，主代理调用此工具，
# 将用户要求转化为一套结构化的「补充提示词」。这些补充提示词会被**追加**到
# 各文档生成工具（generate_section / revise_section / revise_paragraph / write_chapter）
# 的 system_prompt 末尾，作为对原有提示词的补充（不覆盖、不破坏原有提示词）。

_SUPPLEMENTARY_SYSTEM_PROMPT = """你是文档生成提示词工程师。用户提出了一些文档编写要求或修改意见，你的任务是把这些要求转化为一套清晰、具体、可执行的「补充提示词」。

这些补充提示词会被**追加**到原有文档生成提示词的末尾，作为对原有提示词的补充。因此：

1. 只输出「补充要求」本身，不要重复原有提示词中已有的通用规则（如"内容专业""用中文""符合NMPA"等）
2. 每条补充要求要具体、可操作，明确指出"应该怎么做"或"不要怎么做"
3. 用简洁的要点列表表达，每条一行，以 `- ` 开头
4. 严格保留用户要求的原意，不要擅自扩展或缩小范围，不要臆造用户未提及的要求
5. 只输出补充提示词正文，不要输出任何解释、前言、JSON 围栏或 markdown 代码块"""


# 合并模式系统提示词：已有累积补充提示词时，将最新要求与旧版合并消解为一套完整版本
# （整体替换旧版，避免新旧冲突指令共存注入生成任务）
_SUPPLEMENTARY_MERGE_SYSTEM_PROMPT = """你是文档生成提示词工程师。用户提出了**新的**文档编写要求或修改意见，同时存在此前累积的补充提示词。你的任务是把两者合并为一套**完整、无内部冲突**的「补充提示词」（它将整体替换旧版本）。

合并规则：

1. **最新优先**：用户最新要求与已有补充提示词冲突时，一律以最新要求为准——删除或改写被覆盖的旧条目，合并结果中不得残留任何与最新要求矛盾的表述
2. 去重：语义重复的条目只保留一条
3. 与最新要求无关、且不冲突的已有条目原样保留（可微调措辞使其通顺）
4. 只输出「补充要求」本身，不要重复原有文档生成提示词中已有的通用规则
5. 每条补充要求要具体、可操作，用简洁的要点列表表达，每条一行，以 `- ` 开头
6. 严格保留用户要求的原意，不要擅自扩展或缩小范围，不要臆造用户未提及的要求
7. 只输出合并后的完整补充提示词正文，不要输出任何解释、前言、JSON 围栏或 markdown 代码块"""


@tool
async def generate_supplementary_prompt(
    requirement: str,
    doc_type: str = "design_development_plan",
) -> str:
    """将用户提出的文档编写要求或修改意见转化为一套「补充提示词」。

    当用户提出以下需求时调用此工具：
    - 对文档编写提出额外要求（如"风险等级用中文不用英文"、"表格统一用三线表"）
    - 对已生成文档提出修改意见（如"把严重度分级改成3级"、"增加EO灭菌验证要求"）
    - 指定特定格式、风格、术语、字数、结构等要求

    生成的补充提示词会被**追加**到文档生成工具的原有提示词末尾，
    作为对原有提示词的补充（不会覆盖或破坏原有提示词）。
    若此前已累积过补充提示词，本工具会自动将最新要求与旧版**合并消解**
    （冲突处以最新要求为准，旧冲突条目作废），返回合并后的完整版本整体替换旧版。

    Args:
        requirement: 用户的原始要求或修改意见（完整原文，尽量原样传入）
        doc_type: 文档类型标识，从当前会话状态的 doc_type 字段获取

    Returns:
        JSON 字符串，含 status、supplementary_prompt、merged 字段。
        supplementary_prompt 为补充提示词正文；merged=true 时表示该正文已是
        与历史补充提示词合并消解后的完整版，系统将用它整体替换旧版本。
    """
    import re  # 修复既有bug: 下方围栏清理用到 re.sub，但本函数此前未导入 re（文件惯例为函数内局部导入）

    from app.services.minimax import _call_minimax_api_raw
    from app.services.doc_types import DOC_TYPE_LABELS

    doc_label = DOC_TYPE_LABELS.get(doc_type, doc_type)

    # 读取已累积的补充提示词（每轮由 _sync_doc_context 从 state 同步到 contextvar）
    existing = (_current_supplementary_prompts.get() or "").strip()

    if existing:
        # 合并模式：最新要求 + 旧版补充提示词 → 消解冲突后的完整版（整体替换）
        system_prompt = _SUPPLEMENTARY_MERGE_SYSTEM_PROMPT
        user_prompt = (
            f"文档类型：{doc_label}\n\n"
            f"已有的补充提示词（此前累积，可能含与最新要求冲突的旧条目）：\n{existing}\n\n"
            f"用户的最新要求/修改意见：\n{requirement}\n\n"
            f"请把最新要求与已有补充提示词合并为一套完整、无冲突的补充提示词"
            f"（冲突处以最新要求为准）："
        )
    else:
        system_prompt = _SUPPLEMENTARY_SYSTEM_PROMPT
        user_prompt = (
            f"文档类型：{doc_label}\n\n"
            f"用户的原始要求/修改意见：\n{requirement}\n\n"
            f"请把上述要求转化为一套补充提示词（追加到原有提示词末尾）："
        )

    try:
        result = _call_minimax_api_raw(
            system_prompt,
            user_prompt,
            temperature=0.3,
            max_tokens=2048,
            timeout=(30, 120),
        )
        sp_text = (result or "").strip()
        if not sp_text:
            return json.dumps({
                "status": "error",
                "message": "补充提示词生成失败：API 返回空结果。",
            }, ensure_ascii=False)
        # 去掉可能残留的 markdown 围栏
        sp_text = re.sub(r"^```(?:markdown)?\s*\n?", "", sp_text)
        sp_text = re.sub(r"\n?```\s*$", "", sp_text)
        return json.dumps({
            "status": "ok",
            "supplementary_prompt": sp_text,
            "merged": bool(existing),
            "requirement": requirement[:200],
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"补充提示词生成异常: {str(e)}",
        }, ensure_ascii=False)


# ── 文档语言风格切换工具 ──
# 用户在聊天中口头要求切换风格（如"以后文档写精炼点"）时，主代理调用此工具，
# 结果由 _after_tools_node 同步写入 state.writing_style，system prompt 的
# 风格断言随状态刷新，后续章节生成/修改按新风格执行。

_WRITING_STYLE_ALIASES = {
    "concise": "concise", "detailed": "detailed",
    "精炼": "concise", "简洁": "concise", "精简": "concise", "精炼简洁": "concise",
    "详细": "detailed", "严谨": "detailed", "详尽": "detailed", "严谨详细": "detailed",
}


@tool
async def set_writing_style(style: str) -> str:
    """更新文档语言风格（writing_style 会话状态）。

    当用户在对话中明确要求切换文档语言风格时调用，例如：
    - "以后文档写精炼一点/简洁一些" → style="concise"
    - "文档要严谨详细/写详细一点" → style="detailed"

    此工具只改变**文档内容生成**的语言风格，不影响聊天回复风格。
    更新后立即写入会话状态，后续所有章节生成/修改按新风格执行。

    Args:
        style: 目标风格。标准值为 "concise"（精炼简洁）或 "detailed"（严谨详细），
               也接受中文别名（精炼/简洁/精简/详细/严谨/详尽）。

    Returns:
        JSON 字符串，含 status 和 writing_style 字段。
    """
    s = _WRITING_STYLE_ALIASES.get((style or "").strip().lower())
    if not s:
        s = _WRITING_STYLE_ALIASES.get((style or "").strip())
    if s not in ("concise", "detailed"):
        return json.dumps({
            "status": "error",
            "message": f"无效风格 '{style}'，可选: concise(精炼简洁) / detailed(严谨详细)",
        }, ensure_ascii=False)
    label = "精炼简洁" if s == "concise" else "严谨详细"
    return json.dumps({
        "status": "ok",
        "writing_style": s,
        "message": f"文档语言风格已切换为「{label}」，后续文档生成按新风格执行。",
    }, ensure_ascii=False)


# ── 模板风格分析工具 ──
# 用户上传模板后，主代理调用此工具：读模板正文，用 LLM 分析提炼结构化写作风格总结，
# 结果经 _after_tools_node 写入 state.template_style_summary，后续 write_chapter 优先注入。

_TEMPLATE_STYLE_ANALYZE_SYSTEM = """你是文档写作风格分析专家。请分析给定的模板文档正文，提炼其写作风格，输出结构化的风格总结。

总结应涵盖以下方面（但不限于）：
1. 句式特点：句长偏好（短句/长句）、是否大量使用列表项
2. 段落密度：每段句数、是否分段细碎
3. 列表与表格使用：是否大量使用项目符号列表、表格的密度与风格
4. 措辞语气：正式/精炼/详尽、是否有固定句式（如"支持X功能""参数：Y""协议：Z"）
5. 术语与编号：术语风格、章节/条款编号习惯
6. 详略程度：要点式精炼还是充分展开

输出要求：
- 用简洁的要点列表（每条以 `- ` 开头），每条给出具体、可执行的风格描述
- 控制在 500 字以内
- 直接输出风格总结正文，不要输出解释、前言、JSON 围栏或 markdown 代码块"""


@tool
async def analyze_template_style() -> str:
    """分析已添加的模板文档，提炼写作风格总结。

    当用户上传模板后应调用：通读模板全文，分析提炼出该模板的写作风格
    （句式/段落/列表表格/措辞/术语/详略），形成结构化风格总结写入会话状态，
    后续 write_chapter 生成章节时优先按该总结模仿模板风格。

    与直接注入模板原文相比，风格总结更精炼、指导性更强，避免长模板占用过多上下文。

    Returns:
        JSON 字符串，含 status 和 style_summary 字段。
        style_summary 为提炼出的风格总结正文，由系统写入会话状态供后续生成注入。
    """
    templates = _current_templates.get()
    if not templates:
        return json.dumps({
            "status": "error",
            "message": "当前没有已添加的模板。请先通过「添加模板」上传参考文档。",
        }, ensure_ascii=False)

    # 核心分析逻辑抽出为 _analyze_template_style_core（与 write_chapter 懒加载共用）
    summary = await _analyze_template_style_core()
    if not summary:
        return json.dumps({
            "status": "error",
            "message": "风格分析失败：模板无文本内容或 API 返回空结果。",
        }, ensure_ascii=False)
    n_with_text = sum(1 for t in templates if (t.get("full_text") or "").strip())
    return json.dumps({
        "status": "ok",
        "style_summary": summary,
        "template_count": n_with_text,
    }, ensure_ascii=False)


# ── 工具列表导出 ──

PHASE1_TOOLS = [
    search_kb,
    search_attachment,
    search_template,
    modify_attachment,
    enrich_attachment,
    summarize_attachment,
    web_search,
    set_document_format,
    find_kb_reference_files,
    add_kb_files_as_attachment,
    analyze_document_structure,
    ingest_attachment_to_kb,
    generate_search_query,
    generate_section,
    revise_section,
    revise_paragraph,
    generate_supplementary_prompt,
    set_writing_style,
    analyze_template_style,
    build_docx,
    design_outline,
    outline_from_attachment,
    outline_from_template,
    write_chapter,
    update_outline,
    summarize_section,
    summarize_document,
    # SQL 领域数据库查询（2026-08-11 集成）
    sql_db_list_tables,
    sql_db_schema,
    sql_db_query,
    # PostgreSQL 数据库查询（2026-08-18 集成）
    pgsql_list_tables,
    pgsql_schema,
    pgsql_query,
    # 本地文件系统工具
    list_local_directory,
    read_local_file,
    read_folder_file,
    # 计算/统计工具（2026-08-19 集成）
    calculate_sample_size,
    calculate_process_capability,
    calculate_reliability,
    calculate_statistics,
]
