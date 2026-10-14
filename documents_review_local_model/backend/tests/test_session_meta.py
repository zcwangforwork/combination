# -*- coding: utf-8 -*-
"""session_meta 会话元数据 + P0 新端点守卫测试（P0 优化新增）

1. review_auth.session_meta CRUD：upsert / get / list 排序 / touch / delete
   （updated_at 粒度为秒，排序断言用直接 SQL 铺垫可辨识时间戳）
2. 守卫（源码级扫描，不 import main.py —— 其模块级会加载 ChromaDB/LangGraph）：
   - P0 新增 8 个端点全部存在且挂对鉴权依赖
   - SSE 流端点签名含 from_seq 回放参数
   - /api/sessions GET 必须 require_user（列表隔离靠查询条件，不是端点参数）
"""
import asyncio
import io
import re
import sqlite3
from pathlib import Path

import pytest

import review_auth
from review_auth import (
    delete_session_rows, get_session_meta, init_owner_table,
    list_session_meta, touch_session_meta, upsert_session_meta,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    """每个测试用独立临时库（避免污染 checkpoints/review_owners.db）"""
    db = tmp_path / "review_owners.db"
    monkeypatch.setattr(review_auth, "_OWNERS_DB_PATH", str(db))
    yield db


def _set_updated_at(db, sid, ts):
    with sqlite3.connect(str(db)) as conn:
        conn.execute("UPDATE session_meta SET updated_at = ? WHERE session_id = ?",
                     (ts, sid))


# ── 1. session_meta CRUD ──────────────────────────────────────

def test_upsert_and_get_roundtrip():
    async def scenario():
        await init_owner_table()
        await upsert_session_meta("s1", "alice", mode="single",
                                  filename="risk.docx",
                                  audit_type="risk_management", section_count=7)
        row = await get_session_meta("s1")
        assert row is not None
        assert row["username"] == "alice"
        assert row["mode"] == "single"
        assert row["filename"] == "risk.docx"
        assert row["audit_type"] == "risk_management"
        assert row["section_count"] == 7
        assert await get_session_meta("nope") is None
    asyncio.run(scenario())


def test_upsert_conflict_updates_fields():
    async def scenario():
        await init_owner_table()
        await upsert_session_meta("s1", "alice", mode="single",
                                  filename="a.docx", section_count=1)
        # 同 id 再写：模式与文件名更新（恢复/续用场景）
        await upsert_session_meta("s1", "alice", mode="multi",
                                  filename="b.docx", section_count=9)
        row = await get_session_meta("s1")
        assert row["mode"] == "multi"
        assert row["filename"] == "b.docx"
        assert row["section_count"] == 9
    asyncio.run(scenario())


def test_list_orders_by_updated_at_desc_and_filters_user(_temp_db):
    async def scenario():
        await init_owner_table()
        await upsert_session_meta("s-old", "alice")
        await upsert_session_meta("s-new", "alice")
        await upsert_session_meta("s-bob", "bob")
    asyncio.run(scenario())
    # updated_at 粒度是秒：用 SQL 铺垫可辨识时间戳
    _set_updated_at(_temp_db, "s-old", "2026-10-13T10:00:00")
    _set_updated_at(_temp_db, "s-new", "2026-10-13T11:00:00")

    async def check():
        rows = await list_session_meta("alice")
        assert [r["session_id"] for r in rows] == ["s-new", "s-old"]
        assert await list_session_meta("carol") == []
    asyncio.run(check())


def test_touch_updates_updated_at(_temp_db):
    async def scenario():
        await init_owner_table()
        await upsert_session_meta("s1", "alice")
    asyncio.run(scenario())
    _set_updated_at(_temp_db, "s1", "2026-10-13T08:00:00")

    async def scenario2():
        await touch_session_meta("s1")
        row = await get_session_meta("s1")
        assert row["updated_at"] > "2026-10-13T08:00:00"
        # 不存在的行 touch 不报错（幂等）
        await touch_session_meta("ghost")
    asyncio.run(scenario2())


def test_delete_removes_meta_and_owner_rows():
    async def scenario():
        await init_owner_table()
        await upsert_session_meta("s1", "alice")
        with sqlite3.connect(str(review_auth._db_file())) as conn:
            conn.execute(
                "INSERT INTO session_owners VALUES ('s1', 'alice', '2026-10-13')")
        await delete_session_rows("s1")
        assert await get_session_meta("s1") is None
        assert await review_auth.get_owner("s1") is None
    asyncio.run(scenario())


# ── 2. P0 新端点守卫（源码级扫描） ─────────────────────────────

def _scan_routes():
    src = io.open(BACKEND_DIR / "main.py", encoding="utf-8").read()
    out = []
    for m in re.finditer(r'@app\.(get|post|delete)\("(/api/[^"]+)"([^\n]*)', src):
        out.append((m.group(2), m.group(3)))
    return dict(out)


def test_guard_p0_endpoints_exist_with_right_deps():
    routes = _scan_routes()
    session_scoped = [
        "/api/agent/conversation/stream/status/{session_id}",
        "/api/agent/conversation/history/{session_id}",
        "/api/agent/conversation/restore/{session_id}",
        "/api/multi-agent/conversation/stream/status/{session_id}",
        "/api/multi-agent/conversation/history/{session_id}",
        "/api/multi-agent/conversation/restore/{session_id}",
    ]
    for p in session_scoped:
        assert p in routes, f"缺少端点 {p}"
        assert "require_session_access" in routes[p], f"{p} 缺少会话归属校验"

    assert "/api/sessions" in routes
    assert "require_user" in routes["/api/sessions"], \
        "/api/sessions 列表必须挂 require_user（用户隔离靠 list_session_meta 查询条件）"


def test_guard_stream_endpoints_support_from_seq():
    """SSE 流端点签名必须带 from_seq 查询参数（断线回放入口）"""
    src = io.open(BACKEND_DIR / "main.py", encoding="utf-8").read()
    for name in ("conversation_stream", "multi_agent_conversation_stream"):
        m = re.search(rf"async def {name}\(session_id: str[^\)]*\)", src)
        assert m, f"未找到 {name} 定义"
        assert "from_seq" in m.group(0), f"{name} 缺少 from_seq 参数"
