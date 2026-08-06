"""
智能体测试
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.resolver import resolve_entity, COMMON_ALIASES
from src.agents.base import FinancialAgentBase
from src.utils.validators import validate_agent_envelope, validate_tool_request


class TestEntityResolution:
    """实体解析测试（无 LLM 模式，走别名表匹配）"""

    def test_resolve_common_alias(self):
        """别名表精确匹配"""
        result = resolve_entity("分析茅台", llm=None)
        assert result["stock_code"] == "600519"
        assert result["stock_name"] == "贵州茅台"
        assert result["confidence"] >= 0.9

    def test_resolve_full_name(self):
        """全称匹配"""
        result = resolve_entity("科大讯飞怎么样", llm=None)
        assert result["stock_code"] == "002230"
        assert result["stock_name"] == "科大讯飞"

    def test_resolve_by_code(self):
        """直接股票代码"""
        result = resolve_entity("600519", llm=None)
        assert result["stock_code"] == "600519"

    def test_resolve_not_found(self):
        """无法识别"""
        result = resolve_entity("xyz_not_exist", llm=None)
        assert result["action"] == "not_found"


class TestValidator:
    """校验器测试"""

    def test_valid_envelope(self):
        data = {
            "agent_name": "Test",
            "status": "success",
            "fact_sheet": {"roe": 0.25},
            "brief_summary": "测试",
            "confidence_score": 80,
        }
        valid, envelope, error = validate_agent_envelope(data)
        assert valid is True
        assert envelope is not None
        assert error is None

    def test_invalid_envelope_missing_field(self):
        data = {
            "agent_name": "Test",
        }
        valid, envelope, error = validate_agent_envelope(data)
        assert valid is False
        assert error is not None

    def test_valid_tool_request(self):
        data = {
            "tool_name": "test_tool",
            "tool_description": "测试工具",
            "reason": "需要测试",
            "urgency": "medium",
            "agent_id": "test_agent",
        }
        valid, request, error = validate_tool_request(data)
        assert valid is True
        assert request is not None

    def test_invalid_tool_request(self):
        data = {
            "tool_name": "test",
        }
        valid, request, error = validate_tool_request(data)
        assert valid is False


class TestCommonAliases:
    """常见别名测试"""

    def test_alias_count(self):
        assert len(COMMON_ALIASES) >= 10

    def test_alias_format(self):
        for alias, (code, name) in COMMON_ALIASES.items():
            assert len(alias) >= 1
            assert len(code) >= 4
            assert len(name) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
