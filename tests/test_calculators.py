"""
财务指标计算器测试
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.financial_calculators import (
    calculate_dupont, calculate_cashflow_quality, calculate_net_cash_ratio,
    calculate_debt_ratio, calculate_current_ratio, calculate_quick_ratio,
    calculate_inventory_turnover, calculate_receivable_turnover,
    calculate_asset_turnover, calculate_roe, calculate_roa,
    calculate_gross_margin, calculate_net_margin,
    calculate_dcf, calculate_pe_valuation, calculate_pb_valuation,
)


class TestDupont:
    """杜邦分析测试"""

    def test_normal_case(self):
        result = calculate_dupont(
            net_income=100, revenue=1000, total_assets=2000, shareholders_equity=800
        )
        assert result["status"] == "success"
        assert abs(result["roe"] - 0.125) < 0.001  # (100/1000) * (1000/2000) * (2000/800)
        assert abs(result["net_margin"] - 0.1) < 0.001
        assert abs(result["asset_turnover"] - 0.5) < 0.001
        assert abs(result["equity_multiplier"] - 2.5) < 0.001

    def test_zero_equity(self):
        result = calculate_dupont(
            net_income=100, revenue=1000, total_assets=2000, shareholders_equity=0
        )
        assert result["status"] == "error"
        assert result["roe"] is None

    def test_high_roe(self):
        result = calculate_dupont(
            net_income=300, revenue=1000, total_assets=1500, shareholders_equity=600
        )
        assert result["status"] == "success"
        assert result["roe"] > 0.2


class TestCashflowQuality:
    """现金流质量测试"""

    def test_excellent_quality(self):
        result = calculate_cashflow_quality(
            operating_cashflow=120, net_income=100
        )
        assert result["status"] == "success"
        assert result["net_cash_ratio"] == 1.2
        assert result["quality"] == "优秀"

    def test_poor_quality(self):
        result = calculate_cashflow_quality(
            operating_cashflow=30, net_income=100
        )
        assert result["status"] == "success"
        assert result["net_cash_ratio"] == 0.3
        assert result["quality"] == "较差"

    def test_zero_income(self):
        result = calculate_cashflow_quality(
            operating_cashflow=50, net_income=0
        )
        assert result["status"] == "warning"
        assert result["net_cash_ratio"] is None


class TestDebtRatio:
    """资产负债率测试"""

    def test_normal_case(self):
        result = calculate_debt_ratio(
            total_liabilities=400, total_assets=1000
        )
        assert result["status"] == "success"
        assert result["ratio"] == 0.4
        assert result["level"] == "中"

    def test_high_debt(self):
        result = calculate_debt_ratio(
            total_liabilities=800, total_assets=1000
        )
        assert result["ratio"] == 0.8
        assert result["level"] == "高"

    def test_zero_assets(self):
        result = calculate_debt_ratio(
            total_liabilities=100, total_assets=0
        )
        assert result["status"] == "error"


class TestCurrentRatio:
    """流动比率测试"""

    def test_good_ratio(self):
        result = calculate_current_ratio(
            current_assets=300, current_liabilities=100
        )
        assert result["status"] == "success"
        assert result["ratio"] == 3.0
        assert result["level"] == "优秀"

    def test_poor_ratio(self):
        result = calculate_current_ratio(
            current_assets=80, current_liabilities=100
        )
        assert result["ratio"] == 0.8
        assert result["level"] == "较差"


class TestQuickRatio:
    """速动比率测试"""

    def test_normal_case(self):
        result = calculate_quick_ratio(
            current_assets=300, inventory=100, current_liabilities=100
        )
        assert result["status"] == "success"
        assert result["ratio"] == 2.0


class TestTurnover:
    """周转率测试"""

    def test_inventory_turnover(self):
        result = calculate_inventory_turnover(cogs=500, avg_inventory=100)
        assert result["status"] == "success"
        assert result["turnover"] == 5.0
        assert result["days"] == 73.0

    def test_receivable_turnover(self):
        result = calculate_receivable_turnover(revenue=1000, avg_receivables=200)
        assert result["status"] == "success"
        assert result["turnover"] == 5.0

    def test_asset_turnover(self):
        result = calculate_asset_turnover(revenue=1000, total_assets=2000)
        assert result == 0.5


class TestDCF:
    """DCF 估值测试"""

    def test_normal_dcf(self):
        result = calculate_dcf(
            fcf=100, growth_rate=0.10, discount_rate=0.12,
            terminal_growth=0.03, years=5
        )
        assert result["status"] == "success"
        assert result["enterprise_value"] > 0
        assert result["pv_terminal"] > 0
        assert len(result["projected_fcfs"]) == 5

    def test_invalid_rates(self):
        result = calculate_dcf(
            fcf=100, growth_rate=0.10, discount_rate=0.02,
            terminal_growth=0.03, years=5
        )
        assert result["status"] == "error"


class TestRelativeValuation:
    """相对估值测试"""

    def test_pe_valuation(self):
        result = calculate_pe_valuation(eps=5.0, industry_pe=25.0)
        assert result["status"] == "success"
        assert result["fair_value"] == 125.0

    def test_pe_negative_eps(self):
        result = calculate_pe_valuation(eps=-1.0, industry_pe=25.0)
        assert result["status"] == "warning"

    def test_pb_valuation(self):
        result = calculate_pb_valuation(bvps=20.0, industry_pb=3.0)
        assert result["status"] == "success"
        assert result["fair_value"] == 60.0


class TestBasicMetrics:
    """基础指标测试"""

    def test_roe(self):
        assert calculate_roe(100, 500) == 0.2
        assert calculate_roe(100, 0) == 0.0

    def test_roa(self):
        assert calculate_roa(100, 1000) == 0.1
        assert calculate_roa(100, 0) == 0.0

    def test_gross_margin(self):
        assert calculate_gross_margin(1000, 600) == 0.4
        assert calculate_gross_margin(0, 600) == 0.0

    def test_net_margin(self):
        assert calculate_net_margin(100, 1000) == 0.1
        assert calculate_net_margin(100, 0) == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
