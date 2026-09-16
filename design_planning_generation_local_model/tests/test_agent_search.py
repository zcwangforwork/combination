"""
test_agent_search.py — AgentSearchService 和 SyncAgentSearchService 单元测试
"""
import os
import sys
import pytest
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestSyncAgentSearchService:
    """SyncAgentSearchService 测试"""

    def test_returns_empty_when_no_api_key(self, monkeypatch):
        """无 API Key 时返回空结果"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from app.services.agent_search import SyncAgentSearchService

        service = SyncAgentSearchService(api_key="")
        assert service.available is False

        text, files = service.search_regulations(
            chapter_name="风险分析",
            product_type="血糖仪"
        )
        assert text == ""
        assert files == []

    def test_fallback_on_import_error(self, monkeypatch):
        """SDK 未安装时 available=False 且返回空"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

        # 模拟 SDK 不可用
        import app.services.agent_search as agent_mod
        monkeypatch.setattr(agent_mod, "_sdk_available", False)

        service = agent_mod.SyncAgentSearchService()
        assert service.available is False

        text, files = service.search_regulations(
            chapter_name="概述",
            product_type="胰岛素泵"
        )
        assert text == ""
        assert files == []

    def test_service_structure_matches_web_search(self):
        """验证接口与 SyncWebSearchService 兼容"""
        from app.services.agent_search import SyncAgentSearchService
        from app.services.web_search import SyncWebSearchService

        # 两者都有 search_regulations 方法
        assert hasattr(SyncAgentSearchService, "search_regulations")
        assert hasattr(SyncWebSearchService, "search_regulations")

        # available 是实例属性（在 __init__ 中设置）
        agent_svc = SyncAgentSearchService(api_key="")
        web_svc = SyncWebSearchService()
        assert hasattr(agent_svc, "available")
        assert hasattr(web_svc, "playwright_available")


class TestProxyConfig:
    """代理配置测试"""

    def test_no_proxy_when_not_configured(self, monkeypatch):
        """未配置代理时只返回 NO_PROXY（如系统已设置）"""
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("CLAUDE_HTTP_PROXY", raising=False)
        monkeypatch.delenv("CLAUDE_HTTPS_PROXY", raising=False)
        monkeypatch.delenv("NO_PROXY", raising=False)

        from app.services.agent_search import _get_proxy_env
        result = _get_proxy_env()
        # 没有 HTTP_PROXY/HTTPS_PROXY 时，不应设置 NODE_USE_ENV_PROXY
        assert "HTTP_PROXY" not in result
        assert "HTTPS_PROXY" not in result
        assert "NODE_USE_ENV_PROXY" not in result

    def test_standard_proxy_vars(self, monkeypatch):
        """标准 HTTP_PROXY/HTTPS_PROXY 被读取"""
        monkeypatch.setenv("HTTP_PROXY", "http://proxy:8080")
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8443")
        monkeypatch.delenv("CLAUDE_HTTP_PROXY", raising=False)
        monkeypatch.delenv("CLAUDE_HTTPS_PROXY", raising=False)

        from app.services.agent_search import _get_proxy_env
        result = _get_proxy_env()
        assert result["HTTP_PROXY"] == "http://proxy:8080"
        assert result["HTTPS_PROXY"] == "http://proxy:8443"
        assert result["NODE_USE_ENV_PROXY"] == "1"

    def test_claude_prefix_override(self, monkeypatch):
        """CLAUDE_ 前缀变量优先级更高"""
        monkeypatch.setenv("HTTP_PROXY", "http://system:8080")
        monkeypatch.setenv("CLAUDE_HTTP_PROXY", "http://custom:9999")
        monkeypatch.delenv("HTTPS_PROXY", raising=False)

        from app.services.agent_search import _get_proxy_env
        result = _get_proxy_env()
        assert result["HTTP_PROXY"] == "http://custom:9999"
        # system proxy 不应出现
        assert "http://system:8080" not in result.values()

    def test_no_node_env_proxy_without_http_proxy(self, monkeypatch):
        """没有 HTTP_PROXY 时不设置 NODE_USE_ENV_PROXY"""
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("CLAUDE_HTTP_PROXY", raising=False)
        monkeypatch.delenv("CLAUDE_HTTPS_PROXY", raising=False)

        from app.services.agent_search import _get_proxy_env
        result = _get_proxy_env()
        assert "NODE_USE_ENV_PROXY" not in result


class TestAgentSearchService:
    """AgentSearchService 测试"""

    def test_unavailable_without_key_and_sdk(self, monkeypatch):
        """无 key 无 SDK 时 available=False"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        import app.services.agent_search as agent_mod
        monkeypatch.setattr(agent_mod, "_sdk_available", False)

        service = agent_mod.AgentSearchService(api_key="")
        assert service.available is False

    def test_available_with_key_and_sdk(self, monkeypatch):
        """有 key 有 SDK 时 available=True"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        import app.services.agent_search as agent_mod
        monkeypatch.setattr(agent_mod, "_sdk_available", True)

        service = agent_mod.AgentSearchService(api_key="sk-ant-test")
        assert service.available is True

    def test_research_returns_none_when_unavailable(self, monkeypatch):
        """不可用时 research_chapter 返回 None"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        import app.services.agent_search as agent_mod
        monkeypatch.setattr(agent_mod, "_sdk_available", False)

        service = agent_mod.AgentSearchService(api_key="")
        import asyncio
        result = asyncio.run(service.research_chapter("概述", "血糖仪"))
        assert result is None

    def test_build_research_prompt_contains_keywords(self):
        """研究提示词包含正确的关键词"""
        import app.services.agent_search as agent_mod

        service = agent_mod.AgentSearchService(api_key="test")
        prompt = service._build_research_prompt(
            chapter_name="风险分析",
            product_type="胰岛素泵",
            product_params="流量精度±5%",
            doc_type="risk_management_report"
        )

        assert "风险分析" in prompt
        assert "胰岛素泵" in prompt
        assert "流量精度±5%" in prompt
        assert "风险管理报告" in prompt
        assert "ISO 14971" in prompt
        assert "GB" in prompt
