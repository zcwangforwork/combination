"""agent_retention 单元测试（2026-09-29）

覆盖：过期删除（三表）/ 新近保留 / 关闭开关 / 无归属行的孤儿线程 /
created_at 兜底口径 / 活跃流跳过 / 内部命名空间跳过 / 空库不崩。
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import msgpack
import pytest

from app.services import agent_retention

ISO = "%Y-%m-%dT%H:%M:%S.%f+00:00"


def _ts(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime(ISO)


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    """每个测试独立临时库（对齐真实 langgraph 表结构的最小形态）"""
    db = tmp_path / "agent_checkpoints.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE checkpoints ("
        " thread_id TEXT, checkpoint_ns TEXT DEFAULT '',"
        " checkpoint_id TEXT, parent_checkpoint_id TEXT,"
        " type TEXT, checkpoint BLOB, metadata BLOB)")
    conn.execute(
        "CREATE TABLE writes (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT)")
    conn.execute(
        "CREATE TABLE project_owners ("
        " thread_id TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(agent_retention, "_RETENTION_DB_PATH", str(db))
    yield db


def _ckpt(db, tid: str, ts: str, ns: str = "", blob=None):
    """插一行 checkpoint（blob 默认带 ts；blob=None 显式传 bytes 可造无 ts 场景）"""
    payload = blob if blob is not None else msgpack.packb(
        {"v": 4, "id": "cp1", "ts": ts}, use_bin_type=True)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id,"
        " parent_checkpoint_id, type, checkpoint, metadata)"
        " VALUES (?, ?, 'cp1', NULL, 'msgpack', ?, x'7B7D')",
        (tid, ns, payload))
    conn.commit()
    conn.close()


def _owner(db, tid: str, created_at: str, username: str = "alice"):
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT OR IGNORE INTO project_owners VALUES (?, ?, ?)", (tid, username, created_at))
    conn.commit()
    conn.close()


def _counts(db, tid: str):
    conn = sqlite3.connect(str(db))
    try:
        c = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id=?",
                         (tid,)).fetchone()[0]
        w = conn.execute("SELECT COUNT(*) FROM writes WHERE thread_id=?",
                         (tid,)).fetchone()[0]
        o = conn.execute("SELECT COUNT(*) FROM project_owners WHERE thread_id=?",
                         (tid,)).fetchone()[0]
        return c, w, o
    finally:
        conn.close()


def test_old_thread_deleted_recent_kept(db, monkeypatch):
    monkeypatch.setenv("AGENT_CHAT_RETENTION_DAYS", "60")
    _ckpt(db, "old", _ts(90)); _owner(db, "old", _ts(90))     # 90 天前 → 删
    _ckpt(db, "new", _ts(1));  _owner(db, "new", _ts(1))      # 1 天前 → 留
    stats = agent_retention.sweep_once()
    assert stats["expired"] == 1 and stats["deleted"] == 1
    assert _counts(db, "old") == (0, 0, 0)      # 三表同清，无孤儿行
    assert _counts(db, "new") == (1, 0, 1)


def test_disabled_by_env_zero(db, monkeypatch):
    monkeypatch.setenv("AGENT_CHAT_RETENTION_DAYS", "0")
    _ckpt(db, "old", _ts(365)); _owner(db, "old", _ts(365))
    stats = agent_retention.sweep_once()
    assert stats.get("disabled") is True
    assert _counts(db, "old") == (1, 0, 1)


def test_ownerless_old_thread_deleted(db, monkeypatch):
    """认证功能上线前的无归属线程：只要最后活动过期同样清理"""
    monkeypatch.setenv("AGENT_CHAT_RETENTION_DAYS", "60")
    _ckpt(db, "orphan", _ts(100))
    stats = agent_retention.sweep_once()
    assert stats["deleted"] == 1
    assert _counts(db, "orphan") == (0, 0, 0)


def test_fallback_to_created_at(db, monkeypatch):
    """blob 无 ts（解析不出）时回退 project_owners.created_at 定龄"""
    monkeypatch.setenv("AGENT_CHAT_RETENTION_DAYS", "60")
    _ckpt(db, "by_owner", _ts(0), blob=msgpack.packb({"v": 4, "id": "cp1"}))
    _owner(db, "by_owner", _ts(90))            # 创建于 90 天前 → 删
    _ckpt(db, "recent_owner", _ts(0), blob=msgpack.packb({"v": 4, "id": "cp1"}))
    _owner(db, "recent_owner", _ts(2))         # 创建于 2 天前 → 留
    stats = agent_retention.sweep_once()
    assert stats["deleted"] == 1
    assert _counts(db, "by_owner") == (0, 0, 0)
    assert _counts(db, "recent_owner")[0] == 1


def test_no_ts_no_owner_kept(db, monkeypatch):
    """完全无法定龄 → 保守保留，绝不盲删"""
    monkeypatch.setenv("AGENT_CHAT_RETENTION_DAYS", "60")
    _ckpt(db, "mystery", _ts(0), blob=msgpack.packb({"v": 4, "id": "cp1"}))
    stats = agent_retention.sweep_once()
    assert stats["kept_no_ts"] == 1 and stats["deleted"] == 0
    assert _counts(db, "mystery")[0] == 1


def test_active_stream_skipped(db, monkeypatch):
    monkeypatch.setenv("AGENT_CHAT_RETENTION_DAYS", "60")
    _ckpt(db, "busy", _ts(90)); _owner(db, "busy", _ts(90))
    # 处于活跃状态 → 跳过不删
    monkeypatch.setattr("app.services.agent_streams.get_active_stream", lambda tid: object())
    stats = agent_retention.sweep_once()
    assert stats["skipped_active"] == 1 and stats["deleted"] == 0
    assert _counts(db, "busy") == (1, 0, 1)


def test_subnamespace_thread_not_candidate(db, monkeypatch):
    """'::' 内部命名空间线程不是独立聊天任务，不作删除候选"""
    monkeypatch.setenv("AGENT_CHAT_RETENTION_DAYS", "60")
    _ckpt(db, "proj::sub", _ts(90)); _owner(db, "proj::sub", _ts(90))
    stats = agent_retention.sweep_once()
    assert stats["deleted"] == 0
    assert _counts(db, "proj::sub")[0] == 1


def test_empty_db_no_crash(tmp_path, monkeypatch):
    """全新部署（库文件空/无表）→ 返回 note，不抛异常"""
    monkeypatch.setattr(agent_retention, "_RETENTION_DB_PATH",
                        str(tmp_path / "empty.db"))
    monkeypatch.setenv("AGENT_CHAT_RETENTION_DAYS", "60")
    stats = agent_retention.sweep_once()
    assert "note" in stats
