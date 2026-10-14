# -*- coding: utf-8 -*-
"""mcp_manager 单元测试（MCP 外部工具集成新增）

覆盖（全部离线，唯一网络调用是 127.0.0.1 保留端口的 connection-refused）：
1. 配置校验 validate_server_config：transport/必填字段/类型检查
2. CRUD：新增（默认 enabled）/重名拒绝/非法名拒绝/更新保留元数据/删除
3. ${VAR} 环境变量展开：已设置替换、未设置记 missing 并置空
4. _build_connection：剥离管理元数据、transport 推断
5. load_mcp_tools 容错隔离：坏服务器（拒绝连接）+ disabled 服务器 → 返回 []
   且状态记录 error/disabled（不抛异常、不拖垮整体）
6. 工具集合入守卫：agent_tools.create_audit_tools 在 MCP 缓存非空时合入、
   为空时与内置 5 工具一致；chat_rag._build_free_chat_tools 未加载 MCP 时
   返回 []（保持原直接回答路径）
"""
import asyncio

import pytest

import mcp_manager
from mcp_manager import (
    _build_connection, _expand_env, add_server, delete_server,
    get_server, list_servers, update_server, validate_server_config,
)


class _FakeTool:
    """最小 BaseTool 替身（只用到 .name/.description 属性）"""

    def __init__(self, name, description="fake"):
        self.name = name
        self.description = description


@pytest.fixture(autouse=True)
def _temp_cfg(tmp_path, monkeypatch):
    """每个测试用独立临时配置文件，避免污染 data/mcp_servers.json"""
    cfg = tmp_path / "mcp_servers.json"
    monkeypatch.setattr(mcp_manager, "_SERVERS_FILE", str(cfg))
    yield cfg


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    """每个测试还原模块级工具缓存，避免用例间串扰"""
    monkeypatch.setattr(mcp_manager, "_MCP_TOOLS", [])
    monkeypatch.setattr(mcp_manager, "_TOOL_SERVER", {})
    monkeypatch.setattr(mcp_manager, "_SERVER_STATUS", {})


# ── 1. 配置校验 ───────────────────────────────────────────────

def test_validate_rejects_bad_transport():
    assert validate_server_config({"transport": "carrier-pigeon", "url": "http://x"}) is not None


def test_validate_rejects_stdio_without_command():
    assert validate_server_config({"transport": "stdio"}) is not None


def test_validate_rejects_http_without_url():
    assert validate_server_config({"transport": "streamable_http"}) is not None


def test_validate_rejects_non_http_url():
    assert validate_server_config({"url": "ftp://x"}) is not None


def test_validate_rejects_bad_args_type():
    assert validate_server_config({"command": "python", "args": "x.py"}) is not None


def test_validate_accepts_stdio_and_http_and_inference():
    assert validate_server_config(
        {"transport": "stdio", "command": "python", "args": ["s.py"]}) is None
    assert validate_server_config({"url": "http://h:1/mcp"}) is None  # url → 推断 http


# ── 2. CRUD ──────────────────────────────────────────────────

def test_add_defaults_enabled_and_rejects_dup_and_bad_name(_temp_cfg):
    s = add_server("test_http", {"url": "http://h:1/mcp", "description": "测试"})
    assert s.get("enabled") is True
    with pytest.raises(ValueError):
        add_server("test_http", {"url": "http://h:2/mcp"})       # 重名
    with pytest.raises(ValueError):
        add_server("bad name!", {"command": "python"})           # 非法名


def test_update_preserves_meta_and_missing_returns_none(_temp_cfg):
    add_server("srv", {"url": "http://h:1/mcp"})
    u = update_server("srv", {"url": "http://h:2/mcp", "description": "改"})
    assert u["url"] == "http://h:2/mcp"
    assert u["enabled"] is True and u["description"] == "改"
    assert update_server("nope", {"url": "http://h:3/mcp"}) is None


def test_list_contains_runtime_and_delete_removes(_temp_cfg):
    add_server("srv", {"url": "http://h:1/mcp"})
    assert any("runtime" in x for x in list_servers())
    assert get_server("srv") is not None
    assert delete_server("srv") is True
    assert get_server("srv") is None
    assert delete_server("srv") is False


# ── 3/4. 环境变量展开 + 连接构建 ──────────────────────────────

def test_expand_env_substitutes_and_tracks_missing(monkeypatch):
    monkeypatch.setenv("MCP_TEST_KEY", "sk-abc")
    missing = set()
    out = _expand_env({"Authorization": "Bearer ${MCP_TEST_KEY}",
                       "x": "${MCP_TEST_MISSING_VAR}"}, missing)
    assert out["Authorization"] == "Bearer sk-abc"
    assert out["x"] == ""
    assert missing == {"MCP_TEST_MISSING_VAR"}


def test_build_connection_strips_meta_and_infers_transport():
    conn, missing = _build_connection({
        "transport": "streamable_http",
        "url": "http://h:1/mcp",
        "enabled": True, "description": "d", "search_priority": True,
    })
    assert missing == set()
    assert conn["transport"] == "streamable_http"
    assert "enabled" not in conn and "description" not in conn
    assert "search_priority" not in conn  # 管理元数据必须剥离

    conn2, _ = _build_connection({"url": "http://h:1/mcp"})
    assert conn2["transport"] == "streamable_http"  # url → 推断


# ── 5. load_mcp_tools 容错隔离 ───────────────────────────────

def test_load_fault_isolation_and_disabled_skip(_temp_cfg):
    """坏服务器（拒绝连接，快速失败）+ disabled 服务器 → [] 且状态可查，不抛异常"""
    add_server("bogus_http", {"url": "http://127.0.0.1:59999/mcp",
                              "transport": "streamable_http"})
    add_server("disabled_one", {"url": "http://h:1/mcp", "enabled": False})

    tools = asyncio.run(mcp_manager.load_mcp_tools(exclude_names=set()))
    assert tools == []
    status = mcp_manager.get_server_status()
    assert status["bogus_http"]["status"] == "error"
    assert "拒绝" in status["bogus_http"]["message"] or status["bogus_http"]["message"]
    assert status["disabled_one"]["status"] == "disabled"


# ── 6. 工具集合入守卫 ─────────────────────────────────────────

def test_create_audit_tools_merges_mcp_cache(monkeypatch):
    """MCP 缓存非空 → create_audit_tools 合入；为空 → 与内置 5 工具一致"""
    import agent_tools

    monkeypatch.setattr(mcp_manager, "_MCP_TOOLS", [_FakeTool("web_search")])
    monkeypatch.setattr(mcp_manager, "_TOOL_SERVER", {"web_search": "qianwen"})
    merged = agent_tools.create_audit_tools(None, None)
    names = [t.name for t in merged]
    assert names[:5] == ["parse_document", "rag_search", "check_regulation",
                         "assess_completeness", "audit_section"]
    assert "web_search" in names

    monkeypatch.setattr(mcp_manager, "_MCP_TOOLS", [])
    builtin_only = agent_tools.create_audit_tools(None, None)
    assert [t.name for t in builtin_only] == [
        "parse_document", "rag_search", "check_regulation",
        "assess_completeness", "audit_section",
    ]


def test_free_chat_tools_empty_without_mcp(monkeypatch):
    """MCP 未加载 → chat_rag._build_free_chat_tools 返回 []（保持原直接回答路径）"""
    import chat_rag

    monkeypatch.setattr(mcp_manager, "_MCP_TOOLS", [])
    assert chat_rag._build_free_chat_tools(None, None) == []

    monkeypatch.setattr(mcp_manager, "_MCP_TOOLS", [_FakeTool("web_search")])
    tools = chat_rag._build_free_chat_tools(None, None)
    got = {t.name for t in tools}
    assert got == {"rag_search", "check_regulation", "web_search"}
