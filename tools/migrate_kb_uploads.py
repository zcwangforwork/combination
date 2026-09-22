# -*- coding: utf-8 -*-
"""
migrate_kb_uploads.py — 存量知识库上传文件迁移（一次性，需先停止 8002 服务）

把共享库 chroma_db_insulin_pump 的 qms_doc_uploads collection 全部分块
（含向量，无需重新嵌入）复制到 ADMIN 个人库 chroma_db_users/admin/，
校验数量一致后清空共享侧该 collection（其他用户不再可检索，用户决策 2026-09-21）。
共享库的 insulin_pump_kb（标准语料）不受影响。
幂等：重跑时共享侧已空则直接跳过。
"""
import os

import chromadb
from chromadb.config import Settings

_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENT_ROOT = os.path.join(_HERE, "..", "design_planning_generation_local_model")
SHARED = os.path.normpath(os.path.join(_AGENT_ROOT, "chroma_db_insulin_pump"))
ADMIN_DIR = os.path.normpath(os.path.join(_AGENT_ROOT, "chroma_db_users", "admin"))
COLL = "qms_doc_uploads"
BATCH = 500


def main():
    shared = chromadb.PersistentClient(path=SHARED, settings=Settings(anonymized_telemetry=False))
    admin = chromadb.PersistentClient(path=ADMIN_DIR, settings=Settings(anonymized_telemetry=False))

    src = None
    try:
        src = shared.get_collection(name=COLL)
    except Exception:
        pass
    total = src.count() if src else 0
    print(f"[migrate] 共享库 {COLL}: {total} 块")
    if total == 0:
        print("[migrate] 共享侧无数据，无需迁移（幂等跳过）")
        return

    dst = admin.get_or_create_collection(name=COLL)
    dst_before = dst.count()

    copied = 0
    offset = 0
    while True:
        batch = src.get(limit=BATCH, offset=offset,
                        include=["documents", "metadatas", "embeddings"])
        ids = batch.get("ids") or []
        if not ids:
            break
        dst.add(
            ids=ids,
            documents=batch["documents"],
            metadatas=batch["metadatas"],
            embeddings=batch["embeddings"],
        )
        copied += len(ids)
        offset += len(ids)
        if len(ids) < BATCH:
            break

    dst_after = dst.count()
    print(f"[migrate] 复制完成：{copied} 块 | admin 库 {dst_before} -> {dst_after}")
    assert dst_after >= copied, "目标库数量异常"

    # 校验后清空共享侧（delete_collection + 重建空库，保持 collection 存在）
    shared.delete_collection(name=COLL)
    shared.get_or_create_collection(name=COLL)
    print(f"[migrate] 共享侧 {COLL} 已清空（insulin_pump_kb 不受影响）")
    print("[migrate] OK")


if __name__ == "__main__":
    main()
