"""
API 请求/响应 Pydantic 模型

所有端点的输入输出契约定义于此。
Pydantic v2 自动生成 OpenAPI 文档、请求校验、序列化。
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


# ============================================================
# 枚举
# ============================================================

class TaskStatus(str, Enum):
    """任务生命周期状态"""
    PENDING = "pending"        # 已创建，等待执行
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 已失败


# ============================================================
# 请求模型
# ============================================================

class AnalyzeRequest(BaseModel):
    """提交分析任务的请求体"""

    query: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="分析目标：股票代码（如 600519）或公司名称（如 贵州茅台）",
        examples=["贵州茅台", "600519", "分析科大讯飞"],
    )
    max_debate_rounds: int = Field(
        default=2,
        ge=1,
        le=10,
        description="多空辩论最大轮次，越大分析越深入但耗时越长",
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="自定义报告输出目录（默认使用配置中的 REPORT_OUTPUT_DIR）",
    )


class ResolveRequest(BaseModel):
    """实体解析请求体"""

    query: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="待解析的公司名称、股票代码或自然语言描述",
        examples=["茅台", "科大讯飞", "600519", "帮我分析那家做白酒的公司"],
    )
    use_llm: bool = Field(
        default=True,
        description=(
            "是否使用 LLM 辅助提取实体。"
            "开启后可识别错别字（如'矛台'→'茅台'）和自然语言描述，"
            "但会消耗少量 Token 并增加约 1 秒延迟。"
            "关闭时仅使用别名表和 AKShare 搜索。"
        ),
    )


# ============================================================
# 响应模型
# ============================================================

class AnalyzeResponse(BaseModel):
    """提交分析任务后的响应体（异步任务）"""

    task_id: str = Field(..., description="任务唯一标识，用于后续轮询结果")
    status: TaskStatus = Field(..., description="任务初始状态（通常为 running）")
    message: str = Field(..., description="人类可读的响应消息")


class AgentOutputSummary(BaseModel):
    """单个子 Agent 的分析输出摘要"""

    agent_name: str = Field(..., description="Agent 中文名称，如 财务分析、行业分析")
    status: str = Field(..., description="执行状态：success / partial / failed")
    confidence_score: Optional[float] = Field(
        None, ge=0, le=100, description="Agent 自评置信度（0-100）"
    )
    brief_summary: str = Field(default="", description="核心结论（≤200 字）")
    fact_sheet: Dict[str, Any] = Field(
        default_factory=dict,
        description="结构化指标数据，键为中文指标名，值为数值或列表",
    )


class DebateSummary(BaseModel):
    """辩论结论摘要"""

    final_bull_confidence: int = Field(50, ge=0, le=100, description="多方最终置信度")
    final_bear_confidence: int = Field(50, ge=0, le=100, description="空方最终置信度")
    winner: str = Field("undecided", description="胜方：bull / bear / consensus / undecided")
    debate_rounds: int = Field(0, ge=0, description="实际辩论轮次")
    risk_warning: str = Field("", description="核心风险提示")
    consensus: List[str] = Field(default_factory=list, description="双方共识点列表")


class AnalyzeResult(BaseModel):
    """完整的分析结果（任务完成后返回）"""

    task_id: str = Field(..., description="任务唯一标识")
    status: TaskStatus = Field(..., description="任务最终状态")
    stock_code: str = Field("", description="股票代码")
    stock_name: str = Field("", description="公司名称")
    confidence: float = Field(0.0, ge=0, le=1, description="实体解析置信度")
    agent_outputs: List[AgentOutputSummary] = Field(
        default_factory=list, description="各 Agent 分析输出"
    )
    debate_summary: Optional[DebateSummary] = Field(None, description="辩论结论")
    final_report: Optional[str] = Field(None, description="Markdown 格式的完整报告")
    report_path: Optional[str] = Field(None, description="报告文件路径")
    elapsed_seconds: float = Field(0.0, ge=0, description="分析耗时（秒）")
    error: Optional[str] = Field(None, description="失败原因（仅 status=failed 时有值）")


class ResolveCandidate(BaseModel):
    """实体解析的候选公司"""

    stock_code: str = Field(..., description="股票代码")
    stock_name: str = Field(..., description="公司名称")
    confidence: float = Field(..., ge=0, le=1, description="匹配置信度")
    source: str = Field("", description="匹配来源：code_match / alias_exact / akshare_search 等")


class ResolveResponse(BaseModel):
    """实体解析的响应体"""

    stock_code: str = Field("", description="匹配到的股票代码")
    stock_name: str = Field("", description="匹配到的公司名称")
    confidence: float = Field(0.0, ge=0, le=1, description="匹配置信度")
    action: str = Field(
        "not_found",
        description="下一步动作：auto_confirm（直接确认）/ need_confirm（需用户选择）/ not_found",
    )
    message: str = Field("", description="人类可读的解析结果消息")
    candidates: List[ResolveCandidate] = Field(
        default_factory=list, description="候选公司列表（need_confirm 时供用户选择）"
    )


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = Field("ok", description="服务状态")
    version: str = Field("1.0.0", description="API 版本号")
    llm_configured: bool = Field(False, description="LLM 是否已配置 API Key")
    cache_stats: Dict[str, Any] = Field(default_factory=dict, description="缓存统计信息")


class ErrorResponse(BaseModel):
    """统一错误响应体"""

    error: str = Field(..., description="错误类型")
    detail: Optional[str] = Field(None, description="错误详情")


class TaskListItem(BaseModel):
    """任务列表中的单条记录"""

    task_id: str = Field(..., description="任务唯一标识")
    query: str = Field(..., description="分析目标")
    status: TaskStatus = Field(..., description="任务状态")
    elapsed: float = Field(0.0, description="已耗时（秒）")


class TaskListResponse(BaseModel):
    """任务列表响应"""

    tasks: List[TaskListItem] = Field(default_factory=list, description="任务列表")


class ProgressEvent(BaseModel):
    """SSE 流式进度事件"""

    status: str = Field(..., description="任务状态")
    phase: str = Field("", description="当前执行阶段")
    progress: int = Field(0, ge=0, le=100, description="进度百分比")
    message: str = Field("", description="进度消息")
    elapsed: float = Field(0.0, description="已耗时（秒）")
