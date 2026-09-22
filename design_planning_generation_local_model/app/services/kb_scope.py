"""
kb_scope — 知识库用户隔离的作用域解析（2026-09-21 新增）

存储布局：
  chroma_db_insulin_pump/        共享：贴敷式胰岛素泵专用知识库（全体可检索）
  chroma_db_users/<username>/    各登录用户个人知识库（仅本人与 ADMIN 可检索）

作用域规则：
  普通用户 → [共享库] + [本人库]
  ADMIN    → [共享库] + [全部个人库]
  无上下文（旧版表单模式等无登录场景）→ [共享库]

Agent 请求的作用域经 ContextVar 传递：在 /messages 等 Agent 入口端点设置；
asyncio.create_task / to_thread 均会复制上下文，故后台生成任务内创建的
VectorStore 在查询时按当前用户解析检索目标，多用户并发互不串扰
（替代 VectorStore.EXTRA_DB_CONFIG 类级全局，后者无法按请求区分）。
"""
import contextvars
import re
from pathlib import Path
from typing import Optional, Tuple

_PROJECT_ROOT = Path(__file__).parent.parent.parent
SHARED_DB_DIR = str(_PROJECT_ROOT / "chroma_db_insulin_pump")
USERS_KB_ROOT = _PROJECT_ROOT / "chroma_db_users"

# 个人库与共享库上传 collection 的实际名称（VectorStore 前缀 + "uploads"）
UPLOADS_COLLECTION = "qms_doc_uploads"
# 共享库检索目标（历史行为：脚本摄入的标准库 + 页面上传库）
SHARED_QUERY_COLLECTIONS = ["insulin_pump_kb", "qms_doc_uploads"]

_kb_user: contextvars.ContextVar = contextvars.ContextVar(
    "kb_user", default=None)  # (username, is_admin) | None


def set_kb_user(username: str, is_admin: bool) -> None:
    """在请求入口设置当前知识库用户上下文（随请求/后台任务传播）"""
    _kb_user.set((username, bool(is_admin)))


def get_kb_user() -> Optional[Tuple[str, bool]]:
    return _kb_user.get()


def _safe_name(username: str) -> str:
    """目录名净化：仅允许字母数字与 _ . -（防路径注入）；纯点名（./..）强制前缀"""
    name = re.sub(r"[^0-9A-Za-z_.-]", "_", username) or "anonymous"
    if name in (".", ".."):
        name = "_" + name
    return name


def user_kb_dir(username: str) -> str:
    """当前用户个人知识库目录（不存在则创建）"""
    d = USERS_KB_ROOT / _safe_name(username)
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def list_user_kb_dirs() -> list:
    """已存在的全部个人知识库目录（按目录名排序）"""
    if not USERS_KB_ROOT.exists():
        return []
    return [str(p) for p in sorted(USERS_KB_ROOT.iterdir()) if p.is_dir()]


def query_targets() -> dict:
    """按当前上下文解析检索目标 {db_path: [collection_names]}。

    共享库始终在列；普通用户附本人库；ADMIN 附全部个人库；
    无上下文仅共享库（安全默认，fail-closed）。
    """
    targets = {SHARED_DB_DIR: list(SHARED_QUERY_COLLECTIONS)}
    ctx = _kb_user.get()
    if not ctx:
        return targets
    username, is_admin = ctx
    if is_admin:
        for d in list_user_kb_dirs():
            targets[d] = [UPLOADS_COLLECTION]
    else:
        targets[user_kb_dir(username)] = [UPLOADS_COLLECTION]
    return targets


def scoped_kb_stores() -> list:
    """当前作用域内全部 uploads 库的 VectorStore 实例（共享库在前）。

    供工具/端点遍历多库检索或按 source_file 查找文件。
    """
    from app.services.rag.vector_store import VectorStore
    stores = []
    for db_path, colls in query_targets().items():
        if UPLOADS_COLLECTION not in colls:
            continue
        stores.append(VectorStore(collection_name="uploads", persist_directory=db_path))
    return stores


def personal_kb_store():
    """当前用户的个人库（写入目标）；无上下文回退共享库（旧版表单模式）。

    供 ingest_attachment_to_kb、kb 上传等写入方使用。
    """
    from app.services.rag.vector_store import VectorStore
    ctx = get_kb_user()
    if ctx:
        return VectorStore(collection_name="uploads", persist_directory=user_kb_dir(ctx[0]))
    return VectorStore(collection_name="uploads")
