"""
上下文初始化 Agent
拉取基础元数据，存入缓存供所有子 Agent 共享
"""

import time
from typing import Any, Dict, List
from src.tools.baostock_wrapper import (
    get_stock_basic, get_multi_year_profit, get_multi_year_balance,
    get_stock_kline,
)
from src.tools.akshare_wrapper import get_stock_info, get_stock_valuation
from src.cache.sqlite_cache import get_cache
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _fetch_financials(stock_code: str) -> Dict[str, Any]:
    """获取多年财务数据"""
    logger.info(f"获取 {stock_code} 财务数据...")

    # 盈利数据
    profit_data = get_multi_year_profit(stock_code)

    # 偿债数据
    balance_data = get_multi_year_balance(stock_code)

    # K线数据（近1年）
    kline_data = get_stock_kline(stock_code)

    # 提取最新数据期间（statDate）
    data_period = _extract_data_period(profit_data)

    return {
        "profit": profit_data,
        "balance": balance_data,
        "kline": kline_data,
        "data_period": data_period,  # 如 "2025Q4"
    }


def _extract_data_period(profit_data: Dict[str, Any]) -> str:
    """从盈利数据中提取最新数据期间"""
    try:
        data_list = profit_data.get("data", [])
        if not data_list:
            return ""

        # 找最新的 statDate
        latest = ""
        for record in data_list:
            stat_date = record.get("statDate", "")
            if stat_date and stat_date > latest:
                latest = stat_date

        if latest:
            # 转换为 "2025Q4" 格式
            year = latest[:4]
            month = int(latest[5:7]) if len(latest) > 7 else 12
            quarter = (month - 1) // 3 + 1
            return f"{year}Q{quarter}"
        return ""
    except Exception:
        return ""


def _fetch_valuation(stock_code: str) -> Dict[str, Any]:
    """获取估值数据（AKShare + MCP 双源）"""
    logger.info(f"获取 {stock_code} 估值数据...")

    # 优先 AKShare
    val_data = get_stock_valuation(stock_code)
    if val_data.get("status") == "success":
        return val_data

    # 降级到 MCP
    logger.info(f"AKShare 估值失败，降级到 MCP...")
    try:
        from src.tools.mcp_stock_wrapper import get_stock_brief
        mcp_data = get_stock_brief(stock_code)
        if mcp_data.get("status") == "success":
            d = mcp_data.get("data", {})
            return {
                "status": "success",
                "data": {
                    "current_price": d.get("current_price"),
                    "pe_ttm": d.get("pe_ttm"),
                    "pb": d.get("pb"),
                    "change_pct": d.get("change_pct"),
                },
                "source": "mcp_cn_stock",
            }
    except Exception as e:
        logger.warning(f"MCP 估值降级失败: {e}")

    return val_data


def _fetch_basic_info(stock_code: str) -> Dict[str, Any]:
    """获取基本信息（AKShare + MCP 双源）"""
    logger.info(f"获取 {stock_code} 基本信息...")

    # 优先 AKShare
    info = get_stock_info(stock_code)
    if info.get("status") == "success":
        return info

    # 降级到 MCP
    logger.info(f"AKShare 基本信息失败，降级到 MCP...")
    try:
        from src.tools.mcp_stock_wrapper import get_stock_brief
        mcp_data = get_stock_brief(stock_code)
        if mcp_data.get("status") == "success":
            d = mcp_data.get("data", {})
            return {
                "status": "success",
                "data": {
                    "股票简称": d.get("stock_name", ""),
                    "行业": d.get("industry", ""),
                    "市盈率(动态)": d.get("pe_ttm"),
                    "市净率": d.get("pb"),
                },
                "stock_name": d.get("stock_name", ""),
                "industry": d.get("industry", ""),
                "source": "mcp_cn_stock",
            }
    except Exception as e:
        logger.warning(f"MCP 基本信息降级失败: {e}")

    return info


def _fetch_mcp_data(stock_code: str) -> Dict[str, Any]:
    """获取 MCP 数据（技术指标 + 资金流向 + 行情）"""
    logger.info(f"获取 {stock_code} MCP 数据...")
    try:
        from src.tools.mcp_stock_wrapper import get_stock_brief
        mcp_data = get_stock_brief(stock_code)
        if mcp_data.get("status") == "success":
            return mcp_data
    except Exception as e:
        logger.warning(f"MCP 数据获取失败: {e}")
    return {"status": "error", "data": {}}


def init_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    上下文初始化主函数
    拉取基础元数据，写入 State 的 shared_context

    数据源优先级：
    - 财务数据：BaoStock（稳定）
    - 估值/基本信息：AKShare → MCP（降级）
    - 技术指标/资金流向：MCP（独占）
    """
    resolved = state.get("resolved_entity", {})
    stock_code = resolved.get("stock_code", "")
    stock_name = resolved.get("stock_name", "")

    if not stock_code:
        logger.error("未解析到股票代码，无法初始化上下文")
        return {
            "shared_context": None,
            "errors": [{"phase": "context_init", "error": "未解析到股票代码"}],
            "messages": [{"role": "system", "content": "上下文初始化失败：未解析到股票代码"}],
        }

    logger.info(f"开始初始化上下文: {stock_name}({stock_code})")

    try:
        # 获取各类数据
        financials = _fetch_financials(stock_code)
        valuation = _fetch_valuation(stock_code)
        basic_info = _fetch_basic_info(stock_code)
        mcp_data = _fetch_mcp_data(stock_code)

        # 构建共享上下文
        data_period = financials.get("data_period", "")

        shared_context = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "financials": financials,
            "valuation": valuation,
            "basic_info": basic_info,
            "mcp_data": mcp_data,
            "data_freshness": time.strftime("%Y-%m-%d"),
            "data_period": data_period,  # 如 "2025Q4"，标识财务数据所属期间
            "cache_keys": {
                "profit": f"profit_{stock_code}",
                "balance": f"balance_{stock_code}",
                "kline": f"kline_{stock_code}",
                "valuation": f"akshare_valuation_{stock_code}",
                "mcp_brief": f"mcp_brief_{stock_code}",
            },
        }

        logger.info(f"上下文初始化完成: {stock_name}({stock_code})")

        return {
            "shared_context": shared_context,
            "current_phase": "context_initialized",
            "messages": [{"role": "system", "content": f"上下文初始化完成: {stock_name}({stock_code})"}],
        }

    except Exception as e:
        logger.error(f"上下文初始化异常: {e}")
        return {
            "shared_context": None,
            "errors": [{"phase": "context_init", "error": str(e)}],
            "messages": [{"role": "system", "content": f"上下文初始化异常: {e}"}],
        }


class ContextAgent:
    """上下文初始化节点（LangGraph 节点）"""

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return init_context(state)
