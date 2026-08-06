"""
FinancialAnalysisState 定义
LangGraph 状态图的核心数据结构
"""

from typing import TypedDict, List, Dict, Optional, Annotated, Any
from operator import add
from pydantic import BaseModel, Field
from enum import Enum
import time
import uuid


# ============================================================
# Pydantic 校验模型
# ============================================================

class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"


class EntityResolution(BaseModel):
    """实体解析结果"""
    stock_code: str = Field(..., description="6位股票代码")
    stock_name: str = Field(..., description="公司全称")
    confidence: float = Field(..., ge=0, le=1, description="匹配置信度")
    candidates: Optional[List[Dict[str, Any]]] = Field(default=None, description="候选列表")


class AgentRegistryEntry(BaseModel):
    """子 Agent 注册表条目"""
    agent_id: str
    capability: str
    input_schema: List[str]
    tools: List[str] = Field(default_factory=list)
    status: str = AgentStatus.PENDING.value


class AgentEnvelope(BaseModel):
    """子 Agent 强制输出信封格式"""
    agent_name: str
    status: str = Field(..., pattern="^(success|partial|failed|timeout)$")
    fact_sheet: Dict[str, Any] = Field(default_factory=dict)
    brief_summary: str = Field(..., max_length=1000)
    full_report_ref: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0, le=100)


class ToolRequest(BaseModel):
    """子 Agent 工具申请协议"""
    action: str = Field(default="request_tool", pattern="^request_tool$")
    tool_name: str
    tool_description: str
    reason: str
    urgency: str = Field(default="medium", pattern="^(low|medium|high)$")
    agent_id: str


class DebateArgument(BaseModel):
    """辩论论点"""
    role: str = Field(..., pattern="^(bull|bear)$")
    round: int
    argument: str
    rebuttal_to: Optional[str] = None
    confidence: int = Field(..., ge=0, le=100)
    evidence_refs: List[str] = Field(default_factory=list)


class DebateConsensus(BaseModel):
    """辩论结论"""
    consensus: List[str] = Field(default_factory=list)
    disagreements: List[Dict[str, Any]] = Field(default_factory=list)
    risk_warning: str = ""
    final_bull_confidence: int = Field(50, ge=0, le=100)
    final_bear_confidence: int = Field(50, ge=0, le=100)
    debate_rounds: int = 0
    winner: str = "undecided"


class FactsPool(BaseModel):
    """事实池"""
    bullish_facts: List[Dict[str, Any]] = Field(default_factory=list)
    bearish_facts: List[Dict[str, Any]] = Field(default_factory=list)
    neutral_facts: List[Dict[str, Any]] = Field(default_factory=list)
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)


class DebateBriefing(BaseModel):
    """辩论简报"""
    briefing_id: str = Field(default_factory=lambda: f"debate_{uuid.uuid4().hex[:8]}")
    stock_code: str
    stock_name: str
    facts_pool: FactsPool = Field(default_factory=FactsPool)
    agent_summaries: List[Dict[str, Any]] = Field(default_factory=list)
    missing_data: List[str] = Field(default_factory=list)


class SharedContext(BaseModel):
    """共享上下文（基础元数据）"""
    stock_code: str
    stock_name: str
    financials: Dict[str, Any] = Field(default_factory=dict)
    valuation: Dict[str, Any] = Field(default_factory=dict)
    market_data: Dict[str, Any] = Field(default_factory=dict)
    data_freshness: str = ""
    cache_keys: Dict[str, str] = Field(default_factory=dict)


# ============================================================
# LangGraph State 定义
# ============================================================

class FinancialAnalysisState(TypedDict):
    """金融分析系统的完整状态定义"""

    # 系统级
    messages: Annotated[List[Dict], add]  # 对话历史（使用 add 归约器）
    user_query: str  # 原始用户问题

    # 阶段一：实体解析
    resolved_entity: Optional[Dict[str, Any]]

    # 阶段二：上下文初始化
    shared_context: Optional[Dict[str, Any]]

    # 阶段三：任务拆解与子 Agent 执行
    agent_registry: List[Dict[str, Any]]
    agent_outputs: Dict[str, Any]  # {agent_id: AgentEnvelope}
    tool_requests: List[Dict[str, Any]]

    # 阶段四：汇聚仲裁
    debate_briefing: Optional[Dict[str, Any]]

    # 阶段五：对抗辩论
    debate_history: List[Dict[str, Any]]
    debate_consensus: Optional[Dict[str, Any]]

    # 阶段六：报告生成
    final_report: Optional[str]
    report_id: Optional[str]

    # 状态控制
    current_phase: str
    errors: List[Dict[str, Any]]
    start_time: float


def create_initial_state(user_query: str) -> FinancialAnalysisState:
    """创建初始状态"""
    return FinancialAnalysisState(
        messages=[],
        user_query=user_query,
        resolved_entity=None,
        shared_context=None,
        agent_registry=[],
        agent_outputs={},
        tool_requests=[],
        debate_briefing=None,
        debate_history=[],
        debate_consensus=None,
        final_report=None,
        report_id=None,
        current_phase="entity_resolution",
        errors=[],
        start_time=time.time(),
    )
