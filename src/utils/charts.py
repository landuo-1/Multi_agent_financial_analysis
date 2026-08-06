"""
图表生成模块
生成财务分析相关的专业图表，返回 base64 编码的 PNG 图片

图表类型：
- 杜邦分析瀑布图
- 财务健康度雷达图
- 多空置信度对比图
- K线走势图（含均线）
- 营收/净利润趋势图
- 利润率对比图
- 资金流向饼图
"""

import io
import base64
from typing import Any, Dict, List, Optional


def _setup_matplotlib():
    """配置 matplotlib 中文字体"""
    import matplotlib
    import matplotlib.pyplot as plt
    matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    return plt


def _render_chart(fig) -> str:
    """将 matplotlib figure 转为 base64 PNG"""
    plt = _setup_matplotlib()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{b64}"


def _save_chart_to_file(fig, filepath: str):
    """保存图表到文件"""
    plt = _setup_matplotlib()
    fig.savefig(filepath, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ============================================================
# 1. 杜邦分析瀑布图
# ============================================================

def generate_dupont_chart(fact_sheet: Dict[str, Any]) -> Optional[str]:
    """生成杜邦分析瀑布图"""
    try:
        plt = _setup_matplotlib()

        roe = fact_sheet.get("roe", 0) or 0
        net_margin = fact_sheet.get("net_margin", 0) or 0
        asset_turnover = fact_sheet.get("asset_turnover", 0) or 0
        equity_multiplier = fact_sheet.get("equity_multiplier", 0) or 0

        if roe == 0:
            return None

        labels = ["净利率", "资产周转率", "权益乘数", "ROE"]
        values = [net_margin * 100, asset_turnover * 100, equity_multiplier, roe * 100]
        colors = ["#4CAF50", "#2196F3", "#FF9800", "#F44336"]

        fig, ax = plt.subplots(figsize=(8, 4))
        bars = ax.bar(labels, values, color=colors, width=0.6)

        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=12, fontweight="bold")

        ax.set_title("杜邦分析分解", fontsize=14, fontweight="bold")
        ax.set_ylabel("数值 (%)")
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()

        return _render_chart(fig)
    except Exception:
        return None


# ============================================================
# 2. 财务健康度雷达图
# ============================================================

def generate_financial_metrics_chart(fact_sheet: Dict[str, Any]) -> Optional[str]:
    """生成核心财务指标雷达图"""
    try:
        plt = _setup_matplotlib()
        import numpy as np

        metrics = {
            "ROE": min((fact_sheet.get("roe", 0) or 0) * 400, 100),
            "毛利率": min((fact_sheet.get("gross_margin", 0) or 0) * 200, 100),
            "净利率": min((fact_sheet.get("net_margin", 0) or 0) * 400, 100),
            "现金流": min((fact_sheet.get("net_cash_ratio", 0) or 0) * 80, 100),
            "偿债能力": max(0, 100 - (fact_sheet.get("debt_ratio", 0.5) or 0.5) * 150),
            "流动性": min((fact_sheet.get("current_ratio", 1) or 1) * 40, 100),
        }

        labels = list(metrics.keys())
        values = list(metrics.values())
        values += values[:1]

        angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
        ax.fill(angles, values, color="#2196F3", alpha=0.25)
        ax.plot(angles, values, color="#2196F3", linewidth=2)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=11)
        ax.set_title("财务健康度雷达图", fontsize=14, fontweight="bold", pad=20)
        ax.set_ylim(0, 100)

        return _render_chart(fig)
    except Exception:
        return None


# ============================================================
# 3. 多空置信度对比图
# ============================================================

def generate_confidence_chart(bull_conf: int, bear_conf: int) -> Optional[str]:
    """生成多空置信度对比图"""
    try:
        plt = _setup_matplotlib()

        fig, ax = plt.subplots(figsize=(6, 3))

        colors = ["#4CAF50" if bull_conf > bear_conf else "#888",
                  "#F44336" if bear_conf > bull_conf else "#888"]

        ax.barh(["多方 (Bull)", "空方 (Bear)"], [bull_conf, bear_conf],
                color=colors, height=0.3)

        for i, v in enumerate([bull_conf, bear_conf]):
            ax.text(v + 1, [0.6, 0.4][i], f"{v}%", va="center", fontsize=13, fontweight="bold")

        ax.set_xlim(0, 110)
        ax.set_title("多空置信度对比", fontsize=14, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)
        fig.tight_layout()

        return _render_chart(fig)
    except Exception:
        return None


# ============================================================
# 4. K线走势图（含均线）
# ============================================================

def generate_kline_chart(kline_data: List[Dict], stock_name: str = "") -> Optional[str]:
    """
    生成K线走势图（简化版：收盘价 + 成交量）
    kline_data: [{"date": "2026-07-01", "close": 1300, "volume": 5000000}, ...]
    """
    try:
        plt = _setup_matplotlib()
        import numpy as np

        if not kline_data or len(kline_data) < 5:
            return None

        dates = [d.get("date", "") for d in kline_data[-60:]]  # 最近60天
        closes = [float(d.get("close", 0)) for d in kline_data[-60:]]
        volumes = [float(d.get("volume", 0)) for d in kline_data[-60:]]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={"height_ratios": [3, 1]})

        # 收盘价 + 均线
        ax1.plot(range(len(closes)), closes, color="#2196F3", linewidth=1.5, label="收盘价")

        # 5日均线
        if len(closes) >= 5:
            ma5 = np.convolve(closes, np.ones(5) / 5, mode="valid")
            ax1.plot(range(4, len(closes)), ma5, color="#FF9800", linewidth=1, label="MA5", alpha=0.8)

        # 20日均线
        if len(closes) >= 20:
            ma20 = np.convolve(closes, np.ones(20) / 20, mode="valid")
            ax1.plot(range(19, len(closes)), ma20, color="#F44336", linewidth=1, label="MA20", alpha=0.8)

        ax1.set_title(f"{stock_name} 股价走势", fontsize=13, fontweight="bold")
        ax1.legend(fontsize=9)
        ax1.grid(alpha=0.3)

        # X轴标签（每10天一个）
        tick_pos = list(range(0, len(dates), 10))
        ax1.set_xticks(tick_pos)
        ax1.set_xticklabels([dates[i][5:] for i in tick_pos], fontsize=8)  # 只显示月-日

        # 成交量
        colors = ["#4CAF50" if closes[i] >= closes[max(0, i - 1)] else "#F44336"
                  for i in range(len(closes))]
        ax2.bar(range(len(volumes)), volumes, color=colors, alpha=0.7)
        ax2.set_ylabel("成交量", fontsize=9)
        ax2.set_xticks(tick_pos)
        ax2.set_xticklabels([dates[i][5:] for i in tick_pos], fontsize=8)

        fig.tight_layout()
        return _render_chart(fig)
    except Exception as e:
        return None


# ============================================================
# 5. 营收/净利润趋势图
# ============================================================

def generate_revenue_trend_chart(financial_data: List[Dict], stock_name: str = "") -> Optional[str]:
    """
    生成营收/净利润趋势图
    financial_data: [{"year": 2023, "quarter": 4, "revenue": 1000, "net_profit": 200}, ...]
    """
    try:
        plt = _setup_matplotlib()

        if not financial_data:
            return None

        # 按时间排序
        sorted_data = sorted(financial_data, key=lambda x: (x.get("year", 0), x.get("quarter", 0)))

        labels = [f"{d.get('year', '')}Q{d.get('quarter', '')}" for d in sorted_data[-12:]]  # 最近12个季度
        revenues = []
        profits = []

        for d in sorted_data[-12:]:
            # 尝试提取营收和净利润
            r = d.get("MBRevenue") or d.get("revenue") or d.get("营收") or 0
            p = d.get("netProfit") or d.get("net_profit") or d.get("净利润") or 0
            # 转换为亿
            try:
                r = float(r) / 1e8 if float(r) > 1e6 else float(r)
                p = float(p) / 1e8 if float(p) > 1e6 else float(p)
            except (ValueError, TypeError):
                r = 0
                p = 0
            revenues.append(r)
            profits.append(p)

        if all(r == 0 for r in revenues):
            return None

        fig, ax1 = plt.subplots(figsize=(10, 4))

        x = range(len(labels))
        ax1.bar([i - 0.15 for i in x], revenues, width=0.3, color="#2196F3", alpha=0.7, label="营收(亿)")
        ax1.bar([i + 0.15 for i in x], profits, width=0.3, color="#4CAF50", alpha=0.7, label="净利润(亿)")

        ax1.set_xticks(x)
        ax1.set_xticklabels(labels, fontsize=8, rotation=45)
        ax1.set_title(f"{stock_name} 营收与净利润趋势", fontsize=13, fontweight="bold")
        ax1.legend(fontsize=10)
        ax1.grid(axis="y", alpha=0.3)
        ax1.set_ylabel("金额 (亿元)")

        fig.tight_layout()
        return _render_chart(fig)
    except Exception:
        return None


# ============================================================
# 6. 利润率对比图
# ============================================================

def generate_margin_comparison_chart(fact_sheet: Dict[str, Any]) -> Optional[str]:
    """生成利润率对比图（毛利率 vs 净利率 vs ROE）"""
    try:
        plt = _setup_matplotlib()

        gross = (fact_sheet.get("gross_margin", 0) or 0) * 100
        net = (fact_sheet.get("net_margin", 0) or 0) * 100
        roe = (fact_sheet.get("roe", 0) or 0) * 100

        if gross == 0 and net == 0 and roe == 0:
            return None

        labels = ["毛利率", "净利率", "ROE"]
        values = [gross, net, roe]
        colors = ["#2196F3", "#4CAF50", "#FF9800"]

        fig, ax = plt.subplots(figsize=(6, 4))
        bars = ax.bar(labels, values, color=colors, width=0.5)

        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f"{val:.1f}%", ha="center", va="bottom", fontsize=12, fontweight="bold")

        ax.set_title("盈利能力指标", fontsize=14, fontweight="bold")
        ax.set_ylabel("百分比 (%)")
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()

        return _render_chart(fig)
    except Exception:
        return None


# ============================================================
# 7. 资金流向饼图
# ============================================================

def generate_fund_flow_chart(fund_data: Dict[str, Any]) -> Optional[str]:
    """
    生成资金流向饼图
    fund_data: {"main_inflow": 5.52, "retail_inflow": 4.11, "net": 1.40}
    """
    try:
        plt = _setup_matplotlib()

        main_in = fund_data.get("main_inflow", 0) or 0
        retail_in = fund_data.get("retail_inflow", 0) or 0

        if main_in == 0 and retail_in == 0:
            return None

        sizes = [abs(main_in), abs(retail_in)]
        labels = [f"主力流入\n{main_in:.1f}亿", f"散户流入\n{retail_in:.1f}亿"]
        colors = ["#F44336", "#2196F3"]
        explode = (0.05, 0)

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.pie(sizes, explode=explode, labels=labels, colors=colors,
               autopct="%1.1f%%", shadow=True, startangle=90, textprops={"fontsize": 11})
        ax.set_title("资金流向分布", fontsize=14, fontweight="bold")

        return _render_chart(fig)
    except Exception:
        return None


# ============================================================
# 批量生成
# ============================================================

def generate_all_charts(fact_sheet: Dict[str, Any],
                        bull_conf: int = 50, bear_conf: int = 50,
                        kline_data: List[Dict] = None,
                        financial_data: List[Dict] = None,
                        fund_data: Dict[str, Any] = None,
                        stock_name: str = "") -> Dict[str, str]:
    """生成所有图表，返回 {name: base64_url}"""
    charts = {}

    dupont = generate_dupont_chart(fact_sheet)
    if dupont:
        charts["dupont"] = dupont

    radar = generate_financial_metrics_chart(fact_sheet)
    if radar:
        charts["radar"] = radar

    confidence = generate_confidence_chart(bull_conf, bear_conf)
    if confidence:
        charts["confidence"] = confidence

    margins = generate_margin_comparison_chart(fact_sheet)
    if margins:
        charts["margins"] = margins

    if kline_data:
        kline = generate_kline_chart(kline_data, stock_name)
        if kline:
            charts["kline"] = kline

    if financial_data:
        trend = generate_revenue_trend_chart(financial_data, stock_name)
        if trend:
            charts["trend"] = trend

    if fund_data:
        flow = generate_fund_flow_chart(fund_data)
        if flow:
            charts["fund_flow"] = flow

    return charts


def save_all_charts(charts: Dict[str, str], output_dir: str, stock_code: str):
    """将所有图表保存到文件"""
    import os
    os.makedirs(output_dir, exist_ok=True)

    for name, b64_url in charts.items():
        # 解码 base64
        header, data = b64_url.split(",", 1)
        img_data = base64.b64decode(data)
        filepath = os.path.join(output_dir, f"{stock_code}_{name}.png")
        with open(filepath, "wb") as f:
            f.write(img_data)
