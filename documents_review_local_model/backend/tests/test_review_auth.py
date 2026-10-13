"""review_auth 用户隔离测试（combination 移植新增）

对齐 design_planning_generation_local_model/tests/test_agent_auth.py 的覆盖面：
1. JWT 校验：有效 / HS384/512 / 过期 / 签名不符 / alg=none / 缺失 / 无 sub → 401 语义
2. 会话归属登记：POST 登记（路径参数与 Form 体两种 session_id 来源）、先到先得、
   跨用户 403、未登记 GET 放行
3. 集成：最小 FastAPI 应用 + TestClient 验证依赖行为（SSE 流端点 = 路径参数语义）
4. Guard：真实 main.py 的全部 /api 路由必须挂鉴权依赖（源码级扫描，避免 import
   重型依赖 ChromaDB/LangGraph）；/health 必须保持无鉴权（前端端口探测用）

注意：异步依赖用 asyncio.run 驱动（不依赖 pytest-asyncio 插件）。
"""
import asyncio
import base64
import io
import json
import re
import sqlite3
import time
from pathlib import Path

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import review_auth
from review_auth import (
    get_owner, init_owner_table, require_session_access, require_user,
    verify_token,
)

SECRET = review_auth._DEFAULT_SECRET
BACKEND_DIR = Path(__file__).resolve().parent.parent


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


class _fake_request:
    """最小 Request 替身：require_* 只用到 headers / method / path_params / form()"""
    def __init__(self, method: str, token: str, path_params=None, form=None):
        self.method = method
        self.headers = {"authorization": f"Bearer {token}"}
        self.path_params = path_params or {}
        self._form = form

    def get(self, key, default=None):
        return self.headers.get(key, default)

    async def form(self):
        return self._form


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    """每个测试用独立临时归属库（避免污染 checkpoints/review_owners.db）"""
    db = tmp_path / "review_owners.db"
    monkeypatch.setattr(review_auth, "_OWNERS_DB_PATH", str(db))
    yield db


@pytest.fixture
def app():
    """最小应用：复刻真实端点形态——
    SSE 流 = GET + 路径参数 session_id；会话续用 = POST + Form 体 session_id"""
    api = FastAPI()

    @api.get("/api/agent/conversation/stream/{session_id}",
             dependencies=[Depends(require_session_access)])
    async def stream(session_id: str):
        return {"ok": session_id}

    @api.post("/api/agent/conversation/start",
              dependencies=[Depends(require_session_access)])
    async def start():
        return {"ok": True}

    @api.get("/api/export-review", dependencies=[Depends(require_user)])
    async def export_review():
        return {"ok": True}

    return api


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. JWT 校验 ────────────────────────────────────────────────

def test_verify_token_valid():
    assert verify_token(f"Bearer {_make_token('alice')}") == "alice"


def test_verify_token_hs384_hs512_accepted():
    """Spring jjwt 对 ≥64 字节密钥自动选 HS512（真实 UM token 形态）"""
    assert verify_token(f"Bearer {_make_token('admin', alg='HS512')}") == "admin"
    assert verify_token(f"Bearer {_make_token('alice', alg='HS384')}") == "alice"


def test_verify_token_expired():
    with pytest.raises(Exception) as e:
        verify_token(f"Bearer {_make_token('alice', exp_delta=-10)}")
    assert e.value.status_code == 401


def test_verify_token_bad_signature():
    with pytest.raises(Exception) as e:
        verify_token(f"Bearer {_make_token('alice', secret='wrong-secret-entirely')}")
    assert e.value.status_code == 401


def test_verify_token_alg_none_rejected():
    with pytest.raises(Exception) as e:
        verify_token(f"Bearer {_make_alg_none_token('mallory')}")
    assert e.value.status_code == 401


def test_verify_token_missing_or_malformed():
    for header in [None, "", "Basic xyz", "Bearer ", "Bearer a.b.c"]:
        with pytest.raises(Exception) as e:
            verify_token(header)
        assert e.value.status_code == 401


def test_verify_token_no_sub():
    token = pyjwt.encode({"exp": time.time() + 3600}, SECRET, algorithm="HS256")
    with pytest.raises(Exception) as e:
        verify_token(f"Bearer {token}")
    assert e.value.status_code == 401


# ── 2. 会话归属登记与访问控制（依赖级） ────────────────────────

def test_owner_claim_and_access():
    async def scenario():
        await init_owner_table()
        assert await get_owner("s1") is None

        # POST + Form 体 session_id（会话创建/续用形态）→ 首写登记
        await require_session_access(
            _fake_request("POST", _make_token("alice"), form={"session_id": "s1"}))
        assert await get_owner("s1") == "alice"

        # 他人 POST / GET（路径参数形态）→ 403
        with pytest.raises(Exception) as e:
            await require_session_access(
                _fake_request("POST", _make_token("bob"), form={"session_id": "s1"}))
        assert e.value.status_code == 403
        with pytest.raises(Exception) as e:
            await require_session_access(
                _fake_request("GET", _make_token("bob"), path_params={"session_id": "s1"}))
        assert e.value.status_code == 403

        # 本人读 → 放行
        await require_session_access(
            _fake_request("GET", _make_token("alice"), path_params={"session_id": "s1"}))

        # 未登记 + GET（新会话空态）→ 放行
        await require_session_access(
            _fake_request("GET", _make_token("bob"), path_params={"session_id": "s2"}))

        # POST + 路径参数（SSE 之外的 {session_id} 型端点）→ 同样登记
        await require_session_access(
            _fake_request("POST", _make_token("carol"), path_params={"session_id": "s3"}))
        assert await get_owner("s3") == "carol"

        # 无 session_id 的请求 → 仅认证放行（宽容路径）
        await require_session_access(_fake_request("POST", _make_token("dave")))

    asyncio.run(scenario())


def test_owner_claim_first_wins_concurrent():
    """两用户同 POST 未登记会话：INSERT OR IGNORE 先到先得，后到者 403"""
    async def scenario():
        await init_owner_table()
        await require_session_access(
            _fake_request("POST", _make_token("alice"), form={"session_id": "race"}))
        with pytest.raises(Exception) as e:
            await require_session_access(
                _fake_request("POST", _make_token("bob"), form={"session_id": "race"}))
        assert e.value.status_code == 403
        assert await get_owner("race") == "alice"

    asyncio.run(scenario())


# ── 3. 集成（TestClient） ──────────────────────────────────────

def test_no_token_401(client):
    assert client.get("/api/agent/conversation/stream/sX").status_code == 401
    assert client.post("/api/agent/conversation/start").status_code == 401
    assert client.get("/api/export-review").status_code == 401


def test_cross_user_and_claim_flow(client):
    alice = {"Authorization": f"Bearer {_make_token('alice')}"}
    bob = {"Authorization": f"Bearer {_make_token('bob')}"}

    # alice 首次会话 → 登记；随后 alice 读流 → 200
    assert client.post("/api/agent/conversation/start",
                       headers=alice, data={"session_id": "s1"}).status_code == 200
    assert client.get("/api/agent/conversation/stream/s1", headers=alice).status_code == 200

    # bob 对 s1 读写 → 403
    assert client.post("/api/agent/conversation/start",
                       headers=bob, data={"session_id": "s1"}).status_code == 403
    assert client.get("/api/agent/conversation/stream/s1", headers=bob).status_code == 403


def test_owners_persisted_in_db(client, _temp_db):
    alice = {"Authorization": f"Bearer {_make_token('alice')}"}
    client.post("/api/agent/conversation/start",
                headers=alice, data={"session_id": "persist-me"})
    with sqlite3.connect(str(_temp_db)) as conn:
        row = conn.execute(
            "SELECT username FROM session_owners WHERE session_id = 'persist-me'"
        ).fetchone()
    assert row == ("alice",)


# ── 4. Guard：真实 main.py 全部 /api 路由必须挂鉴权 ────────────

def _scan_routes():
    """源码级扫描（不 import main.py——其模块级会加载 ChromaDB/LangGraph 等重型依赖）"""
    src = io.open(BACKEND_DIR / "main.py", encoding="utf-8").read()
    out = []
    for m in re.finditer(r'@app\.(get|post)\("(/api/[^"]+)"', src):
        line_end = src.index("\n", m.start())
        out.append((m.group(2), src[m.start():line_end]))
    return out


def test_guard_all_api_routes_have_auth():
    routes = _scan_routes()
    assert routes, "未找到 /api 路由：wire_review_auth 尚未接线或路由注册变化"
    unwired = [p for p, line in routes if "Depends(require_" not in line]
    assert not unwired, f"以下 /api 路由缺少鉴权依赖: {unwired}"


def test_guard_session_routes_use_session_access():
    """conversation/segment/history 路由必须用 require_session_access（会话级隔离）"""
    routes = _scan_routes()
    session_routes = [(p, l) for p, l in routes
                      if any(k in p for k in ("conversation", "segment", "history"))]
    assert session_routes, "未找到会话级路由"
    wrong = [p for p, l in session_routes if "require_session_access" not in l]
    assert not wrong, f"以下会话路由只做了认证、缺少归属校验: {wrong}"


def test_guard_health_stays_public():
    """/health 供前端端口探测，必须保持无鉴权"""
    src = io.open(BACKEND_DIR / "main.py", encoding="utf-8").read()
    m = re.search(r'@app\.get\("/health"[^\n]*', src)
    assert m, "未找到 /health 路由"
    assert "Depends(" not in m.group(0), "/health 被误挂鉴权，前端端口探测将失效"
