"""
状态定义和校验器测试
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.state import (
    AgentEnvelope, ToolRequest, DebateArgument, EntityResolution,
    DebateConsensus, DebateBriefing, FactsPool, SharedContext,
    create_initial_state, AgentStatus,
)


class TestAgentEnvelope:
    """AgentEnvelope 校验测试"""

    def test_valid_envelope(self):
        envelope = AgentEnvelope(
            agent_name="Financial_Agent",
            status="success",
            fact_sheet={"roe": 0.25},
            brief_summary="测试摘要",
            confidence_score=85,
        )
        assert envelope.agent_name == "Financial_Agent"
        assert envelope.status == "success"
        assert envelope.fact_sheet["roe"] == 0.25

    def test_invalid_status(self):
        with pytest.raises(Exception):
            AgentEnvelope(
                agent_name="Test",
                status="invalid_status",
                brief_summary="test",
            )

    def test_confidence_out_of_range(self):
        with pytest.raises(Exception):
            AgentEnvelope(
                agent_name="Test",
                status="success",
                brief_summary="test",
                confidence_score=150,
            )

    def test_partial_status(self):
        envelope = AgentEnvelope(
            agent_name="Test",
            status="partial",
            brief_summary="部分完成",
        )
        assert envelope.status == "partial"


class TestToolRequest:
    """ToolRequest 校验测试"""

    def test_valid_request(self):
        req = ToolRequest(
            tool_name="get_competitor_data",
            tool_description="获取竞争对手数据",
            reason="需要对比数据",
            urgency="high",
            agent_id="financial_agent_001",
        )
        assert req.action == "request_tool"
        assert req.urgency == "high"

    def test_invalid_urgency(self):
        with pytest.raises(Exception):
            ToolRequest(
                tool_name="test",
                tool_description="test",
                reason="test",
                urgency="critical",
                agent_id="test",
            )


class TestDebateArgument:
    """DebateArgument 校验测试"""

    def test_bull_argument(self):
        arg = DebateArgument(
            role="bull",
            round=1,
            argument="ROE 连续三年超25%",
            confidence=85,
        )
        assert arg.role == "bull"
        assert arg.rebuttal_to is None

    def test_bear_argument_with_rebuttal(self):
        arg = DebateArgument(
            role="bear",
            round=2,
            argument="针对多方论点进行反驳",
            rebuttal_to="bull_round_1",
            confidence=60,
        )
        assert arg.rebuttal_to == "bull_round_1"

    def test_invalid_role(self):
        with pytest.raises(Exception):
            DebateArgument(
                role="neutral",
                round=1,
                argument="test",
                confidence=50,
            )


class TestInitialState:
    """初始状态创建测试"""

    def test_create_initial_state(self):
        state = create_initial_state("分析贵州茅台")
        assert state["user_query"] == "分析贵州茅台"
        assert state["resolved_entity"] is None
        assert state["shared_context"] is None
        assert state["agent_registry"] == []
        assert state["agent_outputs"] == {}
        assert state["debate_briefing"] is None
        assert state["debate_consensus"] is None
        assert state["final_report"] is None
        assert state["current_phase"] == "entity_resolution"
        assert state["errors"] == []
        assert state["start_time"] > 0


class TestFactsPool:
    """FactsPool 测试"""

    def test_facts_pool(self):
        pool = FactsPool(
            bullish_facts=[{"fact": "ROE=25%", "source": "FA"}],
            bearish_facts=[{"fact": "净现比=0.6", "source": "FA"}],
        )
        assert len(pool.bullish_facts) == 1
        assert len(pool.bearish_facts) == 1
        assert len(pool.neutral_facts) == 0


class TestDebateBriefing:
    """DebateBriefing 测试"""

    def test_briefing_creation(self):
        briefing = DebateBriefing(
            stock_code="600519",
            stock_name="贵州茅台",
        )
        assert briefing.stock_code == "600519"
        assert briefing.briefing_id.startswith("debate_")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
