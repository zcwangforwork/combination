"""
agent_auth — Agent 服务的用户鉴权与项目归属隔离（combination 移植新增）

复用体系文档管理系统（Spring Boot, JwtUtil）签发的 JWT：以共享密钥做 HS256
验签，从 sub claim 取用户名（JwtUtil.generateToken 的 subject 即登录名）。
项目（LangGraph thread）归属记录在与 checkpoint 同库的 project_owners 表：

  SPA fetch ──Authorization: Bearer <UM JWT>──▶ require_user ──验签──▶ username
                                                    │
  /agent/projects/{pid}/... ──▶ require_project_access
        ├─ 已登记 owner==user            ──▶ 放行
        ├─ 已登记 owner!=user            ──▶ 403（禁止跨用户读/删/续写）
        └─ 未登记：POST（首次写入）       ──▶ 登记归属后放行
                    非 POST（读/删）     ──▶ 放行（新项目空态；存量已由迁移脚本划归 admin）
缺失/无效/过期凭证 ──▶ 401（前端提示重新登录）

密钥来源：环境变量 UM_JWT_SECRET（与 Spring 的 ${UM_JWT_SECRET:...} 占位共用），
默认值为 application.properties 中的存量密钥，保证不设置环境变量时行为一致。
"""
import os
import sqlite3
import asyncio
import datetime
from typing import Optional

import jwt
from fastapi import HTTPException, Request

# 与 user_management/backend application.properties 的 app.jwt.secret 保持一致
_DEFAULT_SECRET = "insulin-pump-employee-mgmt-secret-key-2026-please-change-in-production"

# 归属表所在库：默认与 checkpoint 同库（agent_state 初始化后记录的模块级路径），
# 测试可通过直接改写本模块级变量指向临时库。
_OWNERS_DB_PATH: Optional[str] = None


def _secret() -> str:
    """JWT 验签密钥：环境变量优先，回退存量默认值"""
    return os.environ.get("UM_JWT_SECRET") or _DEFAULT_SECRET


def _db_file() -> str:
    """project_owners 表所在 SQLite 文件（与 checkpoint 库同库同目录）"""
    global _OWNERS_DB_PATH
    if _OWNERS_DB_PATH:
        return _OWNERS_DB_PATH
    from pathlib import Path
    from app.services import agent_state as _agent_state
    db_path = getattr(_agent_state, "_db_path", None)
    if not db_path:
        project_root = Path(__file__).parent.parent.parent
        db_path = str(project_root / "project_store" / "agent_checkpoints.db")
    _OWNERS_DB_PATH = db_path
    return db_path


def _conn() -> sqlite3.Connection:
    """短连接（沿用项目内 sqlite timeout=5 惯例）"""
    return sqlite3.connect(_db_file(), timeout=5)


async def init_owner_table() -> None:
    """建表（幂等）"""
    def _c():
        with _conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS project_owners ("
                " thread_id TEXT PRIMARY KEY,"
                " username TEXT NOT NULL,"
                " created_at TEXT NOT NULL)"
            )
    await asyncio.to_thread(_c)


async def get_owner(thread_id: str) -> Optional[str]:
    """查询项目归属用户名；未登记返回 None"""
    def _q():
        with _conn() as conn:
            cur = conn.execute(
                "SELECT username FROM project_owners WHERE thread_id = ?", (thread_id,))
            row = cur.fetchone()
            return row[0] if row else None
    return await asyncio.to_thread(_q)


async def list_owned_threads(username: str) -> list:
    """列出某用户拥有的全部 thread_id（按最新活动倒序；GROUP BY 去重——
    checkpoints 每线程多行，无去重会重复返回同一项目）"""
    def _q():
        with _conn() as conn:
            cur = conn.execute(
                "SELECT c.thread_id FROM checkpoints c "
                "JOIN project_owners o ON o.thread_id = c.thread_id "
                "WHERE o.username = ? AND c.checkpoint_ns = '' AND c.thread_id != '' "
                "GROUP BY c.thread_id ORDER BY MAX(c.rowid) DESC",
                (username,))
            return [row[0] for row in cur.fetchall()]
    return await asyncio.to_thread(_q)


def verify_token(authorization: Optional[str]) -> str:
    """校验 Authorization: Bearer <JWT>，返回用户名（sub claim）

    Raises:
        HTTPException 401: 缺失/格式错误/签名不符/已过期
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少登录凭证，请先登录体系管理系统")
    token = authorization[len("Bearer "):].strip()
    try:
        # HMAC 家族全放行：Spring jjwt 的 signWith(key) 依据密钥字节数自动选
        # HS256/384/512（当前 65 字节密钥 → HS512）；轮换 UM_JWT_SECRET 变更
        # 密钥长度时算法会随之变化。非对称与 none 仍被拒绝（无算法混淆风险，
        # 三者验签均使用同一共享密钥）
        payload = jwt.decode(token, _secret(), algorithms=["HS256", "HS384", "HS512"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录体系管理系统")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录凭证无效，请重新登录")
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="登录凭证缺少用户标识，请重新登录")
    return username


def verify_token_identity(authorization: Optional[str]) -> tuple:
    """校验凭证并返回 (username, is_admin)（role claim == 'ADMIN' 判定管理员）。

    知识库作用域等需要角色信息的调用方使用；仅认证场景用 verify_token。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少登录凭证，请先登录体系管理系统")
    token = authorization[len("Bearer "):].strip()
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256", "HS384", "HS512"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录体系管理系统")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录凭证无效，请重新登录")
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="登录凭证缺少用户标识，请重新登录")
    return username, payload.get("role") == "ADMIN"


async def require_user(request: Request) -> str:
    """FastAPI 依赖：仅认证（适用于非项目级 /agent 端点）"""
    return verify_token(request.headers.get("authorization"))


async def require_project_access(project_id: str, request: Request) -> str:
    """FastAPI 依赖：认证 + 项目归属校验（路径参数 project_id 由 FastAPI 自动注入）

    - 已登记且非本人 → 403
    - 未登记且为 POST（首次写入）→ 登记归属（先到先得）
    - 未登记且非 POST → 放行（新项目空态/不存在的项目由端点自身返回 404 或空数据）
    """
    username = verify_token(request.headers.get("authorization"))
    await init_owner_table()
    owner = await get_owner(project_id)
    if owner is not None:
        if owner != username:
            raise HTTPException(status_code=403, detail="无权访问该项目")
        return username
    if request.method == "POST":
        def _claim():
            with _conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO project_owners (thread_id, username, created_at) "
                    "VALUES (?, ?, ?)",
                    (project_id, username,
                     datetime.datetime.now().isoformat(timespec="seconds")))
                cur = conn.execute(
                    "SELECT username FROM project_owners WHERE thread_id = ?", (project_id,))
                return cur.fetchone()[0]
        actual = await asyncio.to_thread(_claim)
        if actual != username:
            raise HTTPException(status_code=403, detail="无权访问该项目")
    return username
