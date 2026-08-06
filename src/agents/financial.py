"""
财务分析子 Agent
杜邦分解、盈利质量、偿债能力、现金流分析
"""

import json
from typing import Any, Dict
from langchain_core.language_models import BaseChatModel
from src.agents.base import FinancialAgentBase
from src.prompts.agent_prompts import FINANCIAL_SYSTEM
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FinancialAgent(FinancialAgentBase):
    """财务分析子 Agent"""

    def __init__(self, llm: BaseChatModel):
        super().__init__(llm, agent_name="财务分析")

    def _build_system_prompt(self, state: Dict[str, Any]) -> str:
        return FINANCIAL_SYSTEM

    def _build_user_prompt(self, state: Dict[str, Any]) -> str:
        shared_context = state.get("shared_context", {})
        stock_code = shared_context.get("stock_code", "")
        stock_name = shared_context.get("stock_name", "")

        # 提取财务数据
        financials = shared_context.get("financials", {})
        profit_data = financials.get("profit", {})
        balance_data = financials.get("balance", {})
        kline_data = financials.get("kline", {})
        valuation = shared_context.get("valuation", {})

        # 构建数据摘要
        data_summary = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "profit_data": profit_data.get("data", [])[-10:] if profit_data.get("status") == "success" else "数据获取失败",
            "balance_data": balance_data.get("data", [])[-10:] if balance_data.get("status") == "success" else "数据获取失败",
            "valuation": valuation.get("data", {}) if valuation.get("status") == "success" else {},
        }

        data_str = json.dumps(data_summary, ensure_ascii=False, indent=2, default=str)

        return f"""请对 {stock_name}（{stock_code}）进行财务健康度分析。

**可用财务数据**：
{data_str}

请输出分析结果（JSON 信封格式）。"""


class IndustryAgent(FinancialAgentBase):
    """行业分析子 Agent"""

    def __init__(self, llm: BaseChatModel):
        super().__init__(llm, agent_name="行业分析")

    def _build_system_prompt(self, state: Dict[str, Any]) -> str:
        from src.prompts.agent_prompts import INDUSTRY_SYSTEM
        return INDUSTRY_SYSTEM

    def _build_user_prompt(self, state: Dict[str, Any]) -> str:
        shared_context = state.get("shared_context", {})
        stock_code = shared_context.get("stock_code", "")
        stock_name = shared_context.get("stock_name", "")
        basic_info = shared_context.get("basic_info", {})
        valuation = shared_context.get("valuation", {})

        data_summary = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "basic_info": basic_info.get("data", {}) if basic_info.get("status") == "success" else {},
            "valuation": valuation.get("data", {}) if valuation.get("status") == "success" else {},
        }

        data_str = json.dumps(data_summary, ensure_ascii=False, indent=2, default=str)

        return f"""请对 {stock_name}（{stock_code}）进行行业竞争格局分析。

**可用数据**：
{data_str}

请输出分析结果（JSON 信封格式）。"""


class SentimentAgent(FinancialAgentBase):
    """舆情分析子 Agent"""

    def __init__(self, llm: BaseChatModel):
        super().__init__(llm, agent_name="舆情分析")

    def _build_system_prompt(self, state: Dict[str, Any]) -> str:
        from src.prompts.agent_prompts import SENTIMENT_SYSTEM
        return SENTIMENT_SYSTEM

    def _build_user_prompt(self, state: Dict[str, Any]) -> str:
        shared_context = state.get("shared_context", {})
        stock_code = shared_context.get("stock_code", "")
        stock_name = shared_context.get("stock_name", "")

        # 获取新闻数据（使用 news_fetcher）
        try:
            from src.tools.news_fetcher import get_stock_sentiment
            sentiment_result = get_stock_sentiment(stock_code, stock_name)
            sentiment_data = sentiment_result.get("data", {}) if sentiment_result.get("status") == "success" else {}
        except Exception:
            sentiment_data = {}

        # 获取 MCP 数据（资金流向）
        mcp_data = shared_context.get("mcp_data", {})
        mcp_info = mcp_data.get("data", {}) if mcp_data.get("status") == "success" else {}

        # 获取K线数据
        financials = shared_context.get("financials", {})
        kline = financials.get("kline", {})
        kline_summary = kline.get("data", [])[-30:] if kline.get("status") == "success" else []

        data_summary = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "sentiment": sentiment_data,
            "fund_flow": mcp_info.get("fund_flow", {}),
            "recent_kline": kline_summary,
        }

        data_str = json.dumps(data_summary, ensure_ascii=False, indent=2, default=str)

        return f"""请对 {stock_name}（{stock_code}）进行舆情与市场情绪分析。

**可用数据**：
{data_str}

请输出分析结果（JSON 信封格式）。"""


class ValuationAgent(FinancialAgentBase):
    """估值分析子 Agent"""

    def __init__(self, llm: BaseChatModel):
        super().__init__(llm, agent_name="估值分析")

    def _build_system_prompt(self, state: Dict[str, Any]) -> str:
        from src.prompts.agent_prompts import VALUATION_SYSTEM
        return VALUATION_SYSTEM

    def _build_user_prompt(self, state: Dict[str, Any]) -> str:
        shared_context = state.get("shared_context", {})
        stock_code = shared_context.get("stock_code", "")
        stock_name = shared_context.get("stock_name", "")
        financials = shared_context.get("financials", {})
        valuation = shared_context.get("valuation", {})

        # 提取关键财务数据用于估值
        profit_data = financials.get("profit", {})
        balance_data = financials.get("balance", {})

        data_summary = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "valuation": valuation.get("data", {}) if valuation.get("status") == "success" else {},
            "profit_data": profit_data.get("data", [])[-5:] if profit_data.get("status") == "success" else [],
            "balance_data": balance_data.get("data", [])[-5:] if balance_data.get("status") == "success" else [],
        }

        data_str = json.dumps(data_summary, ensure_ascii=False, indent=2, default=str)

        return f"""请对 {stock_name}（{stock_code}）进行估值分析。

**可用数据**：
{data_str}

请输出分析结果（JSON 信封格式），包含 DCF 估值和 PE/PB 相对估值。
注意：估值结论必须标注"基于特定假设，实际可能存在偏差"。"""
