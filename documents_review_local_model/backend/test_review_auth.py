# -*- coding: utf-8 -*-
"""review_auth 用户鉴权与会话归属隔离测试（combination 移植新增）

对齐 design_planning_generation_local_model/tests/test_agent_auth.py 的覆盖面，
按审核服务的平铺模块结构适配：
1. JWT 校验：有效 / HS384+HS512 / 过期 / 签名不符 / alg=none / 缺失 / 无 sub → 401
2. 会话归属登记（依赖级）：POST 先到先得、跨用户 403、未登记 GET 放行
3. 集成：最小 FastAPI 应用 + TestClient 验证依赖行为
   （path 参数与 Form 体两种 session_id 来源）
4. Guard：真实 main.py 的全部 /api 路由必须挂鉴权依赖（防新端点漏锁）
"""
import asyncio
import base64
import json
import re
import sqlite3
import time
from pathlib import Path

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fastapi import Form

import review_auth
from review_auth import verify_token, require_user, require_session_access

SECRET = review_auth._DEFAULT_SECRET
MAIN_PY = Path(__file__).parent / "main.py"


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
    """每个测试用独立临时归属库（review_auth 模块级变量直改）"""
    db = tmp_path / "review_owners.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS session_owners ("
        " session_id TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(review_auth, "_OWNERS_DB_PATH", str(db))
    yield db


@pytest.fixture
def app():
    """最小应用：复用真实依赖，覆盖 path 参数 / Form 体 / 纯认证三类路由"""
    api = FastAPI()

    @api.get("/api/state/{session_id}",
             dependencies=[Depends(require_session_access)])
    async def read_state(session_id: str):
        return {"ok": session_id}

    @api.post("/api/conversation/message",
              dependencies=[Depends(require_session_access)])
    async def post_message(session_id: str = Form("default")):
        return {"ok": session_id}

    @api.get("/api/vectorstore/status", dependencies=[Depends(require_user)])
    async def vs_status():
        return {"ok": True}

    return api


@pytest.fixture
def client(app):
    return TestClient(app)


def _hdr(user: str) -> dict:
    return {"Authorization": f"Bearer {_make_token(user)}"}


# ── 1. JWT 校验 ────────────────────────────────────────────────

def test_verify_token_valid():
    assert verify_token(f"Bearer {_make_token('alice')}") == "alice"


def test_verify_token_hs384_hs512_accepted():
    """Spring jjwt 依据密钥字节数自动选 HS256/384/512 —— 三者必须全放行"""
    assert verify_token(f"Bearer {_make_token('admin', alg='HS512')}") == "admin"
    assert verify_token(f"Bearer {_make_token('alice', alg='HS384')}") == "alice"


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
    token = pyjwt.encode({"exp": time.time() + 3600}, SECRET, algorithm="HS256")
    with pytest.raises(Exception) as e:
        verify_token(f"Bearer {token}")
    assert e.value.status_code == 401


# ── 2. 会话归属登记与访问控制（依赖级） ────────────────────────

def test_owner_claim_first_write_wins():
    """未登记 + POST → 登记归属；另一用户 POST 同一会话 → 403"""
    asyncio.run(_claim_and_conflict())


async def _claim_and_conflict():
    class _Req:
        method = "POST"
        headers = {"authorization": f"Bearer {_make_token('alice')}"}
        path_params = {}

        async def form(self):
            return {"session_id": "conv-1"}

    assert await require_session_access(_Req()) == "alice"
    assert await review_auth.get_owner("conv-1") == "alice"

    class _ReqBob(_Req):
        headers = {"authorization": f"Bearer {_make_token('bob')}"}

    with pytest.raises(Exception) as e:
        await require_session_access(_ReqBob())
    assert e.value.status_code == 403


def test_unregistered_get_passes_through():
    """未登记 + 非 POST → 放行（会话不存在由端点自身提示）"""
    asyncio.run(_unregistered_get())


async def _unregistered_get():
    class _Req:
        method = "GET"
        headers = {"authorization": f"Bearer {_make_token('bob')}"}
        path_params = {"session_id": "conv-never-claimed"}

        async def form(self):  # pragma: no cover - GET 不应读体
            raise AssertionError("GET 不应读取请求体")

    assert await require_session_access(_Req()) == "bob"


def test_registered_cross_user_get_403():
    asyncio.run(_cross_get())


async def _cross_get():
    class _ReqPost:
        method = "POST"
        headers = {"authorization": f"Bearer {_make_token('alice')}"}
        path_params = {}

        async def form(self):
            return {"session_id": "conv-2"}

    await require_session_access(_ReqPost())

    class _ReqGet:
        method = "GET"
        headers = {"authorization": f"Bearer {_make_token('bob')}"}
        path_params = {"session_id": "conv-2"}

        async def form(self):  # pragma: no cover
            raise AssertionError("GET 不应读取请求体")

    with pytest.raises(Exception) as e:
        await require_session_access(_ReqGet())
    assert e.value.status_code == 403


# ── 3. 集成（TestClient） ──────────────────────────────────────

def test_client_401_without_token(client):
    assert client.get("/api/vectorstore/status").status_code == 401
    assert client.get("/api/state/conv-x").status_code == 401


def test_client_session_flow_path_and_form(client):
    """Form 体登记（POST message）→ path 参数校验（GET state）→ 跨用户 403"""
    # alice 以 Form 体发起会话 → 归属登记
    r = client.post("/api/conversation/message", headers=_hdr("alice"),
                    data={"session_id": "conv-9"})
    assert r.status_code == 200
    # alice 经 path 参数读同会话 → 放行
    assert client.get("/api/state/conv-9", headers=_hdr("alice")).status_code == 200
    # bob 读同一会话 → 403
    assert client.get("/api/state/conv-9", headers=_hdr("bob")).status_code == 403
    # bob 读未登记会话 → 放行（端点自身提示不存在）
    assert client.get("/api/state/conv-other", headers=_hdr("bob")).status_code == 200


def test_client_require_user_allows_any_session(client):
    """纯认证路由与会话无关：任何登录用户可访问"""
    assert client.get("/api/vectorstore/status", headers=_hdr("bob")).status_code == 200


# ── 4. Guard：真实路由全量挂锁 ─────────────────────────────────

def test_main_all_api_routes_guarded():
    """main.py 的全部 /api 路由装饰器必须携带 Depends 鉴权依赖（防新端点漏锁）"""
    text = MAIN_PY.read_text(encoding="utf-8")
    lines = text.splitlines()
    missing = []
    for i, ln in enumerate(lines):
        m = re.match(r'\s*@app\.(get|post|put|delete)\("(/api/[^"]+)"', ln)
        if m and "Depends(" not in "\n".join(lines[i:i + 4]):
            missing.append((i + 1, m.group(2)))
    assert not missing, f"发现未挂鉴权依赖的 /api 路由: {missing}"


def test_main_health_stays_open():
    """前端端口探测依赖 /health 无鉴权 —— 必须保持开放"""
    text = MAIN_PY.read_text(encoding="utf-8")
    m = re.search(r'@app\.get\("/health"[^)]*\)', text)
    assert m and "Depends(" not in m.group(0), "/health 不得挂鉴权依赖"
