"""sec_admin 集成测试 — 密级台账 / 变更 / 存量回填（方案 §4.3 / §4.4 / §8.2.1）

用 chroma PersistentClient(tmp) 直写原始 collection（与 test_kb_isolation 同法，
绕开 embedder）。覆盖：
1. set_source_sec_level：单文件全部 chunk 原子变更 + 方差一致 + 审计留痕
2. 变更范围隔离：只动目标文件，其他文件不受影响
3. 非法密级 → ValueError；未知文件 → LookupError
4. backfill_all_collections：补缺失字段、幂等（重跑零更新）、dry_run 不落库
5. list_sec_ledger：聚合视图 + mixed 密级不一致检测 + 未标注按 3 展示
"""
import json
import pytest
from pathlib import Path

from app.services import kb_scope, sec_admin
from app.services.rag import sec_filter
from app.services.rag.vector_store import VectorStore


@pytest.fixture(autouse=True)
def _tmp_chroma(tmp_path, monkeypatch):
    """共享库 / 个人库 / 回填进度 / 审计投递全部指向临时目录与捕获器"""
    shared = tmp_path / "chroma_shared"
    users = tmp_path / "chroma_users"
    shared.mkdir()
    monkeypatch.setattr(kb_scope, "USERS_KB_ROOT", users)
    monkeypatch.setattr(kb_scope, "SHARED_DB_DIR", str(shared))
    monkeypatch.setattr(VectorStore, "BASE_DIR", shared)
    monkeypatch.setattr(VectorStore, "_extra_clients", {})
    import app.services.rag.vector_store as vs_mod
    monkeypatch.setattr(vs_mod, "_chroma_client", None)
    # 回填进度文件 → 临时目录
    monkeypatch.setattr(sec_admin, "_PROGRESS_DIR", tmp_path / "progress")
    # 审计投递捕获（不落库不起线程）
    captured = []
    import app.services.sec_audit as sec_audit_mod
    monkeypatch.setattr(sec_audit_mod, "enqueue_admin_audit",
                        lambda row: captured.append(row))
    kb_scope._kb_user.set(None)
    yield {"shared": shared, "users": users, "captured": captured}
    kb_scope._kb_user.set(None)


def _client(db_dir: Path):
    import chromadb
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=str(db_dir),
                                     settings=Settings(anonymized_telemetry=False))


def _seed(db_dir: Path, coll_name: str, chunks: list):
    """chunks: [(file, meta_override_dict)] — sec 字段按 override 写（模拟历史数据）"""
    coll = _client(db_dir).get_or_create_collection(name=coll_name)
    ids, docs, metas, embs = [], [], [], []
    for i, (sf, override) in enumerate(chunks):
        meta = {"source_file": sf, "file_id": sf, "chunk_index": i}
        meta.update(override or {})
        ids.append(f"{sf}#{i}")
        docs.append(f"content of {sf} chunk {i}")
        metas.append(meta)
        embs.append([0.1, 0.2, 0.3])
    coll.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
    return coll


def _levels(db_dir: Path, coll_name: str, sf: str) -> list:
    coll = _client(db_dir).get_or_create_collection(name=coll_name)
    got = coll.get(where={"source_file": sf}, include=["metadatas"])
    return [sec_filter.normalize_sec_level((m or {}).get("sec_level"))
            for m in got.get("metadatas", [])]


# ── 1. 单文件密级变更 ────────────────────────────────────────

def test_set_source_sec_level_atomic(_tmp_chroma):
    shared = _tmp_chroma["shared"]
    _seed(shared, kb_scope.UPLOADS_COLLECTION, [
        ("plan.docx", {"sec_level": 0, "sec_source": "manual",
                       "sec_label": "公开", "acl_version": "v0",
                       "sec_updated_at": "2026-09-01T00:00:00"}),
        ("plan.docx", {"sec_level": 0, "sec_source": "manual",
                       "sec_label": "公开", "acl_version": "v0",
                       "sec_updated_at": "2026-09-01T00:00:00"}),
        ("plan.docx", {"sec_level": 0, "sec_source": "manual",
                       "sec_label": "公开", "acl_version": "v0",
                       "sec_updated_at": "2026-09-01T00:00:00"}),
        ("other.docx", {"sec_level": 1, "sec_source": "manual",
                        "sec_label": "内部", "acl_version": "v0",
                        "sec_updated_at": "2026-09-01T00:00:00"}),
    ])
    ret = sec_admin.set_source_sec_level("plan.docx", 2, "升密测试", "tester")
    assert ret["new_level"] == 2
    assert ret["chunk_count"] == 3
    assert ret["acl_version"].startswith("chg-")
    # 方差为 0：全部 chunk 一致为新密级
    assert _levels(shared, kb_scope.UPLOADS_COLLECTION, "plan.docx") == [2, 2, 2]
    # 其他文件不受影响
    assert _levels(shared, kb_scope.UPLOADS_COLLECTION, "other.docx") == [1]
    # 审计留痕
    audits = [a for a in _tmp_chroma["captured"] if a["action"] == "sec_level_change"]
    assert len(audits) == 1
    assert audits[0]["operator"] == "tester"
    assert "new_level=2" in audits[0]["detail"]


def test_set_source_sec_level_errors(_tmp_chroma):
    shared = _tmp_chroma["shared"]
    _seed(shared, kb_scope.UPLOADS_COLLECTION, [("a.docx", {"sec_level": 0})])
    with pytest.raises(ValueError):
        sec_admin.set_source_sec_level("a.docx", 9, "x", "t")
    with pytest.raises(LookupError):
        sec_admin.set_source_sec_level("missing.docx", 1, "x", "t")


# ── 2. 存量回填 ─────────────────────────────────────────────

def test_backfill_stamps_and_idempotent(_tmp_chroma):
    shared = _tmp_chroma["shared"]
    _seed(shared, kb_scope.UPLOADS_COLLECTION, [
        ("old1.docx", {}),                       # 历史无密级
        ("old2.docx", {}),
        # 已带本批次 acl_version 的精标 chunk → 回填跳过（幂等标记）
        ("new.docx", {"sec_level": 1, "sec_source": "manual",
                      "sec_label": "内部", "acl_version": "bf-test-1",
                      "sec_updated_at": "2026-09-28T00:00:00"}),
    ])
    stats = sec_admin.backfill_all_collections(
        acl_version="bf-test-1", level=3, operator="(test)")
    assert stats["total_updated"] == 2  # 只补缺失的两个
    assert _levels(shared, kb_scope.UPLOADS_COLLECTION, "old1.docx") == [3]
    assert _levels(shared, kb_scope.UPLOADS_COLLECTION, "old2.docx") == [3]
    assert _levels(shared, kb_scope.UPLOADS_COLLECTION, "new.docx") == [1]

    # 幂等：删掉进度文件重跑（排除 offset 短路，纯靠 acl_version 标记跳过）
    sec_admin._PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    for f in Path(sec_admin._PROGRESS_DIR).glob("*.json"):
        f.unlink()
    stats2 = sec_admin.backfill_all_collections(
        acl_version="bf-test-1", level=3, operator="(test)")
    assert stats2["total_updated"] == 0
    # 数据未被改动
    assert _levels(shared, kb_scope.UPLOADS_COLLECTION, "new.docx") == [1]


def test_backfill_dry_run(_tmp_chroma):
    shared = _tmp_chroma["shared"]
    _seed(shared, kb_scope.UPLOADS_COLLECTION, [("old.docx", {})])
    stats = sec_admin.backfill_all_collections(
        acl_version="bf-dry", level=3, dry_run=True)
    assert stats["dry_run"] is True
    assert stats["total_updated"] == 1  # 计数照常
    assert _levels(shared, kb_scope.UPLOADS_COLLECTION, "old.docx") == [None]  # 未落库


# ── 3. 密级台账 ─────────────────────────────────────────────

def test_list_sec_ledger(_tmp_chroma):
    shared = _tmp_chroma["shared"]
    _seed(shared, kb_scope.UPLOADS_COLLECTION, [
        ("clean.docx", {"sec_level": 1, "sec_source": "manual",
                        "sec_label": "内部", "acl_version": "v",
                        "sec_updated_at": "2026-09-01T00:00:00"}),
        ("clean.docx", {"sec_level": 1, "sec_source": "manual",
                        "sec_label": "内部", "acl_version": "v",
                        "sec_updated_at": "2026-09-01T00:00:00"}),
        ("mixed.docx", {"sec_level": 0}),
        ("mixed.docx", {"sec_level": 2}),
        ("blank.docx", {}),  # 未标注
    ])
    ledger = {e["source_file"]: e for e in sec_admin.list_sec_ledger()}
    assert ledger["clean.docx"]["mixed"] is False
    assert ledger["clean.docx"]["chunk_count"] == 2
    assert ledger["clean.docx"]["sec_level"] == 1
    assert ledger["mixed.docx"]["mixed"] is True  # 密级不一致 → 立即修复信号
    # 未标注 → 按 3 展示（fail-closed 视图）
    assert ledger["blank.docx"]["sec_level"] == 3
    assert ledger["blank.docx"]["sec_label"] == "未标注"
