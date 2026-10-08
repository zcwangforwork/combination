"""agent_retention — 聊天任务保留期后台清理（2026-09-29 新增）

用户要求：用户与 agent 的聊天任务（thread）只保留两个月以内的。

设计（对齐 sec_audit 的环境变量 + 后台线程模式）：
- 保留天数：环境变量 AGENT_CHAT_RETENTION_DAYS（默认 60，0 = 关闭自动清理）
- 过期口径：按【最后活动时间】——取该线程最新 checkpoint blob 内的 ts（UTC ISO），
  与 project_owners.created_at 取较大者；两者皆不可得时保守保留（不删）
- 删除动作：同事务清三表该 thread_id 的行（checkpoints / writes / project_owners）；
  对齐 DELETE /agent/projects/{id} 的语义（官方 adelete_thread 只认 checkpoints+writes，
  归属行由本模块补删；本模块跑在后台线程，无事件循环，故直接走 SQL）
- 误删防护：进行中生成流的线程跳过；'::' 内部命名空间线程不作为删除候选；
  同库的 retrieval_audit / sec_denied_detail / sec_admin_audit 审计表绝不触碰
- 调度：start_retention_sweeper() 拉起 daemon 线程，启动延迟 60s，此后每 24h 一轮
"""
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent.parent

# 归属/检查点所在库：测试可直接改写本模块级变量指向临时库（对齐 sec_audit._AUDIT_DB_PATH）
_RETENTION_DB_PATH: Optional[str] = None

_THREAD: Optional[threading.Thread] = None
_START_LOCK = threading.Lock()

_FIRST_DELAY_SEC = 60      # 启动后先等 Agent 初始化完再扫
_SWEEP_INTERVAL_SEC = 24 * 3600


def retention_days() -> int:
    """保留天数（AGENT_CHAT_RETENTION_DAYS，缺省 60；非法值回退 60）"""
    try:
        return int(os.environ.get("AGENT_CHAT_RETENTION_DAYS", "60"))
    except ValueError:
        return 60


def _db_file() -> str:
    """聊天任务所在 SQLite 文件（与 checkpoint / project_owners 同库同目录）"""
    if _RETENTION_DB_PATH:
        return _RETENTION_DB_PATH
    from app.services import agent_state as _agent_state
    db_path = getattr(_agent_state, "_db_path", None)
    if db_path:
        return db_path
    return str(_PROJECT_ROOT / "project_store" / "agent_checkpoints.db")


def _blob_ts(blob, blob_type: str) -> Optional[datetime]:
    """解析 checkpoint blob 内的 ts（langgraph 检查点协议的时间戳，UTC aware）"""
    if blob is None:
        return None
    try:
        if blob_type == "json":
            import json
            obj = json.loads(blob)
        else:
            import msgpack
            obj = msgpack.unpackb(blob, raw=False)
        ts = obj.get("ts") if isinstance(obj, dict) else None
        if not ts or not isinstance(ts, str):
            return None
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001 — 单线程解析失败不应中断整轮清扫
        return None


def _thread_last_activity(
    blob_ts: Optional[datetime],
    created_at: Optional[str],
) -> Optional[datetime]:
    """线程最后活动时间 = max(最新 checkpoint ts, 归属行 created_at)

    created_at 为本地 naive ISO，astimezone() 补本地时区后与 UTC ts 可比；
    两者皆无 → None（调用方保守保留）。
    """
    candidates = []
    if blob_ts is not None:
        candidates.append(blob_ts.astimezone(timezone.utc))
    if created_at:
        try:
            local = datetime.fromisoformat(created_at)
            if local.tzinfo is None:
                local = local.astimezone()  # naive → 本地时区 aware
            candidates.append(local.astimezone(timezone.utc))
        except ValueError:
            pass
    return max(candidates) if candidates else None


def sweep_once(now: Optional[datetime] = None) -> dict:
    """同步执行一轮保留期清理，返回统计 dict（便于测试与日志观察）

    纯后台线程调用（无事件循环），全程短事务 + timeout=5（项目 sqlite 惯例）。
    """
    days = retention_days()
    if days <= 0:
        return {"disabled": True, "retention_days": days}

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    db_path = _db_file()

    stats = {"retention_days": days, "threads": 0, "expired": 0,
             "deleted": 0, "skipped_active": 0, "kept_no_ts": 0, "errors": 0}

    conn = sqlite3.connect(db_path, timeout=5)
    try:
        # 候选：根命名空间（checkpoint_ns=''）每线程最新 rowid 的 checkpoint 行。
        # GROUP BY 去重 + MAX(rowid) = 最新活动（对齐 agent_auth.list_owned_threads 惯例）
        try:
            rows = conn.execute(
                "SELECT c.thread_id, c.checkpoint, c.type FROM checkpoints c "
                "JOIN (SELECT thread_id, MAX(rowid) rid FROM checkpoints "
                "      WHERE checkpoint_ns='' AND thread_id != '' GROUP BY thread_id) m "
                "  ON m.rid = c.rowid").fetchall()
        except sqlite3.OperationalError:  # 库/表尚不存在（全新部署）
            return {**stats, "note": "checkpoints table missing"}

        owners = dict(conn.execute(
            "SELECT thread_id, created_at FROM project_owners").fetchall())
    finally:
        conn.close()

    stats["threads"] = len(rows)

    expired = []
    for thread_id, blob, blob_type in rows:
        tid = thread_id or ""
        if "::" in tid:  # 内部命名空间（HITL/子图），非独立聊天任务
            continue
        last = _thread_last_activity(
            _blob_ts(blob, blob_type), owners.get(tid))
        if last is None:
            stats["kept_no_ts"] += 1        # 无法定龄 → 保守保留
        elif last < cutoff:
            expired.append(tid)

    stats["expired"] = len(expired)
    if not expired:
        return stats

    # 进行中生成流的线程跳过（删除后流仍会向库写回 → 立即复活）
    from app.services import agent_streams
    for tid in expired:
        try:
            if agent_streams.get_active_stream(tid) is not None:
                stats["skipped_active"] += 1
                continue
            with sqlite3.connect(db_path, timeout=5) as conn:
                conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (tid,))
                conn.execute("DELETE FROM writes WHERE thread_id = ?", (tid,))
                conn.execute("DELETE FROM project_owners WHERE thread_id = ?", (tid,))
            stats["deleted"] += 1
        except sqlite3.OperationalError:    # writes 表在旧库可能不存在 → 只清存在的两张
            try:
                with sqlite3.connect(db_path, timeout=5) as conn:
                    conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (tid,))
                    conn.execute("DELETE FROM project_owners WHERE thread_id = ?", (tid,))
                stats["deleted"] += 1
            except Exception as e:  # noqa: BLE001 — 单线程失败不拖垮整轮
                stats["errors"] += 1
                print(f"[agent_retention] 删除 {tid[:18]} 失败: {e}")
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            print(f"[agent_retention] 删除 {tid[:18]} 失败: {e}")

    return stats


def _sweep_loop() -> None:
    """守护线程：延迟启动 → 每 24h 清扫一轮；单轮异常只打印不退出"""
    time.sleep(_FIRST_DELAY_SEC)
    while True:
        try:
            stats = sweep_once()
            if not stats.get("disabled"):
                print(f"[agent_retention] sweep done: {stats}")
        except Exception as e:  # noqa: BLE001
            print(f"[agent_retention] sweep failed: {e}")
        time.sleep(_SWEEP_INTERVAL_SEC)


def start_retention_sweeper() -> None:
    """拉起后台清扫线程（幂等；main.py lifespan 启动时调用）"""
    global _THREAD
    with _START_LOCK:
        if _THREAD and _THREAD.is_alive():
            return
        _THREAD = threading.Thread(
            target=_sweep_loop, name="agent-retention", daemon=True)
        _THREAD.start()
