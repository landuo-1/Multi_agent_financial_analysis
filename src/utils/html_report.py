"""
HTML 报告生成模块
生成专业排版的 HTML 报告，支持嵌入图表、表格、交互式展示
"""

import os
import time
from typing import Any, Dict, List, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


def generate_html_report(stock_code: str, stock_name: str,
                         final_report: str, agent_outputs: Dict[str, Any],
                         debate_consensus: Dict[str, Any] = None,
                         charts: Dict[str, str] = None,
                         data_freshness: str = "",
                         data_period: str = "") -> str:
    """
    生成完整的 HTML 报告

    Args:
        stock_code: 股票代码
        stock_name: 公司名称
        final_report: Markdown 格式的报告文本
        agent_outputs: 各 Agent 输出
        debate_consensus: 辩论结论
        charts: 图表 {name: base64_url}
        data_freshness: 数据截止日期
        data_period: 财务数据所属期间（如 2025Q4）
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M")

    # 解析 Markdown 为 HTML
    report_html = _markdown_to_html(final_report)

    # 构建 Agent 数据卡片
    agent_cards = _build_agent_cards(agent_outputs)

    # 构建辩论结论卡片
    debate_card = _build_debate_card(debate_consensus)

    # 构建图表区域
    charts_html = _build_charts_section(charts)

    # 构建数据表格
    data_table = _build_data_table(agent_outputs, data_period)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{stock_name}({stock_code}) 投资价值分析报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
            background: #f5f7fa; color: #333; line-height: 1.8;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}

        /* 头部 */
        .header {{
            background: linear-gradient(135deg, #1a5276, #2874a6);
            color: white; padding: 40px; border-radius: 12px; margin-bottom: 30px;
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header .meta {{ opacity: 0.85; font-size: 14px; }}
        .header .meta span {{ margin-right: 20px; }}

        /* 导航标签 */
        .tabs {{
            display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap;
        }}
        .tab {{
            padding: 10px 20px; background: white; border: 1px solid #ddd;
            border-radius: 8px; cursor: pointer; font-size: 14px;
            transition: all 0.2s;
        }}
        .tab:hover {{ background: #e8f4fd; border-color: #2874a6; }}
        .tab.active {{ background: #2874a6; color: white; border-color: #2874a6; }}

        /* 内容区 */
        .section {{
            background: white; border-radius: 12px; padding: 30px;
            margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .section h2 {{
            color: #1a5276; font-size: 20px; margin-bottom: 20px;
            padding-bottom: 10px; border-bottom: 2px solid #e8f4fd;
        }}
        .section h3 {{ color: #2874a6; font-size: 16px; margin: 15px 0 10px; }}

        /* 指标卡片 */
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .metric-card {{
            background: #f8f9fa; border-radius: 8px; padding: 15px; text-align: center;
            border-left: 4px solid #2874a6;
        }}
        .metric-card .label {{ font-size: 12px; color: #666; margin-bottom: 5px; }}
        .metric-card .value {{ font-size: 24px; font-weight: bold; color: #1a5276; }}
        .metric-card.bull {{ border-left-color: #4CAF50; }}
        .metric-card.bull .value {{ color: #4CAF50; }}
        .metric-card.bear {{ border-left-color: #F44336; }}
        .metric-card.bear .value {{ color: #F44336; }}

        /* 表格 */
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #1a5276; }}
        tr:hover {{ background: #f8f9fa; }}

        /* 图表 */
        .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }}
        .chart-card {{
            background: #f8f9fa; border-radius: 8px; padding: 15px; text-align: center;
        }}
        .chart-card img {{ max-width: 100%; height: auto; border-radius: 4px; }}
        .chart-card .title {{ font-size: 13px; color: #666; margin-top: 8px; }}

        /* Agent 卡片 */
        .agent-card {{
            border: 1px solid #eee; border-radius: 8px; padding: 20px; margin: 15px 0;
        }}
        .agent-card.success {{ border-left: 4px solid #4CAF50; }}
        .agent-card.partial {{ border-left: 4px solid #FF9800; }}
        .agent-card.failed {{ border-left: 4px solid #F44336; }}
        .agent-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .agent-name {{ font-weight: bold; font-size: 16px; }}
        .agent-status {{ padding: 3px 10px; border-radius: 12px; font-size: 12px; }}
        .agent-status.success {{ background: #e8f5e9; color: #2e7d32; }}
        .agent-status.partial {{ background: #fff3e0; color: #e65100; }}
        .agent-status.failed {{ background: #ffebee; color: #c62828; }}

        /* 辩论区 */
        .debate {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 15px 0; }}
        .debate-side {{ padding: 15px; border-radius: 8px; }}
        .debate-bull {{ background: #e8f5e9; border: 1px solid #c8e6c9; }}
        .debate-bear {{ background: #ffebee; border: 1px solid #ffcdd2; }}
        .debate-side h4 {{ margin-bottom: 10px; }}

        /* 免责声明 */
        .disclaimer {{
            background: #fff3cd; border: 1px solid #ffc107; padding: 20px;
            border-radius: 8px; margin-top: 30px; font-size: 13px; color: #856404;
        }}

        /* 报告正文 */
        .report-content {{ line-height: 2; }}
        .report-content table {{ margin: 20px 0; }}
        .report-content blockquote {{
            border-left: 4px solid #2874a6; padding: 10px 20px;
            margin: 15px 0; background: #f8f9fa;
        }}

        /* 风险信号 */
        .risk {{ background: #fff3e0; border-left: 4px solid #FF9800; padding: 10px 15px; margin: 8px 0; border-radius: 4px; }}

        /* 响应式 */
        @media (max-width: 768px) {{
            .debate {{ grid-template-columns: 1fr; }}
            .charts {{ grid-template-columns: 1fr; }}
            .metrics {{ grid-template-columns: repeat(2, 1fr); }}
        }}

        /* 打印样式 */
        @media print {{
            body {{ background: white; }}
            .tabs {{ display: none; }}
            .section {{ box-shadow: none; border: 1px solid #eee; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部 -->
        <div class="header">
            <h1>{stock_name}（{stock_code}）投资价值分析报告</h1>
            <div class="meta">
                <span>📅 生成时间：{timestamp}</span>
                <span>📊 数据截止：{data_freshness or timestamp}</span>
                <span>🤖 AI 多智能体系统生成</span>
            </div>
        </div>

        <!-- 辩论结论 -->
        {debate_card}

        <!-- Agent 分析详情 -->
        <div class="section">
            <h2>🔍 分析详情</h2>
            {agent_cards}
        </div>

        <!-- 数据底稿 -->
        {data_table}

        <!-- 完整报告 -->
        <div class="section">
            <h2>📄 完整报告</h2>
            <div class="report-content">
                {report_html}
            </div>
        </div>

        <!-- 免责声明 -->
        <div class="disclaimer">
            <strong>⚠️ 免责声明：</strong>本报告由 AI 多智能体系统生成，仅供学习与研究参考，不构成任何投资建议。
            股市有风险，投资需谨慎。最终投资决策前请务必咨询持牌投资顾问。
            报告中的数据来源于 BaoStock、AKShare 和 MCP 公开接口，截止日期为 {data_freshness or timestamp}。
        </div>
    </div>
</body>
</html>"""

    return html


def _markdown_to_html(md_text: str) -> str:
    """Markdown 转 HTML"""
    try:
        import markdown
        return markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "codehilite", "toc"],
        )
    except ImportError:
        # 简单转换
        html = md_text
        html = html.replace("\n\n", "</p><p>")
        html = html.replace("\n", "<br>")
        return f"<p>{html}</p>"


def _format_html_value(value) -> str:
    """格式化 HTML 显示值（处理 list/float/str）"""
    if value is None or value == "" or value is False:
        return "—"
    if isinstance(value, list):
        return "、".join(str(x) for x in value if x)
    if isinstance(value, float):
        if abs(value) < 1 and value != 0:
            return f"{value:.2%}"
        else:
            return f"{value:.2f}"
    return str(value)


def _build_agent_cards(agent_outputs: Dict[str, Any]) -> str:
    """构建 Agent 分析卡片"""
    cards = []
    for agent_id, output in agent_outputs.items():
        name = output.get("agent_name", agent_id)
        status = output.get("status", "unknown")
        confidence = output.get("confidence_score", 0) or 0
        summary = output.get("brief_summary", "")
        fact_sheet = output.get("fact_sheet", {})

        status_text = {"success": "✅ 成功", "partial": "⚠️ 部分", "failed": "❌ 失败"}.get(status, status)

        # 构建指标表格（更清晰）
        table_rows = ""
        for key, value in fact_sheet.items():
            if key in ("risk_signals", "风险信号", "risk_alerts", "风险预警"):
                continue
            formatted = _format_html_value(value)
            table_rows += f"<tr><td>{key}</td><td>{formatted}</td></tr>\n"

        table_html = ""
        if table_rows:
            table_html = f"""
            <table style="width:100%;margin:10px 0;">
                <thead><tr><th style="text-align:left;padding:6px 10px;background:#f0f4f8;">指标</th>
                <th style="text-align:left;padding:6px 10px;background:#f0f4f8;">数值</th></tr></thead>
                <tbody>{table_rows}</tbody>
            </table>"""

        # 风险信号（兼容中英文字段名）
        risks_html = ""
        risk_signals = fact_sheet.get("风险信号", fact_sheet.get("risk_signals", fact_sheet.get("risk_alerts", [])))
        if risk_signals:
            if isinstance(risk_signals, list):
                for signal in risk_signals:
                    if signal:
                        risks_html += f'<div class="risk">⚠️ {signal}</div>\n'
            else:
                risks_html += f'<div class="risk">⚠️ {risk_signals}</div>\n'

        cards.append(f"""
        <div class="agent-card {status}">
            <div class="agent-header">
                <span class="agent-name">{name}</span>
                <span class="agent-status {status}">{status_text} | 置信度: {confidence:.0f}</span>
            </div>
            <p>{summary}</p>
            {table_html}
            {risks_html}
        </div>""")

    return "\n".join(cards)


def _build_debate_card(debate_consensus: Dict[str, Any]) -> str:
    """构建辩论结论卡片"""
    if not debate_consensus:
        return ""

    bull = debate_consensus.get("final_bull_confidence", 50)
    bear = debate_consensus.get("final_bear_confidence", 50)
    winner = debate_consensus.get("winner", "undecided")
    risk = debate_consensus.get("risk_warning", "")
    rounds = debate_consensus.get("debate_rounds", 0)
    consensus = debate_consensus.get("consensus", [])
    disagreements = debate_consensus.get("disagreements", [])

    winner_text = {"bull": "🟢 多方胜", "bear": "🔴 空方胜", "consensus": "🟡 达成共识"}.get(winner, "🟡 未决")

    consensus_html = "".join(f"<li>✅ {c}</li>" for c in consensus)
    disagree_html = ""
    for d in disagreements:
        disagree_html += f"""
        <div class="debate">
            <div class="debate-side debate-bull"><h4>🟢 多方</h4><p>{d.get('bull_view', '')}</p></div>
            <div class="debate-side debate-bear"><h4>🔴 空方</h4><p>{d.get('bear_view', '')}</p></div>
        </div>"""

    return f"""
    <div class="section">
        <h2>🎯 辩论结论</h2>
        <div class="metrics">
            <div class="metric-card bull"><div class="label">多方置信度</div><div class="value">{bull}%</div></div>
            <div class="metric-card bear"><div class="label">空方置信度</div><div class="value">{bear}%</div></div>
            <div class="metric-card"><div class="label">辩论轮次</div><div class="value">{rounds}</div></div>
            <div class="metric-card"><div class="label">判定结果</div><div class="value">{winner_text}</div></div>
        </div>
        {"<h3>共识点</h3><ul>" + consensus_html + "</ul>" if consensus else ""}
        {disagree_html}
        {"<div class='risk'><strong>⚠️ 风险提示：</strong>" + risk + "</div>" if risk else ""}
    </div>"""


def _build_charts_section(charts: Dict[str, str]) -> str:
    """构建图表区域"""
    if not charts:
        return ""

    chart_names = {
        "dupont": "杜邦分析分解",
        "radar": "财务健康度雷达图",
        "confidence": "多空置信度对比",
        "margins": "盈利能力指标",
        "kline": "股价走势",
        "trend": "营收与净利润趋势",
        "fund_flow": "资金流向分布",
    }

    items = []
    for name, img_url in charts.items():
        title = chart_names.get(name, name)
        items.append(f"""
        <div class="chart-card">
            <img src="{img_url}" alt="{title}">
            <div class="title">{title}</div>
        </div>""")

    return f"""
    <div class="section">
        <h2>📊 可视化分析</h2>
        <div class="charts">{"".join(items)}</div>
    </div>"""


def _build_data_table(agent_outputs: Dict[str, Any], data_period: str = "") -> str:
    """构建数据底稿表格"""
    rows = []
    for agent_id, output in agent_outputs.items():
        name = output.get("agent_name", agent_id)
        if not name.endswith("Agent"):
            name = f"{name}Agent"

        fact_sheet = output.get("fact_sheet", {})
        for key, value in fact_sheet.items():
            if key in ("risk_signals", "风险信号", "risk_alerts", "风险预警"):
                for signal in (value or []):
                    rows.append(f"<tr><td>{name}</td><td>风险信号</td><td>{signal}</td><td></td></tr>")
            elif value is not None and value != "" and value is not False:
                if isinstance(value, list):
                    formatted = "、".join(str(x) for x in value if x)
                elif isinstance(value, float):
                    formatted = f"{value:.4f}" if abs(value) >= 1 else f"{value:.2%}"
                else:
                    formatted = str(value)

                # 数据年份：财务/估值 Agent 有明确年份，行业/舆情 Agent 留空
                year = data_period if "财务" in name or "估值" in name else ""
                rows.append(f"<tr><td>{name}</td><td>{key}</td><td>{formatted}</td><td>{year}</td></tr>")

    if not rows:
        return ""

    return f"""
    <div class="section">
        <h2>📋 数据底稿</h2>
        <table>
            <thead><tr><th>来源</th><th>指标</th><th>数值</th><th>数据年份</th></tr></thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
    </div>"""


def save_html_report(html_content: str, output_dir: str, stock_code: str) -> str:
    """保存 HTML 报告到文件"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"{stock_code}_{timestamp}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"HTML 报告已保存: {filepath}")
    return filepath
