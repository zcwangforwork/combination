"""sec_filter 单元测试 — fail-closed 矩阵与唯一收口（方案 §2.4 / §5 / §7）

覆盖：
1. 密级归一化与标签
2. §2.4 fail-closed 七场景矩阵（无上下文 / claim 合法 / claim 非法 /
   用户密级非法 / chunk 无密级 / mode=off / mode=shadow）
3. 模式开关三态：off / shadow / enforce 下 where 构造与注入行为
4. combine_where 收口合并（$and）
5. overfetch_n 超额召回（×3 封顶 50）
6. denied 登记簿（note / drain / peek / mark_denied_batch / probe_denied）
7. 入库打标收口（stamp_sec_meta / resolve_ingest_sec_level / 防投毒）
8. audit_retrieval 审计汇总投递
"""
import os
import pytest

from app.services import kb_scope
from app.services.rag import sec_filter


# ── 公共夹具：模式/环境/缓存隔离 + 审计投递拦截（不落真库不起线程） ──

@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    saved_env = ["SEC_FILTER_MODE", "SEC_DEFAULT_LEVEL", "SEC_UPLOAD_DEFAULT",
                 "SEC_OVERFETCH", "SEC_USER_CACHE_TTL"]
    for k in saved_env:
        monkeypatch.delenv(k, raising=False)
    # 审计投递改为捕获（避免启动写线程/建库）
    captured = {"admin": [], "retrieval": []}
    import app.services.sec_audit as sec_audit_mod
    monkeypatch.setattr(sec_audit_mod, "enqueue_admin_audit",
                        lambda row: captured["admin"].append(row))
    monkeypatch.setattr(sec_audit_mod, "enqueue_retrieval_audit",
                        lambda row: captured["retrieval"].append(row))
    # 模式覆盖复位
    monkeypatch.setattr(sec_filter, "_mode_override", None)
    monkeypatch.setattr(sec_filter, "_mode_overridden_by", None)
    # 用户缓存清空
    monkeypatch.setattr(sec_filter, "_user_level_cache", {})
    # 上下文复位
    kb_scope._kb_user.set(None)
    # denied 登记簿（ContextVar）复位，避免跨测试残留
    sec_filter._denied_chunks.set(None)
    yield {"captured": captured}
    kb_scope._kb_user.set(None)
    sec_filter._denied_chunks.set(None)


def _set_user(username="alice", is_admin=False, sec_level=None):
    kb_scope.set_kb_user(username, is_admin, sec_level)


# ── 1. 归一化 ────────────────────────────────────────────────

def test_normalize_sec_level_valid():
    assert sec_filter.normalize_sec_level(0) == 0
    assert sec_filter.normalize_sec_level(3) == 3
    assert sec_filter.normalize_sec_level("2") == 2
    assert sec_filter.normalize_sec_level(1.0) == 1


def test_normalize_sec_level_invalid():
    # bool 显式排除（True 会被 isinstance(int) 误判为 1）
    assert sec_filter.normalize_sec_level(True) is None
    assert sec_filter.normalize_sec_level(None) is None
    assert sec_filter.normalize_sec_level(-1) is None
    assert sec_filter.normalize_sec_level(4) is None
    assert sec_filter.normalize_sec_level("abc") is None
    assert sec_filter.normalize_sec_level([1]) is None


def test_sec_label():
    assert sec_filter.sec_label(0) == "公开"
    assert sec_filter.sec_label(3) == "机密"
    assert sec_filter.sec_label(None) == "未标注"


# ── 2. §2.4 fail-closed 矩阵 ─────────────────────────────────

def test_matrix_no_user_context_level0():
    """场景①：无用户上下文 → 只放行 public 级"""
    assert sec_filter.current_user_sec_level() == 0
    assert sec_filter.build_sec_where(None) == {"sec_level": {"$lte": 0}}
    # 上线 enforce 后无上下文检索只看得见 sec_level=0
    assert sec_filter.candidate_visible({"sec_level": 0}, None) is True
    assert sec_filter.candidate_visible({"sec_level": 1}, None) is False


def test_matrix_claim_valid():
    """场景②：JWT claim 合法 → 直接采用"""
    _set_user(sec_level=2)
    assert sec_filter.resolve_identity_sec_level("alice", 2) == 2


def test_matrix_claim_invalid_fallback_zero():
    """场景③：claim 非法 → 告警 + 查库失败回退 → 按 0"""
    monkeypatch = pytest.MonkeyPatch()
    # 查库通道直接失败（等价 PG 不可达 → None）
    monkeypatch.setattr(sec_filter, "lookup_user_sec_level",
                        lambda u: None)
    try:
        lvl = sec_filter.resolve_identity_sec_level("alice", 99)
    finally:
        monkeypatch.undo()
    assert lvl == 0  # fail-closed


def test_matrix_user_level_invalid_treated_as_zero():
    """场景④：用户密级非法/越界 → 按 0 处理"""
    _set_user(sec_level=7)
    assert sec_filter.current_user_sec_level() == 0
    sec_filter.build_sec_where(7)  # 触发告警路径
    assert sec_filter.build_sec_where("bad") == {"sec_level": {"$lte": 0}}


def test_matrix_chunk_missing_sec_treated_as_secret():
    """场景⑤：chunk 无 sec_level / 非法 → 按 3(secret)，仅最高密级用户可见"""
    assert sec_filter.candidate_visible({}, 3) is True
    assert sec_filter.candidate_visible({}, 2) is False
    assert sec_filter.candidate_visible({}, 0) is False
    assert sec_filter.candidate_visible({"sec_level": "x"}, 3) is True
    assert sec_filter.candidate_visible({"sec_level": "x"}, 1) is False
    # 正常可见性：chunk ≤ user
    assert sec_filter.candidate_visible({"sec_level": 2}, 2) is True
    assert sec_filter.candidate_visible({"sec_level": 3}, 2) is False


def test_matrix_mode_off_returns_none():
    """场景⑥：mode=off 全局回滚通道 → 无 where（上线前行为）"""
    sec_filter.set_mode_override("off", "test")
    assert sec_filter.build_sec_where(2) is None
    assert sec_filter.effective_query_where() is None
    assert sec_filter.combine_where({"source_file": "a.md"}) == {"source_file": "a.md"}


def test_matrix_mode_shadow_no_inject_but_marks():
    """场景⑦：mode=shadow → 不实际过滤，denied 照常复核标记"""
    sec_filter.set_mode_override("shadow", "test")
    assert sec_filter.effective_query_where() is None
    _set_user(sec_level=1)
    docs = ["公开内容", "机密内容"]
    metas = [{"sec_level": 0}, {"sec_level": 3}]
    sec_filter.mark_denied_batch(docs, metas, "uploads", 1)
    denied = sec_filter.drain_denied()
    assert len(denied) == 1
    assert denied[0]["sec_level"] == 3


# ── 3. enforce 模式 where 注入 ────────────────────────────────

def test_enforce_effective_query_where():
    sec_filter.set_mode_override("enforce", "test")
    _set_user(sec_level=2)
    assert sec_filter.effective_query_where() == {"sec_level": {"$lte": 2}}


def test_mode_override_validation_and_reset(monkeypatch):
    monkeypatch.setenv("SEC_FILTER_MODE", "off")
    assert sec_filter.get_mode() == "off"  # env 缺省生效
    sec_filter.set_mode_override("enforce", "tester")
    assert sec_filter.get_mode() == "enforce"  # 运行时覆盖优先
    assert sec_filter.mode_overridden_by() == "tester"
    with pytest.raises(ValueError):
        sec_filter.set_mode_override("bogus", "tester")


def test_cfg_mode_invalid_env_falls_back_shadow(monkeypatch):
    monkeypatch.setenv("SEC_FILTER_MODE", "nonsense")
    assert sec_filter.cfg_mode() == "shadow"


def test_combine_where_merges_with_and():
    sec_filter.set_mode_override("enforce", "test")
    _set_user(sec_level=1)
    extra = {"source_file": {"$in": ["a.md"]}}
    merged = sec_filter.combine_where(extra)
    assert merged == {"$and": [extra, {"sec_level": {"$lte": 1}}]}
    # 无 extra 时仅返回 sec 条件
    assert sec_filter.combine_where(None) == {"sec_level": {"$lte": 1}}


def test_combine_where_shadow_passthrough():
    sec_filter.set_mode_override("shadow", "test")
    extra = {"source_file": {"$in": ["a.md"]}}
    assert sec_filter.combine_where(extra) == extra


# ── 4. overfetch ─────────────────────────────────────────────

def test_overfetch_n(monkeypatch):
    monkeypatch.delenv("SEC_OVERFETCH", raising=False)
    assert sec_filter.overfetch_n(5) == 15
    assert sec_filter.overfetch_n(30) == 50  # 封顶
    assert sec_filter.overfetch_n(100) == 50
    monkeypatch.setenv("SEC_OVERFETCH", "2")
    assert sec_filter.overfetch_n(5) == 10
    monkeypatch.setenv("SEC_OVERFETCH", "abc")  # 非法回退 3
    assert sec_filter.overfetch_n(5) == 15


# ── 5. denied 登记簿 ─────────────────────────────────────────

def test_note_and_drain_denied():
    sec_filter.note_denied("保密文本甲", {"source_file": "a.docx", "sec_level": 2}, "c1")
    sec_filter.note_denied("保密文本乙", {"source_file": "b.docx"}, "c1")  # 无密级 → 3
    denied = sec_filter.drain_denied()
    assert [d["sec_level"] for d in denied] == [2, 3]
    assert denied[1]["sec_label"] == "未标注"
    assert sec_filter.drain_denied() == []  # drain 后清空
    assert all(len(d["text"]) <= 2000 for d in denied)


def test_probe_denied_marks_and_silent_on_failure():
    class FakeColl:
        def query(self, **kw):
            assert "where" not in kw or kw.get("where") is None  # 探针有意无 where
            return {"ids": [["x1"]],
                    "documents": [["机密段落"]],
                    "metadatas": [[{"source_file": "s.doc", "sec_level": 3}]]}

    class BadColl:
        def query(self, **kw):
            raise RuntimeError("boom")

    sec_filter.probe_denied(FakeColl(), [0.1], 5, "c", 0)
    assert len(sec_filter.peek_denied()) == 1
    sec_filter.probe_denied(BadColl(), [0.1], 5, "c", 0)  # 失败静默不抛


# ── 6. 用户密级解析（查库 + TTL 缓存） ────────────────────────

def test_lookup_user_sec_level_pg_failure_returns_none(monkeypatch):
    """PG 连不上 → None（调用方回退 0，fail-closed）"""
    import sys
    import types

    class _FakeConnect:
        def __init__(self, *a, **kw):
            raise ConnectionError("pg down")

    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg.connect = _FakeConnect
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    assert sec_filter.lookup_user_sec_level("bob") is None


def test_user_level_cache_hit_and_invalidate(monkeypatch):
    """TTL 缓存命中不触库；invalidate 后重新查库（失败 → None）"""
    import sys
    import time as _t
    import types

    connect_calls = {"n": 0}

    class _FakeConnect:
        def __init__(self, *a, **kw):
            connect_calls["n"] += 1
            raise ConnectionError("pg down")

    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg.connect = _FakeConnect
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    # 预置新鲜缓存 → 命中，不触库
    sec_filter._user_level_cache["carol"] = (2, _t.time())
    assert sec_filter.lookup_user_sec_level("carol") == 2
    assert connect_calls["n"] == 0

    # 失效后重查 → 触库（失败被吞 → None，fail-closed）
    sec_filter.invalidate_user_level_cache("carol")
    assert sec_filter.lookup_user_sec_level("carol") is None
    assert connect_calls["n"] == 1


# ── 7. 入库打标收口 ──────────────────────────────────────────

def test_resolve_ingest_sec_level_priority():
    # 显式 > 上下文（上传者密级）> 脚本缺省 3
    assert sec_filter.resolve_ingest_sec_level(1) == (1, "manual")
    _set_user(sec_level=2)
    assert sec_filter.resolve_ingest_sec_level(None) == (2, "inherit")
    kb_scope._kb_user.set(None)
    assert sec_filter.resolve_ingest_sec_level(None) == (3, "inherit")  # SEC_DEFAULT_LEVEL


def test_resolve_ingest_upload_default_max(monkeypatch):
    monkeypatch.setenv("SEC_UPLOAD_DEFAULT", "max")
    _set_user(sec_level=1)
    assert sec_filter.resolve_ingest_sec_level(None) == (3, "inherit")


def test_stamp_sec_meta_fields():
    meta = sec_filter.stamp_sec_meta({"source_file": "a.md"}, sec_level=2,
                                     acl_version="v-test")
    assert meta["sec_level"] == 2
    assert meta["sec_label"] == "秘密"
    assert meta["sec_source"] == "manual"
    assert meta["acl_version"] == "v-test"
    assert "sec_updated_at" in meta
    # 缺省 acl_version 形如 live-YYYYMMDD
    meta2 = sec_filter.stamp_sec_meta({}, sec_level=0)
    assert meta2["acl_version"].startswith("live-")


def test_check_upload_sec_level_permission():
    # 普通用户标高于本人密级 → 拒绝（防投毒 §4.1）
    _set_user(is_admin=False, sec_level=1)
    with pytest.raises(ValueError):
        sec_filter.check_upload_sec_level_permission(2, is_admin=False)
    sec_filter.check_upload_sec_level_permission(1, is_admin=False)  # 等于本人 → 允许
    sec_filter.check_upload_sec_level_permission(None, is_admin=False)  # 未指定 → 允许
    # ADMIN 可标任意
    sec_filter.check_upload_sec_level_permission(3, is_admin=True)
    # 无上下文（脚本路径）不适用
    kb_scope._kb_user.set(None)
    sec_filter.check_upload_sec_level_permission(3, is_admin=False)


# ── 8. 检索审计汇总 ──────────────────────────────────────────

def test_audit_retrieval_enqueues_summary(_isolated_env):
    sec_filter.set_mode_override("enforce", "test")
    _set_user(username="dave", sec_level=1)
    sec_filter.note_denied("秘密内容", {"source_file": "s.docx", "sec_level": 2}, "c")
    sec_filter.audit_retrieval(
        query="胰岛素泵 密封 试验 数据",
        scope_summary="shared+uploads",
        results=[{"meta": {"sec_level": 1}}, {"meta": {"sec_level": 0}}],
    )
    rows = _isolated_env["captured"]["retrieval"]
    assert len(rows) == 1
    row = rows[0]
    assert row["username"] == "dave"
    assert row["sec_level_at_query"] == 1
    assert row["mode"] == "enforce"
    assert row["returned_count"] == 2
    assert row["denied_count"] == 1
    assert row["max_hit_level"] == 1
    assert row["denied_files"] == ["s.docx"]
    assert len(row["query_digest"]) == 16
