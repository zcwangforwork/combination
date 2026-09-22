"""kb_scope 知识库用户隔离测试

覆盖：
1. 作用域解析三态：无上下文仅共享库 / 普通用户=共享+本人 / ADMIN=共享+全部个人库
2. VectorStore 定向个人库（persist_directory）与上下文多库检索目标（_effective_extra）
3. /api/kb/* 端点鉴权（无 token → 401）
4. 删除越权：普通用户删他人库文件 → 404；admin 按 owner 定向删除成功
5. guard：全部 /kb 路由必须挂鉴权依赖

数据用 chroma PersistentClient(tmp) 直接写原始 collection（绕开 embedder）。
"""
import os
import sqlite3
import time
import pytest
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.services import kb_scope, agent_auth
from app.services.agent_auth import require_user
from app.services.rag.vector_store import VectorStore

SECRET = agent_auth._DEFAULT_SECRET


def _make_token(username, role="USER", secret=SECRET):
    import jwt as pyjwt
    import time as _t
    now = _t.time()
    payload = {"sub": username, "role": role, "userId": 1,
               "iat": now, "exp": now + 3600}
    return pyjwt.encode(payload, secret, algorithm="HS512")


@pytest.fixture(autouse=True)
def _tmp_kb_root(tmp_path, monkeypatch):
    """个人库根目录指向临时目录；共享库指向临时共享目录"""
    shared = tmp_path / "chroma_shared"
    users = tmp_path / "chroma_users"
    shared.mkdir()
    monkeypatch.setattr(kb_scope, "USERS_KB_ROOT", users)
    monkeypatch.setattr(kb_scope, "SHARED_DB_DIR", str(shared))
    # VectorStore 类级共享目录也切到临时（避免 _effective_extra 误比真实库）
    monkeypatch.setattr(VectorStore, "BASE_DIR", shared)
    monkeypatch.setattr(VectorStore, "_extra_clients", {})
    import app.services.rag.vector_store as vs_mod
    monkeypatch.setattr(vs_mod, "_chroma_client", None)
    kb_scope._kb_user.set(None)  # 每测重置上下文
    yield users
    kb_scope._kb_user.set(None)


def _seed_uploads(db_dir: Path, files: list):
    """直接向 uploads collection 写假分块（带向量与 metadata，绕开 embedder）"""
    import chromadb
    from chromadb.config import Settings
    client = chromadb.PersistentClient(path=str(db_dir),
                                       settings=Settings(anonymized_telemetry=False))
    coll = client.get_or_create_collection(name=kb_scope.UPLOADS_COLLECTION)
    for i, (sf, fid) in enumerate(files):
        coll.add(
            ids=[f"{sf}_{i}"],
            documents=[f"内容 of {sf}"],
            metadatas=[{"source_file": sf, "file_id": fid, "original_filename": sf,
                        "ingested_at": time.time(), "chunk_index": 0}],
            embeddings=[[0.1, 0.2, 0.3]],
        )
    return coll


# ── 1. 作用域解析 ────────────────────────────────────────────

def test_scope_no_context_shared_only():
    targets = kb_scope.query_targets()
    assert list(targets.keys()) == [kb_scope.SHARED_DB_DIR]
    assert set(targets[kb_scope.SHARED_DB_DIR]) == set(kb_scope.SHARED_QUERY_COLLECTIONS)


def test_scope_normal_user_own_plus_shared(tmp_path):
    kb_scope.user_kb_dir("alice")           # 建出 alice 目录
    kb_scope.user_kb_dir("bob")
    kb_scope.set_kb_user("alice", False)
    targets = kb_scope.query_targets()
    assert len(targets) == 2
    assert kb_scope.user_kb_dir("alice") in targets
    assert kb_scope.user_kb_dir("bob") not in targets


def test_scope_admin_all_users(tmp_path):
    kb_scope.user_kb_dir("alice")
    kb_scope.user_kb_dir("bob")
    kb_scope.set_kb_user("admin", True)
    targets = kb_scope.query_targets()
    assert kb_scope.user_kb_dir("alice") in targets
    assert kb_scope.user_kb_dir("bob") in targets


def test_safe_name_blocks_traversal(tmp_path):
    assert kb_scope._safe_name("../etc") == ".._etc"   # 分隔符被替换，点号保留
    assert kb_scope._safe_name("..") == "_.."          # 纯点名强制前缀，防上级逃逸
    assert kb_scope._safe_name("") == "anonymous"
    d = kb_scope.user_kb_dir("a/b")
    assert ".." not in Path(d).parts


# ── 2. VectorStore 定向与多库解析 ────────────────────────────

def test_vectorstore_personal_dir_listing(tmp_path):
    _seed_uploads(tmp_path / "chroma_users" / "alice", [("a.docx", "f1")])
    store = VectorStore(collection_name="uploads",
                        persist_directory=kb_scope.user_kb_dir("alice"))
    files = store.list_uploaded_files()
    assert [f["source_file"] for f in files] == ["a.docx"]


def test_effective_extra_follows_context(tmp_path):
    kb_scope.user_kb_dir("alice")
    kb_scope.user_kb_dir("bob")
    kb_scope.set_kb_user("alice", False)
    store = VectorStore()  # 无显式参数 → 按上下文
    extra = store._effective_extra()
    assert list(extra.keys()) == [kb_scope.user_kb_dir("alice")]
    kb_scope.set_kb_user("admin", True)
    extra = store._effective_extra()
    assert set(extra.keys()) == {kb_scope.user_kb_dir("alice"), kb_scope.user_kb_dir("bob")}


# ── 3/4. 端点：鉴权 + 删除越权（真实 router）─────────────────

@pytest.fixture
def client():
    from app.api.routes import router
    api = FastAPI()
    api.include_router(router, prefix="/api")
    return TestClient(api)


def test_kb_endpoints_401_without_token(client):
    assert client.get("/api/kb/files").status_code == 401
    assert client.post("/api/kb/chat", json={"question": "x"}).status_code == 401
    assert client.post("/api/kb/files/delete",
                       json={"source_file": "x"}).status_code == 401


def test_kb_delete_other_users_file_404(client, tmp_path):
    # bob 的个人库里有 secret.docx；alice 尝试删除 → 404（作用域内找不到）
    _seed_uploads(tmp_path / "chroma_users" / "bob", [("secret.docx", "f9")])
    alice = {"Authorization": f"Bearer {_make_token('alice', 'USER')}"}
    resp = client.post("/api/kb/files/delete",
                       json={"source_file": "secret.docx"}, headers=alice)
    assert resp.status_code == 404


def test_kb_delete_own_and_admin_cross(client, tmp_path):
    _seed_uploads(tmp_path / "chroma_users" / "alice", [("mine.txt", "f1")])
    alice = {"Authorization": f"Bearer {_make_token('alice', 'USER')}"}
    assert client.post("/api/kb/files/delete",
                       json={"source_file": "mine.txt"},
                       headers=alice).status_code == 200
    # 再种一个，admin 按 owner 删除
    _seed_uploads(tmp_path / "chroma_users" / "alice", [("mine2.txt", "f2")])
    admin = {"Authorization": f"Bearer {_make_token('admin', 'ADMIN')}"}
    resp = client.post("/api/kb/files/delete",
                       json={"source_file": "mine2.txt", "owner": "alice"},
                       headers=admin)
    assert resp.status_code == 200
    assert resp.json()["owner_dir"] == "alice"


def test_kb_files_scoped_by_user(client, tmp_path):
    _seed_uploads(tmp_path / "chroma_users" / "alice", [("a.txt", "f1")])
    _seed_uploads(tmp_path / "chroma_users" / "bob", [("b.txt", "f2")])
    alice = {"Authorization": f"Bearer {_make_token('alice', 'USER')}"}
    files = client.get("/api/kb/files", headers=alice).json()["files"]
    assert [f["source_file"] for f in files] == ["a.txt"]
    admin = {"Authorization": f"Bearer {_make_token('admin', 'ADMIN')}"}
    files = client.get("/api/kb/files", headers=admin).json()["files"]
    assert {f["source_file"] for f in files} == {"a.txt", "b.txt"}
    assert {f["owner"] for f in files} == {"alice", "bob"}


# ── 5. guard：全部 /kb 路由挂鉴权 ────────────────────────────

def test_guard_all_kb_routes_have_auth():
    from app.api.routes import router
    kb_routes = [r for r in router.routes if r.path.startswith("/kb")]
    assert kb_routes, "未找到 kb 路由"
    unwired = [r.path for r in kb_routes if not getattr(r, "dependencies", None)]
    assert not unwired, f"以下 /kb 路由缺少鉴权依赖: {unwired}"
