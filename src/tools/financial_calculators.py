"""
财务指标计算器
提供杜邦分析、现金流质量等核心财务指标计算
所有数值必须来源于数据源或基于明确公式计算，不能凭空生成
"""

from typing import Any, Dict, Optional, List
from src.utils.logger import get_logger

logger = get_logger(__name__)


def calculate_dupont(net_income: float, revenue: float, total_assets: float,
                     shareholders_equity: float) -> Dict[str, Any]:
    """
    杜邦分析（ROE 三因素分解）
    ROE = 净利率 × 总资产周转率 × 权益乘数
    """
    if shareholders_equity == 0:
        return {"status": "error", "message": "股东权益为零，无法计算", "roe": None}

    net_margin = net_income / revenue if revenue != 0 else 0
    asset_turnover = revenue / total_assets if total_assets != 0 else 0
    equity_multiplier = total_assets / shareholders_equity if shareholders_equity != 0 else 0
    roe = net_margin * asset_turnover * equity_multiplier

    return {
        "status": "success",
        "roe": round(roe, 4),
        "net_margin": round(net_margin, 4),
        "asset_turnover": round(asset_turnover, 4),
        "equity_multiplier": round(equity_multiplier, 4),
        "analysis": {
            "profitability": "高" if net_margin > 0.15 else "中" if net_margin > 0.05 else "低",
            "efficiency": "高" if asset_turnover > 0.8 else "中" if asset_turnover > 0.4 else "低",
            "leverage": "高" if equity_multiplier > 2.5 else "中" if equity_multiplier > 1.5 else "低",
        },
    }


def calculate_cashflow_quality(operating_cashflow: float, net_income: float) -> Dict[str, Any]:
    """
    现金流质量分析
    净现比 = 经营现金流 / 净利润
    """
    if net_income == 0:
        return {
            "status": "warning",
            "net_cash_ratio": None,
            "quality": "无法评估",
            "message": "净利润为零",
        }

    ratio = operating_cashflow / net_income

    if ratio >= 1.0:
        quality = "优秀"
        signal = "现金流完全覆盖利润"
    elif ratio >= 0.7:
        quality = "良好"
        signal = "现金流基本覆盖利润"
    elif ratio >= 0.5:
        quality = "一般"
        signal = "现金流部分覆盖利润，需关注应收账款"
    else:
        quality = "较差"
        signal = "现金流严重不足，利润质量存疑"

    return {
        "status": "success",
        "net_cash_ratio": round(ratio, 4),
        "quality": quality,
        "signal": signal,
    }


def calculate_net_cash_ratio(operating_cashflow: float, net_income: float) -> float:
    """净现比（简化版）"""
    if net_income == 0:
        return 0.0
    return round(operating_cashflow / net_income, 4)


def calculate_debt_ratio(total_liabilities: float, total_assets: float) -> Dict[str, Any]:
    """
    资产负债率
    """
    if total_assets == 0:
        return {"status": "error", "message": "总资产为零", "ratio": None}

    ratio = total_liabilities / total_assets

    if ratio < 0.4:
        level = "低"
        signal = "财务风险较低"
    elif ratio < 0.6:
        level = "中"
        signal = "财务杠杆适中"
    elif ratio < 0.7:
        level = "偏高"
        signal = "财务杠杆较高，需关注偿债能力"
    else:
        level = "高"
        signal = "财务风险较高"

    return {
        "status": "success",
        "ratio": round(ratio, 4),
        "level": level,
        "signal": signal,
    }


def calculate_current_ratio(current_assets: float, current_liabilities: float) -> Dict[str, Any]:
    """流动比率"""
    if current_liabilities == 0:
        return {"status": "warning", "ratio": None, "message": "流动负债为零"}

    ratio = current_assets / current_liabilities

    if ratio >= 2.0:
        level = "优秀"
    elif ratio >= 1.5:
        level = "良好"
    elif ratio >= 1.0:
        level = "一般"
    else:
        level = "较差"

    return {
        "status": "success",
        "ratio": round(ratio, 4),
        "level": level,
    }


def calculate_quick_ratio(current_assets: float, inventory: float,
                          current_liabilities: float) -> Dict[str, Any]:
    """速动比率"""
    if current_liabilities == 0:
        return {"status": "warning", "ratio": None, "message": "流动负债为零"}

    ratio = (current_assets - inventory) / current_liabilities

    if ratio >= 1.5:
        level = "优秀"
    elif ratio >= 1.0:
        level = "良好"
    elif ratio >= 0.7:
        level = "一般"
    else:
        level = "较差"

    return {
        "status": "success",
        "ratio": round(ratio, 4),
        "level": level,
    }


def calculate_inventory_turnover(cogs: float, avg_inventory: float) -> Dict[str, Any]:
    """存货周转率"""
    if avg_inventory == 0:
        return {"status": "warning", "turnover": None, "message": "平均存货为零"}

    turnover = cogs / avg_inventory

    return {
        "status": "success",
        "turnover": round(turnover, 4),
        "days": round(365 / turnover, 1) if turnover > 0 else None,
    }


def calculate_receivable_turnover(revenue: float, avg_receivables: float) -> Dict[str, Any]:
    """应收账款周转率"""
    if avg_receivables == 0:
        return {"status": "warning", "turnover": None, "message": "平均应收账款为零"}

    turnover = revenue / avg_receivables

    return {
        "status": "success",
        "turnover": round(turnover, 4),
        "days": round(365 / turnover, 1) if turnover > 0 else None,
    }


def calculate_asset_turnover(revenue: float, total_assets: float) -> float:
    """总资产周转率"""
    if total_assets == 0:
        return 0.0
    return round(revenue / total_assets, 4)


def calculate_roe(net_income: float, shareholders_equity: float) -> float:
    """ROE（净资产收益率）"""
    if shareholders_equity == 0:
        return 0.0
    return round(net_income / shareholders_equity, 4)


def calculate_roa(net_income: float, total_assets: float) -> float:
    """ROA（总资产收益率）"""
    if total_assets == 0:
        return 0.0
    return round(net_income / total_assets, 4)


def calculate_gross_margin(revenue: float, cogs: float) -> float:
    """毛利率"""
    if revenue == 0:
        return 0.0
    return round((revenue - cogs) / revenue, 4)


def calculate_net_margin(net_income: float, revenue: float) -> float:
    """净利率"""
    if revenue == 0:
        return 0.0
    return round(net_income / revenue, 4)


def calculate_dcf(fcf: float, growth_rate: float, discount_rate: float,
                  terminal_growth: float, years: int = 5) -> Dict[str, Any]:
    """
    DCF 现金流折现估值
    fcf: 自由现金流（最近一年）
    growth_rate: 未来增长率
    discount_rate: 折现率（WACC）
    terminal_growth: 永续增长率
    years: 预测年数
    """
    if discount_rate <= terminal_growth:
        return {"status": "error", "message": "折现率必须大于永续增长率"}

    # 预测期现金流
    projected_fcfs = []
    pv_fcfs = []
    for i in range(1, years + 1):
        projected_fcf = fcf * (1 + growth_rate) ** i
        pv = projected_fcf / (1 + discount_rate) ** i
        projected_fcfs.append(round(projected_fcf, 2))
        pv_fcfs.append(round(pv, 2))

    # 终值
    terminal_value = projected_fcfs[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / (1 + discount_rate) ** years

    # 企业价值
    enterprise_value = sum(pv_fcfs) + pv_terminal

    return {
        "status": "success",
        "enterprise_value": round(enterprise_value, 2),
        "pv_projected": round(sum(pv_fcfs), 2),
        "pv_terminal": round(pv_terminal, 2),
        "terminal_value": round(terminal_value, 2),
        "projected_fcfs": projected_fcfs,
        "assumptions": {
            "fcf_base": fcf,
            "growth_rate": growth_rate,
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
            "years": years,
        },
    }


def calculate_pe_valuation(eps: float, industry_pe: float) -> Dict[str, Any]:
    """PE 相对估值"""
    if eps <= 0:
        return {"status": "warning", "message": "EPS 为负，PE 估值不适用"}

    fair_value = eps * industry_pe

    return {
        "status": "success",
        "fair_value": round(fair_value, 2),
        "eps": eps,
        "industry_pe": industry_pe,
    }


def calculate_pb_valuation(bvps: float, industry_pb: float) -> Dict[str, Any]:
    """PB 相对估值"""
    if bvps <= 0:
        return {"status": "warning", "message": "每股净资产为负，PB 估值不适用"}

    fair_value = bvps * industry_pb

    return {
        "status": "success",
        "fair_value": round(fair_value, 2),
        "bvps": bvps,
        "industry_pb": industry_pb,
    }
