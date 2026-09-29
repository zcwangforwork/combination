"""
sec_audit — 保密检索审计的异步落盘（2026-09-28 新增）

依据方案 §3.3 / §8.1，与 checkpoint 同库（SQLite）建两张审计表：

  retrieval_audit — 每次检索一条：查询者、当时密级、查询摘要、库作用域、
                    命中最高密级 / 返回数 / 被密级过滤数、L3 是否拦截、模式
  sec_denied_detail — 每次检索被过滤 chunk 的 source_file 明细（高频拦截
                    清单按此聚合，§8.2.2）
  sec_admin_audit  — Agent 侧管理动作（模式切换 / 密级变更 / 批量标注 / 异常告警）

写入策略（§3.3）：守护线程 + 队列异步落盘，不阻塞检索主链路；
写库失败降级为项目 temp/ 下 fallback JSONL 文件 + 启动告警，审计不丢失。

审计保留期 ≥ 1 年（SEC_AUDIT_RETENTION 天，过期清理随写入顺带执行）。
"""
import os
import json
import queue
import sqlite3
import threading
import datetime
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_FALLBACK_DIR = _PROJECT_ROOT / "temp"

# 审计库文件：默认与 checkpoint 同库（agent_state 初始化后记录的模块级路径）；
# 测试可直接改写本模块级变量指向临时库。
_AUDIT_DB_PATH: Optional[str] = None

_writer_thread: Optional[threading.Thread] = None
_writer_queue: "queue.Queue" = queue.Queue(maxsize=10000)
_start_lock = threading.Lock()


def _db_file() -> str:
    """审计表所在 SQLite 文件（与 checkpoint / project_owners 同库同目录）"""
    global _AUDIT_DB_PATH
    if _AUDIT_DB_PATH:
        return _AUDIT_DB_PATH
    from app.services import agent_state as _agent_state
    db_path = getattr(_agent_state, "_db_path", None)
    if not db_path:
        db_path = str(_PROJECT_ROOT / "project_store" / "agent_checkpoints.db")
    _AUDIT_DB_PATH = db_path
    return db_path


def _ensure_schema() -> None:
    """建表（幂等）"""
    with sqlite3.connect(_db_file(), timeout=5) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS retrieval_audit ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts TEXT NOT NULL, username TEXT NOT NULL,"
            " sec_level_at_query INTEGER, query_digest TEXT,"
            " query_preview TEXT, scope_summary TEXT,"
            " max_hit_level INTEGER, returned_count INTEGER, denied_count INTEGER,"
            " leak_blocked INTEGER DEFAULT 0, mode TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sec_denied_detail ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts TEXT NOT NULL, username TEXT NOT NULL,"
            " source_file TEXT NOT NULL, sec_level INTEGER, mode TEXT)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_denied_source"
            " ON sec_denied_detail (source_file)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sec_admin_audit ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts TEXT NOT NULL, operator TEXT NOT NULL,"
            " action TEXT NOT NULL, target TEXT, detail TEXT)"
        )


def _retention_days() -> int:
    try:
        return int(os.environ.get("SEC_AUDIT_RETENTION", "365"))
    except ValueError:
        return 365


def _fallback_write(row_type: str, row: dict, err: str) -> None:
    """审计写库失败的降级：追加 JSONL 文件（审计不丢失，§3.3）"""
    try:
        _FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        path = _FALLBACK_DIR / "sec_audit_fallback.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": row_type, "error": err, **row},
                               ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — 降级通道本身失败则放弃（已无更强手段）
        pass


def _writer_loop() -> None:
    """守护线程：批量出队写库；单条失败降级 fallback 文件"""
    while True:
        batch = [_writer_queue.get()]
        while len(batch) < 50:
            try:
                batch.append(_writer_queue.get_nowait())
            except queue.Empty:
                break
        try:
            _ensure_schema()
            cutoff = (datetime.datetime.now()
                      - datetime.timedelta(days=_retention_days())).isoformat(
                          timespec="seconds")
            with sqlite3.connect(_db_file(), timeout=5) as conn:
                for row_type, row in batch:
                    if row_type == "retrieval":
                        conn.execute(
                            "INSERT INTO retrieval_audit (ts, username, sec_level_at_query,"
                            " query_digest, query_preview, scope_summary, max_hit_level,"
                            " returned_count, denied_count, leak_blocked, mode)"
                            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (row["ts"], row["username"], row.get("sec_level_at_query"),
                             row.get("query_digest"), row.get("query_preview", ""),
                             row.get("scope_summary", ""), row.get("max_hit_level", 0),
                             row.get("returned_count", 0), row.get("denied_count", 0),
                             row.get("leak_blocked", 0), row.get("mode", "")))
                        for sf in row.get("denied_files", [])[:50]:
                            conn.execute(
                                "INSERT INTO sec_denied_detail (ts, username, source_file,"
                                " sec_level, mode) VALUES (?,?,?,?,?)",
                                (row["ts"], row["username"], sf,
                                 row.get("sec_level_at_query"), row.get("mode", "")))
                    elif row_type == "admin":
                        conn.execute(
                            "INSERT INTO sec_admin_audit (ts, operator, action, target, detail)"
                            " VALUES (?,?,?,?,?)",
                            (row["ts"], row["operator"], row["action"],
                             row.get("target", ""), row.get("detail", "")))
                # 保留期清理（顺带执行，幂等）
                conn.execute("DELETE FROM retrieval_audit WHERE ts < ?", (cutoff,))
                conn.execute("DELETE FROM sec_denied_detail WHERE ts < ?", (cutoff,))
        except Exception as e:  # noqa: BLE001
            print(f"[sec_audit] 审计写库失败，降级 fallback 文件: {e}")
            for row_type, row in batch:
                _fallback_write(row_type, row, str(e))


def _ensure_writer() -> None:
    """惰性启动守护写线程（进程内单例）"""
    global _writer_thread
    with _start_lock:
        if _writer_thread is None or not _writer_thread.is_alive():
            _writer_thread = threading.Thread(
                target=_writer_loop, name="sec-audit-writer", daemon=True)
            _writer_thread.start()


def enqueue_retrieval_audit(row: dict) -> None:
    """投递一条检索审计（非阻塞；队列满时降级 fallback 文件）"""
    try:
        _ensure_writer()
        _writer_queue.put_nowait(("retrieval", row))
    except queue.Full:
        _fallback_write("retrieval", row, "writer queue full")


def enqueue_admin_audit(row: dict) -> None:
    """投递一条管理动作审计（非阻塞）"""
    try:
        _ensure_writer()
        _writer_queue.put_nowait(("admin", row))
    except queue.Full:
        _fallback_write("admin", row, "writer queue full")


def mark_leak_blocked(username: str, source_file: str, overlap: float) -> None:
    """L3 拦截发生时的补充审计（§8.1 输出拦截事件：触发源文件、密级、overlap 值）"""
    enqueue_admin_audit({
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "operator": username or "(anonymous)",
        "action": "output_leak_blocked",
        "target": source_file,
        "detail": f"overlap={overlap:.3f}",
    })


# ── 审计查询（§8.2.5 四维：用户 / 时间段 / 密级 / 拦截）──

def query_retrieval_audit(*, username: str = None, start: str = None,
                          end: str = None, min_level: int = None,
                          leak_blocked: bool = None, limit: int = 100) -> list:
    """按维度过滤查询检索审计（同步直查，管理端低频调用）"""
    sql = "SELECT ts, username, sec_level_at_query, query_preview, scope_summary," \
          " max_hit_level, returned_count, denied_count, leak_blocked, mode" \
          " FROM retrieval_audit WHERE 1=1"
    args: list = []
    if username:
        sql += " AND username = ?"
        args.append(username)
    if start:
        sql += " AND ts >= ?"
        args.append(start)
    if end:
        sql += " AND ts <= ?"
        args.append(end)
    if min_level is not None:
        sql += " AND max_hit_level >= ?"
        args.append(int(min_level))
    if leak_blocked is not None:
        sql += " AND leak_blocked = ?"
        args.append(1 if leak_blocked else 0)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 1000)))
    try:
        _ensure_schema()
        with sqlite3.connect(_db_file(), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, args)
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        print(f"[sec_audit] 审计查询失败: {e}")
        return []


def query_denied_top(limit: int = 20) -> list:
    """高频拦截清单（§8.2.2）：denied 按 source_file 聚合 TopN"""
    try:
        _ensure_schema()
        with sqlite3.connect(_db_file(), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT source_file, COUNT(*) AS denied_count,"
                " MAX(ts) AS last_denied_at"
                " FROM sec_denied_detail GROUP BY source_file"
                " ORDER BY denied_count DESC LIMIT ?", (max(1, int(limit)),))
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        print(f"[sec_audit] denied_top 查询失败: {e}")
        return []


def query_admin_audit(*, limit: int = 100) -> list:
    """管理动作审计查询（模式切换 / 密级变更 / 拦截 / 告警）"""
    try:
        _ensure_schema()
        with sqlite3.connect(_db_file(), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT ts, operator, action, target, detail FROM sec_admin_audit"
                " ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 1000)),))
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        print(f"[sec_audit] 管理审计查询失败: {e}")
        return []
