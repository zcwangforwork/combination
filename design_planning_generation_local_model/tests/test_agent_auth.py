"""agent_auth 用户隔离测试

覆盖（对应评审测试计划）：
1. JWT 校验：有效 / 过期 / 签名不符 / alg=none / 缺失 / 无 sub → 401 语义
2. 归属登记：首写登记（POST）、先到先得、跨用户 403、未登记 GET 放行
3. 集成：最小 FastAPI 应用 + TestClient 验证依赖行为与两用户列表过滤
4. Guard：真实 router 的全部 /agent 路由必须挂鉴权依赖（防新端点漏锁）
5. 迁移：无主线程划归 admin、幂等、内部命名空间跳过
"""
import base64
import importlib.util
import json
import sqlite3
import time
import datetime
from pathlib import Path

import jwt as pyjwt
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.services import agent_auth
from app.services.agent_auth import (
    verify_token, require_user, require_project_access,
    init_owner_table, get_owner, list_owned_threads,
)

SECRET = agent_auth._DEFAULT_SECRET


def _make_token(username: str, secret: str = SECRET, exp_delta: int = 3600,
                alg: str = "HS256") -> str:
    now = time.time()
    payload = {"sub": username, "userId": 1, "role": "ADMIN",
               "iat": now, "exp": now + exp_delta}
    return pyjwt.encode(payload, secret, algorithm=alg)


def _make_alg_none_token(username: str) -> str:
    """手工构造 alg=none 的无签名 token（攻击面：算法混淆）"""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": username, "exp": time.time() + 3600}).encode()).rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}."


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    """每个测试用独立临时库（含 checkpoints 最小结构与 owners 表）"""
    db = tmp_path / "agent_checkpoints.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE checkpoints ("
        " thread_id TEXT, checkpoint_ns TEXT DEFAULT '', other TEXT)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(agent_auth, "_OWNERS_DB_PATH", str(db))
    yield db


@pytest.fixture
def app():
    """最小应用：一条非项目级路由 + 一条项目级路由，复用真实依赖"""
    api = FastAPI()

    @api.get("/agent/projects", dependencies=[Depends(require_user)])
    async def list_projects():
        tids = await list_owned_threads("alice")
        return {"projects": tids}

    @api.get("/agent/projects/{project_id}", dependencies=[Depends(require_project_access)])
    async def read_project(project_id: str):
        return {"ok": project_id}

    @api.post("/agent/projects/{project_id}/messages", dependencies=[Depends(require_project_access)])
    async def post_message(project_id: str):
        return {"ok": True}

    return api


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. JWT 校验 ────────────────────────────────────────────────

def test_verify_token_valid():
    assert verify_token(f"Bearer {_make_token('alice')}") == "alice"


def test_verify_token_hs512_accepted():
    """Spring jjwt 对 ≥64 字节密钥自动选 HS512（真实 UM token 形态，2026-09-20 实测）"""
    token = _make_token("admin", alg="HS512")
    assert verify_token(f"Bearer {token}") == "admin"
    token384 = _make_token("alice", alg="HS384")
    assert verify_token(f"Bearer {token384}") == "alice"


def test_verify_token_expired():
    token = _make_token("alice", exp_delta=-10)
    with pytest.raises(Exception) as e:
        verify_token(f"Bearer {token}")
    assert e.value.status_code == 401


def test_verify_token_bad_signature():
    token = _make_token("alice", secret="wrong-secret-entirely")
    with pytest.raises(Exception) as e:
        verify_token(f"Bearer {token}")
    assert e.value.status_code == 401


def test_verify_token_alg_none_rejected():
    with pytest.raises(Exception) as e:
        verify_token(f"Bearer {_make_alg_none_token('mallory')}")
    assert e.value.status_code == 401


def test_verify_token_missing_or_malformed():
    for header in [None, "", "Basic xyz", "Bearer "]:
        with pytest.raises(Exception) as e:
            verify_token(header)
        assert e.value.status_code == 401


def test_verify_token_no_sub():
    now = time.time()
    token = pyjwt.encode({"exp": now + 3600}, SECRET, algorithm="HS256")
    with pytest.raises(Exception) as e:
        verify_token(f"Bearer {token}")
    assert e.value.status_code == 401


# ── 2. 归属登记与访问控制（依赖级） ────────────────────────────

async def test_owner_claim_and_access():
    import asyncio
    await init_owner_table()
    assert await get_owner("p1") is None

    req_post = _fake_request("POST", _make_token("alice"))
    await require_project_access("p1", req_post)          # 首写 → 登记
    assert await get_owner("p1") == "alice"

    req_b = _fake_request("POST", _make_token("bob"))
    with pytest.raises(Exception) as e:
        await require_project_access("p1", req_b)         # 他人写入 → 403
    assert e.value.status_code == 403

    req_get_b = _fake_request("GET", _make_token("bob"))
    with pytest.raises(Exception) as e:
        await require_project_access("p1", req_get_b)     # 他人读取 → 403
    assert e.value.status_code == 403

    await require_project_access("p1", _fake_request("GET", _make_token("alice")))

    # 未登记 + GET（新项目空态）→ 放行
    await require_project_access("p2", _fake_request("GET", _make_token("bob")))


class _fake_request:
    """最小 Request 替身：require_* 只用到 headers 与 method"""
    def __init__(self, method: str, token: str):
        self.method = method
        self.headers = {"authorization": f"Bearer {token}"}

    def get(self, key, default=None):
        return self.headers.get(key, default)


# ── 3. 集成（TestClient） ──────────────────────────────────────

def test_no_token_401(client, _temp_db):
    assert client.get("/agent/projects").status_code == 401
    assert client.get("/agent/projects/pX").status_code == 401


def test_cross_user_and_claim_flow(client, _temp_db):
    alice = {"Authorization": f"Bearer {_make_token('alice')}"}
    bob = {"Authorization": f"Bearer {_make_token('bob')}"}

    # alice 首写 p1 → 登记
    assert client.post("/agent/projects/p1/messages", headers=alice).status_code == 200
    # bob 对 p1 读写 → 403
    assert client.post("/agent/projects/p1/messages", headers=bob).status_code == 403
    assert client.get("/agent/projects/p1", headers=bob).status_code == 403
    # alice 读 p1 → 200
    assert client.get("/agent/projects/p1", headers=alice).status_code == 200


def test_list_filters_by_owner(client, _temp_db):
    import asyncio
    alice = {"Authorization": f"Bearer {_make_token('alice')}"}
    bob = {"Authorization": f"Bearer {_make_token('bob')}"}
    assert client.post("/agent/projects/a1/messages", headers=alice).status_code == 200
    assert client.post("/agent/projects/b1/messages", headers=bob).status_code == 200

    conn = sqlite3.connect(str(_temp_db))
    # 同一线程多个检查点行（每轮对话一行）——必须去重为 1 个项目
    conn.executemany("INSERT INTO checkpoints (thread_id) VALUES (?)",
                     [("a1",)] * 3)
    conn.commit()
    conn.close()

    # list_projects 测试路由固定查 alice → 只见 a1（3 个检查点行 = 1 个项目）
    body = client.get("/agent/projects", headers=alice).json()
    assert body["projects"] == ["a1"]


# ── 4. Guard：真实 router 全部 /agent 路由必须挂鉴权 ───────────

def test_guard_all_agent_routes_have_auth():
    from app.api.routes import router
    agent_routes = [r for r in router.routes if r.path.startswith("/agent")]
    assert agent_routes, "未找到 agent 路由，include 前缀或路由注册发生变化"
    unwired = [r.path for r in agent_routes if not getattr(r, "dependencies", None)]
    assert not unwired, f"以下 /agent 路由缺少鉴权依赖: {unwired}"


# ── 5. 迁移脚本 ────────────────────────────────────────────────

def _load_migration_module():
    path = Path(__file__).parent.parent.parent / "tools" / "migrate_project_owners.py"
    spec = importlib.util.spec_from_file_location("migrate_project_owners", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_claims_ownerless_to_admin(tmp_path, monkeypatch, capsys):
    mod = _load_migration_module()
    db = tmp_path / "cp.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT DEFAULT '')")
    conn.executemany("INSERT INTO checkpoints (thread_id) VALUES (?)",
                     [("old1",), ("old2",), ("sub::internal",)])
    conn.commit()
    conn.close()
    monkeypatch.setattr(mod, "DB", db)

    mod.migrate("admin")
    out = capsys.readouterr().out
    assert "新登记 2" in out

    conn = sqlite3.connect(str(db))
    owners = dict(conn.execute("SELECT thread_id, username FROM project_owners").fetchall())
    conn.close()
    assert owners == {"old1": "admin", "old2": "admin"}   # 内部命名空间被跳过

    # 幂等：重跑不再登记，且不会改写已有归属
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE project_owners SET username = 'zhangsan' WHERE thread_id = 'old1'")
    conn.commit()
    conn.close()
    mod.migrate("admin")
    conn = sqlite3.connect(str(db))
    owners = dict(conn.execute("SELECT thread_id, username FROM project_owners").fetchall())
    conn.close()
    assert owners["old1"] == "zhangsan"
