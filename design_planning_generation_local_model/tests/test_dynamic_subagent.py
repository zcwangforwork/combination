"""
test_dynamic_subagent.py - 动态子代理派生（spawn_subagent）测试

覆盖:
- 白名单守卫：写效果工具 / spawn_subagent 自身不得进入白名单（防递归、防越权写）
- get_subagent_tools 正常解析与未知名称拒绝
- spawn_subagent 参数校验分支（非法工具名 → 引导性错误 JSON）
- ok 路径（fake 子代理，不打 Ollama）：返回结构、elapsed_s
- 超长结果截断保护（8000 字符上限）
- 滑动窗口限流（超上限拒绝；窗口滑过恢复）
- 单个子代理超时分支
- create_dynamic_agent 离线组装（不发起 LLM 调用）
- spawn_subagent 已注册进 PHASE1_TOOLS
"""
import sys
import json
import asyncio
import pytest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def _reset_spawn_state():
    """每个测试前后清空滑动窗口状态，避免用例间串扰"""
    from app.services import agent_tools
    agent_tools._SUBAGENT_SPAWN_TIMES.clear()
    yield
    agent_tools._SUBAGENT_SPAWN_TIMES.clear()


def _fake_agent_factory(content: str, delay: float = 0.0):
    """返回伪造的 create_dynamic_agent，产出固定 content 的子代理（不打 Ollama）"""
    from langchain_core.messages import AIMessage

    class _FakeAgent:
        async def ainvoke(self, state, config=None):
            if delay:
                await asyncio.sleep(delay)
            return {"messages": [AIMessage(content=content)]}

    def _factory(system_prompt, tool_names, **kwargs):
        return _FakeAgent()

    return _factory


class TestWhitelistGuard:
    def _phase1_names(self):
        """PHASE1_TOOLS 混有 BaseTool(.name) 与普通函数(.__name__)，按引擎 _tool_name 约定取名"""
        from app.services.agent_tools import PHASE1_TOOLS
        return {
            getattr(t, "name", None) or getattr(t, "__name__", "") or ""
            for t in PHASE1_TOOLS
        }

    def test_dangerous_tools_excluded(self):
        """写效果工具与派生工具自身必须在白名单外"""
        from app.services.agent_tools import SUBAGENT_TOOL_WHITELIST
        for name in (
            "spawn_subagent", "write_chapter", "build_docx", "revise_section",
            "modify_attachment", "generate_section", "design_outline",
        ):
            assert name not in SUBAGENT_TOOL_WHITELIST, f"{name} 不应出现在子代理白名单"

    def test_whitelist_tools_all_registered(self):
        """白名单里的工具必须是 PHASE1_TOOLS 中真实存在的工具对象"""
        from app.services.agent_tools import SUBAGENT_TOOL_WHITELIST
        for name in SUBAGENT_TOOL_WHITELIST:
            assert name in self._phase1_names(), f"白名单工具 {name} 未在 PHASE1_TOOLS 注册"

    def test_spawn_registered_in_phase1(self):
        assert "spawn_subagent" in self._phase1_names()


class TestGetSubagentTools:
    def test_valid_names(self):
        from app.services.agent_tools import get_subagent_tools
        tools = get_subagent_tools(["search_kb", "web_search"])
        assert [t.name for t in tools] == ["search_kb", "web_search"]

    def test_unknown_name_raises(self):
        from app.services.agent_tools import get_subagent_tools
        with pytest.raises(ValueError):
            get_subagent_tools(["search_kb", "rm_rf_everything"])


class TestSpawnValidation:
    async def test_invalid_tool_returns_guidance(self):
        """非法工具名 → error JSON 且附可用工具清单（引导模型重试）"""
        from app.services.agent_tools import spawn_subagent
        out = json.loads(await spawn_subagent.ainvoke({
            "role_name": "审校员",
            "task_description": "审查第2章",
            "role_instructions": "你是审校员",
            "allowed_tools": "search_kb, build_docx",
        }))
        assert out["status"] == "error"
        assert "build_docx" in out["message"]
        assert "search_kb" in out["message"]  # 可用工具清单

    async def test_spawn_self_rejected(self):
        """子代理不可再派生（spawn_subagent 不在白名单，必须被拒）"""
        from app.services.agent_tools import spawn_subagent
        out = json.loads(await spawn_subagent.ainvoke({
            "role_name": "编排者",
            "task_description": "再派生一层",
            "role_instructions": "你是编排者",
            "allowed_tools": "spawn_subagent",
        }))
        assert out["status"] == "error"


class TestSpawnExecution:
    """执行路径用 fake 子代理替换 create_dynamic_agent，不打 Ollama"""

    async def test_ok_path(self, monkeypatch):
        from app.services import agent_tools, subagents
        monkeypatch.setattr(
            subagents, "create_dynamic_agent",
            _fake_agent_factory("发现3处问题：1. 缺少条款号..."),
        )
        out = json.loads(await agent_tools.spawn_subagent.ainvoke({
            "role_name": "标准审校员",
            "task_description": "审查第2章，原文：...",
            "role_instructions": "职责+知识+流程+格式",
            "allowed_tools": "search_kb, web_search",
        }))
        assert out["status"] == "ok"
        assert out["role"] == "标准审校员"
        assert out["tools"] == ["search_kb", "web_search"]
        assert "发现3处问题" in out["result"]
        assert out["elapsed_s"] >= 0

    async def test_empty_tools_defaults_to_search_kb(self, monkeypatch):
        from app.services import agent_tools, subagents
        monkeypatch.setattr(
            subagents, "create_dynamic_agent",
            _fake_agent_factory("ok"),
        )
        out = json.loads(await agent_tools.spawn_subagent.ainvoke({
            "role_name": "研究员",
            "task_description": "查证标准",
            "role_instructions": "你是研究员",
            "allowed_tools": "",
        }))
        assert out["status"] == "ok"
        assert out["tools"] == ["search_kb"]

    async def test_result_truncation(self, monkeypatch):
        """超长结果必须截断，保护主代理上下文"""
        from app.services import agent_tools, subagents
        monkeypatch.setattr(
            subagents, "create_dynamic_agent",
            _fake_agent_factory("长" * 12000),
        )
        out = json.loads(await agent_tools.spawn_subagent.ainvoke({
            "role_name": "话痨",
            "task_description": "任务",
            "role_instructions": "你是话痨",
        }))
        assert out["status"] == "ok"
        assert out["truncated"] is True
        assert len(out["result"]) <= agent_tools._SUBAGENT_RESULT_MAX_CHARS + 50

    async def test_timeout_branch(self, monkeypatch):
        from app.services import agent_tools, subagents
        monkeypatch.setattr(
            subagents, "create_dynamic_agent",
            _fake_agent_factory("slow", delay=0.5),
        )
        monkeypatch.setattr(agent_tools, "SUBAGENT_SPAWN_TIMEOUT_SECONDS", 0.1)
        out = json.loads(await agent_tools.spawn_subagent.ainvoke({
            "role_name": "慢代理",
            "task_description": "任务",
            "role_instructions": "你是慢代理",
        }))
        assert out["status"] == "error"
        assert "超时" in out["message"]


class TestRateLimit:
    async def test_over_limit_rejected(self, monkeypatch):
        from app.services import agent_tools
        monkeypatch.setattr(agent_tools, "SUBAGENT_MAX_SPAWNS_PER_WINDOW", 0)
        out = json.loads(await agent_tools.spawn_subagent.ainvoke({
            "role_name": "r", "task_description": "t", "role_instructions": "i",
        }))
        assert out["status"] == "error"
        assert "上限" in out["message"]

    async def test_window_sliding_recovery(self, monkeypatch):
        """窗口外的过期时间戳应被清理，之后可再次派生"""
        import time as _time
        from app.services import agent_tools, subagents
        # 预置一个早已过期的派生记录 + fake 子代理（走通限流之后的执行分支）
        agent_tools._SUBAGENT_SPAWN_TIMES.append(
            _time.monotonic() - agent_tools.SUBAGENT_SPAWN_WINDOW_SECONDS - 1
        )
        monkeypatch.setattr(agent_tools, "SUBAGENT_MAX_SPAWNS_PER_WINDOW", 1)
        monkeypatch.setattr(subagents, "create_dynamic_agent", _fake_agent_factory("ok"))
        out = json.loads(await agent_tools.spawn_subagent.ainvoke({
            "role_name": "r", "task_description": "t", "role_instructions": "i",
        }))
        assert out["status"] == "ok"
        # 过期记录被清理后仅剩本次派生
        assert len(agent_tools._SUBAGENT_SPAWN_TIMES) == 1


class TestDynamicAgentOffline:
    def test_create_dynamic_agent_builds(self):
        """create_dynamic_agent 离线组装：不发起 LLM 调用即可构建 compiled graph"""
        from app.services.subagents import create_dynamic_agent
        agent = create_dynamic_agent(
            system_prompt="你是测试审校员。只做测试。",
            tool_names=["search_kb"],
        )
        assert hasattr(agent, "ainvoke")

    def test_create_dynamic_agent_rejects_unknown_tool(self):
        from app.services.subagents import create_dynamic_agent
        with pytest.raises(ValueError):
            create_dynamic_agent("x", ["no_such_tool"])
