# -*- coding: utf-8 -*-
"""
migrate_project_owners.py — 存量项目归属迁移（一次性，幂等）

用户隔离上线前运行：把 checkpoint 库中所有「无主」thread_id 划归指定用户
（默认 admin，评审决策 2A）。已登记归属的线程不受影响；可重复运行。

用法（在 combination 目录下）：
    python tools/migrate_project_owners.py            # 全部划给 admin
    python tools/migrate_project_owners.py zhangsan   # 划给指定用户
"""
import sqlite3
import sys
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE.parent / "design_planning_generation_local_model" / "project_store" / "agent_checkpoints.db"


def migrate(owner: str) -> None:
    if not DB.exists():
        print(f"[skip] checkpoint 库不存在: {DB}")
        return
    conn = sqlite3.connect(str(DB), timeout=5)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS project_owners ("
            " thread_id TEXT PRIMARY KEY,"
            " username TEXT NOT NULL,"
            " created_at TEXT NOT NULL)"
        )
        rows = conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints "
            "WHERE thread_id != '' AND checkpoint_ns = ''"
        ).fetchall()
        now = datetime.datetime.now().isoformat(timespec="seconds")
        claimed = skipped_internal = kept = 0
        for (tid,) in rows:
            if "::" in tid:  # 内部命名空间（HITL/子图），不参与归属
                skipped_internal += 1
                continue
            exists = conn.execute(
                "SELECT 1 FROM project_owners WHERE thread_id = ?", (tid,)).fetchone()
            if exists:
                kept += 1
                continue
            conn.execute(
                "INSERT INTO project_owners (thread_id, username, created_at) VALUES (?, ?, ?)",
                (tid, owner, now))
            claimed += 1
        conn.commit()
        print(f"[ok] 迁移完成：新登记 {claimed} 个线程划给 {owner}；"
              f"已有归属保留 {kept} 个；跳过内部命名空间 {skipped_internal} 个")
    finally:
        conn.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "admin"
    migrate(target)
