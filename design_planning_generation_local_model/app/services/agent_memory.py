"""
Agent Long-Term Memory — 基于 PostgreSQL + pgvector 的语义长期记忆

依据 LangChain / LangGraph 长期记忆文档实现:
- https://docs.langchain.com/oss/python/langchain/long-term-memory
- https://docs.langchain.com/oss/python/langgraph/add-memory#add-long-term-memory

使用 LangGraph 的 AsyncPostgresStore（langgraph-checkpoint-postgres）作为持久化存储，
通过 pgvector 向量检索实现跨会话语义召回。与现有 OpenViking 记忆（capture/recall）
互补：OpenViking 侧重会话级活动存档，本模块侧重长期、跨项目的稳定记忆。

三类长期记忆（命名空间 "memories" 下的子命名空间）:
- semantic    — 语义事实（用户偏好、项目背景、产品信息等长期事实）
- episodic    — 情景经历（历史会话中的关键事件与决策）
- procedural  — 流程规则（用户明确的规则 / 偏好 / 指令）

每条记忆 value: {"text": <检索文本>, "type": <记忆类型>, "thread_id": <会话ID>, "created_at": <ISO时间>}
向量检索字段: "text"（见 index.fields）。

pgvector 维度约束说明:
    qwen3-embedding:4b 输出 2560 维，而 pgvector 的 HNSW / IVFFlat 索引上限为 2000 维。
    因此 index 使用 kind="flat"（精确检索、不建 ANN 索引，规避 2000 维上限），
    配合 distance_type="cosine" 做余弦相似度排序。向量列本身支持 16000 维，2560 无问题。
"""
import asyncio
import json
import os
import re
import time
from datetime import datetime
from typing import Optional

from langchain_openai import OpenAIEmbeddings
from langgraph.store.postgres import AsyncPostgresStore

# ── 环境变量默认值 ──

_DEFAULT_DB_URI = "postgresql://postgres:123456@localhost:5432/postgres"
_DEFAULT_DIMS = 2560  # qwen3-embedding:4b 输出维度
_DEFAULT_EMBED_MODEL = "qwen3-embedding:4b"
_DEFAULT_OLLAMA_URL = "http://localhost:11435"

# ── 单例状态 ──

_memory_store: Optional[AsyncPostgresStore] = None
_memory_ctx = None  # from_conn_string() 返回的异步上下文管理器（pool 生命周期由它托管）
_init_attempted = False  # 记录是否已尝试初始化，失败后不再反复重试


def _enabled() -> bool:
    """是否启用长期记忆（LONG_TERM_MEMORY_ENABLED=true，默认关闭以保持向后兼容）。"""
    return os.getenv("LONG_TERM_MEMORY_ENABLED", "false").lower() in ("1", "true", "yes", "on")


def is_ltm_enabled() -> bool:
    """公开判断：长期记忆是否启用（供 SSE 事件门控等外部调用）。"""
    return _enabled()


def _build_index_config() -> dict:
    """构建 pgvector 语义检索索引配置。

    kind="flat" 规避 pgvector HNSW/IVFFlat 的 2000 维上限（2560 维 embedding）。
    """
    dims = int(os.getenv("LONG_TERM_MEMORY_EMBED_DIMS", str(_DEFAULT_DIMS)))
    embed_model = os.getenv("OLLAMA_EMBED_MODEL", _DEFAULT_EMBED_MODEL)
    base_url = os.getenv("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_URL).rstrip("/") + "/v1"
    api_key = os.getenv("MINIMAX_API_KEY", "ollama")

    embeddings = OpenAIEmbeddings(
        model=embed_model,
        base_url=base_url,
        api_key=api_key,
        # Ollama 的 OpenAI 兼容 /v1/embeddings 只接受字符串/字符串数组输入，
        # 不接受 tiktoken 的 token-ID 数组。关闭 ctx-length 检查可让
        # embed_documents 直接发送原始文本（list[str]），规避 "invalid input type"。
        check_embedding_ctx_length=False,
    )

    return {
        "dims": dims,
        "embed": embeddings,
        "fields": ["text"],  # 仅对 value["text"] 做向量化
        "ann_index_config": {"kind": "flat", "vector_type": "vector"},
        "distance_type": "cosine",
    }


async def get_memory_store() -> Optional[AsyncPostgresStore]:
    """获取或创建 AsyncPostgresStore 单例（含 setup 建表/迁移）。

    失败或未启用时返回 None，调用方静默降级。持久连接池由 _memory_ctx 托管，
    应用关闭时由 close_memory_store() 释放。
    """
    global _memory_store, _memory_ctx, _init_attempted

    if not _enabled():
        return None

    if _memory_store is None and not _init_attempted:
        _init_attempted = True
        try:
            conn_string = os.getenv("LONG_TERM_MEMORY_DB_URI", _DEFAULT_DB_URI)
            index = _build_index_config()

            # 使用连接池以支撑并发请求；from_conn_string 返回异步上下文管理器，
            # 我们保持其打开（mirror agent_state.get_checkpointer 的写法），
            # pool 在 close_memory_store() 时随 __aexit__ 释放。
            _memory_ctx = AsyncPostgresStore.from_conn_string(
                conn_string,
                pool_config={"min_size": 1, "max_size": 5},
                index=index,
            )
            _memory_store = await _memory_ctx.__aenter__()
            await _setup_store(_memory_store, conn_string, index)
            print(f"[agent_memory] Long-term memory store ready "
                  f"(dims={index['dims']}, kind=flat, distance=cosine)")
        except Exception as e:
            _memory_store = None
            _memory_ctx = None
            print(f"[agent_memory] Long-term memory init failed (non-fatal): "
                  f"{type(e).__name__}: {e}")

    return _memory_store


async def _setup_store(store: AsyncPostgresStore, conn_string: str, index: dict) -> None:
    """建表/迁移，并绕过 langgraph-checkpoint-postgres 3.1.2 的 async setup bug。

    该版本 AsyncPostgresStore.setup() 忽略了 Migration.condition，导致 kind="flat"
    （不建 ANN 索引，规避 pgvector 2000 维上限）仍尝试执行索引迁移并抛出
    ``ValueError: Invalid index_type for pgvector: flat``。此时 store / store_vectors
    表其实已建好，只需把该（无需的）flat 索引迁移标记为已应用即可。
    """
    try:
        await store.setup()
    except ValueError as e:
        if "index_type" in str(e) and "flat" in str(e):
            await _mark_vector_migrations_applied(conn_string, upto=2)
            print("[agent_memory] flat-index migration marked applied (kind=flat workaround)")
        else:
            raise


async def _mark_vector_migrations_applied(conn_string: str, upto: int) -> None:
    """将 vector_migrations 版本标记到 upto（幂等），使 store.setup() 向量迁移为空操作。"""
    from psycopg import AsyncConnection
    async with await AsyncConnection.connect(conn_string, autocommit=True) as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS vector_migrations (v INTEGER PRIMARY KEY)"
        )
        for v in range(upto + 1):
            await conn.execute(
                "INSERT INTO vector_migrations (v) VALUES (%s) ON CONFLICT (v) DO NOTHING",
                (v,),
            )


async def close_memory_store():
    """关闭长期记忆存储（应用关闭时调用）。"""
    global _memory_store, _memory_ctx, _init_attempted
    if _memory_ctx:
        try:
            await _memory_ctx.__aexit__(None, None, None)
        except Exception:
            pass
        _memory_ctx = None
    _memory_store = None
    _init_attempted = False


# ── 命名空间与 key ──

_VALID_TYPES = ("semantic", "episodic", "procedural")


def _namespace(memory_type: str) -> tuple[str, ...]:
    """记忆类型 → 命名空间 ("memories", <type>)。"""
    return ("memories", memory_type)


def _make_key(memory_type: str, thread_id: str = "") -> str:
    """生成唯一 key。同一轮对话内 timestamp 精度到毫秒 + 类型 + 会话ID 保证唯一。"""
    thread_part = (thread_id or "global").replace("/", "_")
    return f"{memory_type}-{thread_part}-{int(time.time() * 1000)}"


# ── 记忆读写 ──

async def store_memory(
    text: str,
    memory_type: str = "episodic",
    thread_id: str = "",
) -> bool:
    """写入一条长期记忆。

    Args:
        text: 记忆正文（用于向量检索，会截断到 2000 字符以内避免超长）。
        memory_type: semantic | episodic | procedural。
        thread_id: 关联会话ID（无则空串，表示跨会话全局记忆）。

    Returns:
        True 成功写入，False 未启用 / 失败（静默降级）。
    """
    text = (text or "").strip()
    if not text:
        return False
    if memory_type not in _VALID_TYPES:
        memory_type = "episodic"

    store = await get_memory_store()
    if store is None:
        return False

    try:
        await store.aput(
            _namespace(memory_type),
            _make_key(memory_type, thread_id),
            {
                "text": text[:2000],
                "type": memory_type,
                "thread_id": thread_id or "",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        return True
    except Exception as e:
        print(f"[agent_memory] store_memory failed (non-fatal): {type(e).__name__}: {e}")
        return False


async def search_memories(
    query: str,
    limit: int = 5,
    memory_types: Optional[list[str]] = None,
) -> list[dict]:
    """语义检索长期记忆。

    在 ("memories",) 前缀下检索所有记忆类型，按余弦相似度排序。

    Args:
        query: 自然语言查询（用于向量检索）。
        limit: 返回条数上限。
        memory_types: 限定记忆类型（None 表示全部）。

    Returns:
        [{"text": str, "type": str, "thread_id": str, "score": float, "created_at": str}, ...]
    """
    query = (query or "").strip()
    if not query:
        return []

    store = await get_memory_store()
    if store is None:
        return []

    try:
        results = await store.asearch(("memories",), query=query, limit=limit)
    except Exception as e:
        print(f"[agent_memory] search_memories failed (non-fatal): {type(e).__name__}: {e}")
        return []

    out = []
    for item in results:
        value = getattr(item, "value", {}) or {}
        mtype = value.get("type", "")
        if memory_types and mtype not in memory_types:
            continue
        out.append({
            "text": value.get("text", ""),
            "type": mtype,
            "thread_id": value.get("thread_id", ""),
            "score": float(getattr(item, "score", 0.0) or 0.0),
            "created_at": value.get("created_at", ""),
        })
    return out


# ── 记忆上下文格式化 ──

_TYPE_LABELS = {
    "semantic": "语义事实",
    "episodic": "情景经历",
    "procedural": "流程规则",
}


def format_memory_context(memories: list[dict]) -> str:
    """将检索到的记忆格式化为注入 system prompt 的记忆块。

    与 OpenViking 的 memory_context 块风格一致，最终在 _agent_node 中合并注入。
    """
    if not memories:
        return ""

    lines = [
        "## 长期记忆（来自 PostgreSQL 语义检索）",
        "以下是从历史长期记忆中检索到的相关信息，可作为当前对话的参考：",
        "",
    ]
    used = 0
    for i, mem in enumerate(memories):
        text = (mem.get("text") or "").strip()
        if not text:
            continue
        mtype = mem.get("type", "episodic")
        label = _TYPE_LABELS.get(mtype, mtype)
        score = mem.get("score", 0.0)
        lines.append(f"### 记忆 {i + 1}（{label}，相关度: {score:.2f}）")
        lines.append(text[:600])  # 截断，避免占用过多 context window
        lines.append("")
        used += 1

    if used == 0:
        return ""
    return "\n".join(lines)


# ── 自动捕获 ──

async def capture_conversation_turn(user_text: str, assistant_text: str, thread_id: str = "") -> int:
    """从一轮对话中自动沉淀长期记忆（静默降级）。

    策略（轻量、可解释）:
    - 情景记忆: 保存「用户提问 → agent 回答」的浓缩摘录（仅当用户提问足够实质）。
    - 流程规则: 识别用户明确的规则/偏好表述（如"以后…"、"记住…"、"偏好…"），
      单独存为 procedural 记忆，便于后续长期遵循。

    Returns:
        本次新捕获的记忆条数（0 表示未捕获/失败）。
    """
    user_text = (user_text or "").strip()
    if not user_text:
        return 0

    captured = 0

    # 1. 情景记忆：用户提问足够实质（≥12 字且非纯工具性短语）时保存
    if len(user_text) >= 12:
        snippet = f"用户: {user_text[:400]}"
        if assistant_text and assistant_text.strip():
            snippet += f"\nAgent: {(assistant_text.strip())[:400]}"
        if await store_memory(snippet, memory_type="episodic", thread_id=thread_id):
            captured += 1

    # 2. 流程规则：显式偏好/规则表述单独沉淀为 procedural
    if _looks_like_rule(user_text):
        if await store_memory(user_text[:2000], memory_type="procedural", thread_id=thread_id):
            captured += 1

    return captured


_RULE_MARKERS = ("以后", "记住", "请记住", "偏好", "每次都", "务必", "必须", "不要", "禁止", "统一")


def _looks_like_rule(text: str) -> bool:
    """判断文本是否像一条明确的流程规则/偏好表述。"""
    t = (text or "").strip()
    if len(t) < 8:
        return False
    return any(t.startswith(m) or m in t[:24] for m in _RULE_MARKERS)


# ── 原子化记忆沉淀（LLM 提炼 + 去重） ──

_DEDUP_THRESHOLD = float(os.getenv("LTM_DEDUP_THRESHOLD", "0.9"))  # 相似度 ≥ 此值判为近似重复

_ATOMIC_EXTRACT_SYSTEM = """你是记忆提炼助手。从一轮对话中提炼出值得长期记住的原子化记忆。
每条记忆 = 一个独立的、可复用的结论/事实/决策/规则，供未来跨会话召回。
输出严格 JSON 数组，每项: {"text": "一句话记忆", "type": "semantic|episodic|procedural"}。
规则:
- 只提炼有价值、可复用的信息（用户偏好、项目背景、产品参数、标准条款、明确的规则/决策）；闲聊或一次性内容不提炼
- text 简洁完整、自包含（脱离对话上下文也能看懂），≤120 字
- type 判定: procedural=用户明确的规则/偏好/指令（"以后""记住""必须""不要"等）；semantic=长期事实（产品/项目/标准/偏好）；episodic=本次关键决策或事件
- 无可提炼内容时输出 []
- 只输出 JSON，不要任何解释或代码围栏
"""


async def _extract_atomic_memories(user_text: str, assistant_text: str) -> list:
    """调用本地 LLM 将一轮对话提炼为原子化记忆列表（失败返回空列表）。"""
    from app.services.minimax import _call_minimax_api_raw

    user_prompt = f"用户: {user_text[:1000]}\nAgent: {assistant_text[:1000]}"
    try:
        raw = await asyncio.to_thread(
            _call_minimax_api_raw,
            system_prompt=_ATOMIC_EXTRACT_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=1024,
        )
    except Exception:
        return []

    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
    if not isinstance(data, list):
        return []

    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        mtype = (item.get("type") or "episodic").strip()
        if not text:
            continue
        if mtype not in _VALID_TYPES:
            mtype = "episodic"
        out.append({"text": text[:2000], "type": mtype})
    return out


async def _is_duplicate(text: str, memory_type: str, threshold: float = _DEDUP_THRESHOLD) -> bool:
    """判断新记忆是否与已存记忆近似重复（避免重复占用召回名额）。"""
    existing = await search_memories(text, limit=3, memory_types=[memory_type])
    for m in existing:
        if float(m.get("score") or 0.0) >= threshold:
            return True
    return False


async def capture_conversation_turn_atomic(user_text: str, assistant_text: str, thread_id: str = "") -> int:
    """原子化沉淀一轮对话到长期记忆（静默降级）。

    流程：LLM 提炼原子化记忆 → 逐条去重 → 写入。LLM 提炼为空/失败时，
    回退到标记式 procedural 规则沉淀（保留原 capture_conversation_turn 的规则捕获能力）。

    Returns:
        本次新捕获的记忆条数（0 表示未捕获/失败）。
    """
    user_text = (user_text or "").strip()
    if not user_text:
        return 0

    captured = 0
    memories = await _extract_atomic_memories(user_text, assistant_text or "")
    for mem in memories:
        if await _is_duplicate(mem["text"], mem["type"]):
            continue
        if await store_memory(mem["text"], memory_type=mem["type"], thread_id=thread_id):
            captured += 1

    # 兜底：LLM 提炼无产出时，仍保留原标记式规则沉淀
    if captured == 0 and _looks_like_rule(user_text):
        if await store_memory(user_text[:2000], memory_type="procedural", thread_id=thread_id):
            captured += 1

    return captured
