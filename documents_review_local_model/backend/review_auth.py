"""
review_auth — 文档审核 Agent 服务的用户鉴权与会话归属隔离（combination 移植新增）

复用体系文档管理系统（Spring Boot, JwtUtil）签发的 JWT：以共享密钥做 HS256
验签，从 sub claim 取用户名（与 design_planning_generation_local_model 的
app/services/agent_auth.py 同一模式，本模块按审核服务的平铺模块结构简化）。

审核会话（conversation session）归属登记在独立 SQLite 表 session_owners：

  SPA fetch ──Authorization: Bearer <UM JWT>──▶ require_user ──验签──▶ username
                                                    │
  /api/{agent,multi-agent}/conversation/** ──▶ require_session_access
        ├─ path 参数或 Form 体中的 session_id
        ├─ 已登记 owner==user            ──▶ 放行
        ├─ 已登记 owner!=user            ──▶ 403（禁止跨用户读消息/重审/导出）
        ├─ 未登记且 POST（会话创建/续用） ──▶ 登记归属（先到先得）后放行
        └─ 未登记且非 POST（读流/状态）   ──▶ 放行（会话不存在由端点自身提示）

  SSE 流端点同样是 GET + session_id 路径参数 → 依赖内校验；前端 fetch 流式
  读取可携带 Authorization 头（EventSource 无法带头的替代方案）。

会话本体存于内存 dict（服务重启即失），归属表落在 checkpoints/review_owners.db
（持久化，防重启后同 ID 被他人抢注）。密钥来源：环境变量 UM_JWT_SECRET
（与 Spring 的 ${UM_JWT_SECRET:...} 占位共用），默认值为 application.properties
中的存量密钥，保证不设置环境变量时行为一致。
"""
import os
import asyncio
import datetime
from pathlib import Path
from typing import Optional

import jwt
import sqlite3
from fastapi import HTTPException, Request

# 与 user_management/backend application.properties 的 app.jwt.secret 保持一致
_DEFAULT_SECRET = "insulin-pump-employee-mgmt-secret-key-2026-please-change-in-production"

# 归属表所在库：backend/checkpoints/review_owners.db（测试可直接改写本模块变量）
_OWNERS_DB_PATH: Optional[str] = None


def _secret() -> str:
    """JWT 验签密钥：环境变量优先，回退存量默认值"""
    return os.environ.get("UM_JWT_SECRET") or _DEFAULT_SECRET


def _db_file() -> str:
    global _OWNERS_DB_PATH
    if _OWNERS_DB_PATH:
        return _OWNERS_DB_PATH
    _OWNERS_DB_PATH = str(Path(__file__).parent / "checkpoints" / "review_owners.db")
    return _OWNERS_DB_PATH


def _conn() -> sqlite3.Connection:
    """短连接（沿用项目内 sqlite timeout=5 惯例）"""
    return sqlite3.connect(_db_file(), timeout=5)


def verify_token(authorization: Optional[str]) -> str:
    """校验 Authorization: Bearer <JWT>，返回用户名（sub claim）

    Raises:
        HTTPException 401: 缺失/格式错误/签名不符/已过期
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少登录凭证，请先登录体系管理系统")
    token = authorization[len("Bearer "):].strip()
    try:
        # HMAC 家族全放行：Spring jjwt 依据密钥字节数自动选 HS256/384/512；
        # 非对称与 none 被拒绝（无算法混淆风险，三者验签均使用同一共享密钥）
        payload = jwt.decode(token, _secret(), algorithms=["HS256", "HS384", "HS512"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录体系管理系统")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录凭证无效，请重新登录")
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="登录凭证缺少用户标识，请重新登录")
    return username


async def init_owner_table() -> None:
    """建表（幂等）：session_owners 归属表 + session_meta 会话元数据表

    session_meta（P0 优化 2026-10-13 新增）：支撑 /api/sessions 会话列表与
    刷新/重启后的会话恢复。mode 区分 single（单 Agent）/ multi（多 Agent）。
    """
    def _c():
        os.makedirs(os.path.dirname(_db_file()), exist_ok=True)
        with _conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS session_owners ("
                " session_id TEXT PRIMARY KEY,"
                " username TEXT NOT NULL,"
                " created_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS session_meta ("
                " session_id TEXT PRIMARY KEY,"
                " username TEXT NOT NULL,"
                " mode TEXT NOT NULL DEFAULT 'single',"
                " filename TEXT NOT NULL DEFAULT '',"
                " audit_type TEXT NOT NULL DEFAULT '',"
                " section_count INTEGER NOT NULL DEFAULT 0,"
                " created_at TEXT NOT NULL,"
                " updated_at TEXT NOT NULL)"
            )
    await asyncio.to_thread(_c)


# ============== 会话元数据 CRUD（/api/sessions 支撑） ==============

_META_COLS = ("session_id", "username", "mode", "filename",
              "audit_type", "section_count", "created_at", "updated_at")


async def upsert_session_meta(
    session_id: str, username: str, mode: str = "single",
    filename: str = "", audit_type: str = "", section_count: int = 0,
) -> None:
    """新建/更新会话元数据（会话创建与恢复时调用）"""
    def _w():
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with _conn() as conn:
            conn.execute(
                "INSERT INTO session_meta (session_id, username, mode, filename,"
                " audit_type, section_count, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET"
                "  mode=excluded.mode, filename=excluded.filename,"
                "  audit_type=excluded.audit_type,"
                "  section_count=excluded.section_count, updated_at=excluded.updated_at",
                (session_id, username, mode, filename, audit_type,
                 int(section_count), now, now),
            )
    await asyncio.to_thread(_w)


async def touch_session_meta(session_id: str) -> None:
    """刷新会话 updated_at（发消息/恢复会话时调用，驱动列表排序）"""
    def _w():
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with _conn() as conn:
            conn.execute(
                "UPDATE session_meta SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
    await asyncio.to_thread(_w)


async def get_session_meta(session_id: str) -> Optional[dict]:
    """单条会话元数据；不存在返回 None"""
    def _q():
        with _conn() as conn:
            cur = conn.execute(
                "SELECT %s FROM session_meta WHERE session_id = ?" % ",".join(_META_COLS),
                (session_id,),
            )
            row = cur.fetchone()
            return dict(zip(_META_COLS, row)) if row else None
    return await asyncio.to_thread(_q)


async def list_session_meta(username: str) -> list:
    """某用户的全部会话元数据（updated_at 倒序）"""
    def _q():
        with _conn() as conn:
            cur = conn.execute(
                "SELECT %s FROM session_meta WHERE username = ?"
                " ORDER BY updated_at DESC" % ",".join(_META_COLS),
                (username,),
            )
            return [dict(zip(_META_COLS, row)) for row in cur.fetchall()]
    return await asyncio.to_thread(_q)


async def delete_session_rows(session_id: str) -> None:
    """删除会话的归属与元数据行（调用方须已完成归属校验）"""
    def _w():
        with _conn() as conn:
            conn.execute("DELETE FROM session_meta WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM session_owners WHERE session_id = ?", (session_id,))
    await asyncio.to_thread(_w)


async def get_owner(session_id: str) -> Optional[str]:
    """查询会话归属用户名；未登记返回 None"""
    def _q():
        with _conn() as conn:
            cur = conn.execute(
                "SELECT username FROM session_owners WHERE session_id = ?", (session_id,))
            row = cur.fetchone()
            return row[0] if row else None
    return await asyncio.to_thread(_q)


async def require_user(request: Request) -> str:
    """FastAPI 依赖：仅认证（适用于无会话语义的 /api 端点）"""
    return verify_token(request.headers.get("authorization"))


async def require_session_access(request: Request) -> str:
    """FastAPI 依赖：认证 + 会话归属校验

    session_id 来源：路径参数（stream/state/report/{session_id}）或
    Form 体（start/message/reaudit 等 POST）。语义对齐 agent_auth 的
    require_project_access：
    - 已登记且非本人 → 403
    - 未登记且为 POST → 登记归属（先到先得）
    - 未登记且非 POST → 放行（会话不存在由端点自身返回提示）
    """
    username = verify_token(request.headers.get("authorization"))
    await init_owner_table()

    sid = request.path_params.get("session_id")
    if not sid and request.method == "POST":
        try:
            form = await request.form()
            sid = form.get("session_id") if form else None
        except Exception:
            sid = None
    if not sid:
        # 无会话语义的请求（不应发生于此依赖，但保持宽容）：仅认证
        return username
    sid = str(sid)

    owner = await get_owner(sid)
    if owner is not None:
        if owner != username:
            raise HTTPException(status_code=403, detail="无权访问该审核会话")
        return username
    if request.method == "POST":
        def _claim():
            with _conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO session_owners (session_id, username, created_at) "
                    "VALUES (?, ?, ?)",
                    (sid, username,
                     datetime.datetime.now().isoformat(timespec="seconds")))
                cur = conn.execute(
                    "SELECT username FROM session_owners WHERE session_id = ?", (sid,))
                return cur.fetchone()[0]
        actual = await asyncio.to_thread(_claim)
        if actual != username:
            raise HTTPException(status_code=403, detail="无权访问该审核会话")
    return username
