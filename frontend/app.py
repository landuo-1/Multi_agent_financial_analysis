"""
Streamlit 前端
A股上市公司多智能体金融分析系统的 Web UI
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import requests
import time

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

# Agent 名称中文化
AGENT_NAMES = {
    "Financial_Agent": "财务分析",
    "Industry_Agent": "行业分析",
    "Sentiment_Agent": "舆情分析",
    "Valuation_Agent": "估值分析",
}

# 指标名称中文化
METRIC_NAMES = {
    "roe": "净资产收益率(ROE)",
    "net_margin": "净利率",
    "gross_margin": "毛利率",
    "debt_ratio": "资产负债率",
    "current_ratio": "流动比率",
    "quick_ratio": "速动比率",
    "net_cash_ratio": "净现比",
    "asset_turnover": "总资产周转率",
    "equity_multiplier": "权益乘数",
    "revenue_growth": "营收增长率",
    "profit_growth": "净利润增长率",
    "pe_ttm": "市盈率(TTM)",
    "pb": "市净率",
    "ps": "市销率",
    "market_share": "市场份额",
    "sentiment_score": "情绪评分",
    "industry_growth": "行业增长率",
    "risk_signals": "风险信号",
    "roe_dupont": "ROE(杜邦)",
    "inventory_turnover": "存货周转率",
    "receivable_turnover": "应收账款周转率",
}


def _get_agent_name(name: str) -> str:
    """获取中文 Agent 名称"""
    return AGENT_NAMES.get(name, name)


def _get_metric_name(key: str) -> str:
    """获取中文指标名称"""
    return METRIC_NAMES.get(key, key)


def _format_value(v) -> str:
    """格式化数值（处理 list/float/str 等类型）"""
    if v is None or v == "" or v is False:
        return "—"
    if isinstance(v, list):
        return "、".join(str(x) for x in v if x)
    if isinstance(v, float):
        if abs(v) < 1 and v != 0:
            return f"{v:.2%}"
        else:
            return f"{v:.2f}"
    if isinstance(v, int):
        return str(v)
    return str(v)


# ============================================================
# API 调用
# ============================================================

def check_api_health() -> dict:
    try:
        return requests.get(f"{API_BASE}/api/health", timeout=5).json()
    except Exception:
        return {"status": "unreachable"}


def submit_analysis(query: str, max_rounds: int = 2) -> dict:
    resp = requests.post(
        f"{API_BASE}/api/analyze",
        json={"query": query, "max_debate_rounds": max_rounds},
        timeout=10,
    )
    return resp.json()


def get_task_result(task_id: str) -> dict:
    resp = requests.get(f"{API_BASE}/api/analyze/{task_id}", timeout=10)
    return resp.json()


def poll_until_done(task_id: str, progress_bar, status_text, max_wait: int = 540) -> dict:
    start = time.time()
    last_phase = ""
    while time.time() - start < max_wait:
        try:
            result = get_task_result(task_id)
            status = result.get("status", "pending")
            if status in ("completed", "failed"):
                progress_bar.progress(100)
                return result
            phase = result.get("current_phase", "")
            if phase != last_phase:
                last_phase = phase
                pct = min(95, int(result.get("progress_pct", 50)))
                progress_bar.progress(pct)
                status_text.text(f"⏳ {result.get('message', phase)}...")
        except Exception:
            pass
        time.sleep(3)
    return {"status": "timeout", "error": "分析超时"}


# ============================================================
# 页面渲染
# ============================================================

def init_session_state():
    for key, default in [
        ("task_id", None), ("analysis_result", None),
        ("is_analyzing", False), ("query", ""),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


def render_sidebar():
    with st.sidebar:
        st.title("⚙️ 系统状态")
        health = check_api_health()
        if health.get("status") == "ok":
            st.success("API 服务正常")
            st.text(f"LLM: {'✅' if health.get('llm_configured') else '❌'}")
            cache = health.get("cache_stats", {})
            st.text(f"缓存: {cache.get('active', 'N/A')} 条")
        else:
            st.error("API 不可达")
            st.code("python run.py server", language="bash")

        st.markdown("---")
        st.markdown("### 📊 常用股票")
        for name, code in [("贵州茅台", "600519"), ("宁德时代", "300750"),
                           ("比亚迪", "002594"), ("招商银行", "600036")]:
            if st.button(f"{name} ({code})"):
                st.session_state.query = f"分析{name}"

        st.markdown("---")
        st.markdown("### ⚙️ 配置")
        max_rounds = st.slider("辩论轮次", 1, 5, 2)
        return max_rounds


def render_agent_detail(output: dict):
    """渲染单个 Agent 的详细数据"""
    agent_name = _get_agent_name(output.get("agent_name", "Unknown"))
    status = output.get("status", "unknown")
    confidence = output.get("confidence_score", 0) or 0
    brief = output.get("brief_summary", "")
    fact_sheet = output.get("fact_sheet", {})

    status_icon = {"success": "✅", "partial": "⚠️", "failed": "❌"}.get(status, "❓")

    with st.expander(f"{status_icon} {agent_name} | 置信度: {confidence:.0f}", expanded=False):
        st.markdown(f"**核心结论**: {brief}")

        if fact_sheet:
            st.markdown("**详细指标**:")
            display_data = {}
            for k, v in fact_sheet.items():
                if k in ("risk_signals", "风险信号", "risk_alerts", "风险预警"):
                    continue
                display_data[_get_metric_name(k)] = _format_value(v)

            if display_data:
                import pandas as pd
                df = pd.DataFrame(list(display_data.items()), columns=["指标", "数值"])
                st.dataframe(df, width="stretch", hide_index=True)

            risk_signals = fact_sheet.get("风险信号", fact_sheet.get("risk_signals", fact_sheet.get("risk_alerts", [])))
            if risk_signals:
                st.markdown("**⚠️ 风险信号**:")
                if isinstance(risk_signals, list):
                    for signal in risk_signals:
                        if signal:
                            st.warning(str(signal))
                else:
                    st.warning(str(risk_signals))


def render_result(result: dict):
    """渲染分析结果"""
    st.markdown("---")

    status = result.get("status", "")
    if status == "failed":
        st.error(f"分析失败: {result.get('error', '未知错误')}")
        return
    if status != "completed":
        st.warning(f"任务状态: {status}")
        return

    # ===== 基本信息 =====
    st.subheader("📋 分析结果")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("股票代码", result.get("stock_code", "N/A"))
    with col2:
        st.metric("公司名称", result.get("stock_name", "N/A"))
    with col3:
        st.metric("置信度", f"{result.get('confidence', 0):.0%}")
    with col4:
        st.metric("耗时", f"{result.get('elapsed_seconds', 0):.1f}s")

    # ===== 辩论结论 =====
    debate = result.get("debate_summary")
    if debate:
        st.subheader("🎯 辩论结论")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("多方置信度", f"{debate.get('final_bull_confidence', 50)}")
        with c2:
            st.metric("空方置信度", f"{debate.get('final_bear_confidence', 50)}")
        with c3:
            winner = debate.get("winner", "undecided")
            icon = "🟢" if winner == "bull" else "🔴" if winner == "bear" else "🟡"
            winner_cn = {"bull": "多方胜", "bear": "空方胜", "consensus": "达成共识"}.get(winner, "未决")
            st.metric("判定结果", f"{icon} {winner_cn}")

        for point in debate.get("consensus", []):
            st.markdown(f"✅ {point}")
        risk = debate.get("risk_warning", "")
        if risk:
            st.warning(f"⚠️ {risk}")

    # ===== 子 Agent 详细数据 =====
    agent_outputs = result.get("agent_outputs", [])
    if agent_outputs:
        st.subheader("🔍 分析详情")
        for output in agent_outputs:
            render_agent_detail(output)

    # ===== HTML 报告预览 =====
    task_id = st.session_state.get("task_id", "")
    stock_code = result.get("stock_code", "report")
    final_report = result.get("final_report", "")

    st.subheader("📄 完整报告")
    if task_id:
        try:
            html_resp = requests.get(f"{API_BASE}/api/reports/{task_id}/html", timeout=30)
            if html_resp.status_code == 200:
                st.html(html_resp.content.decode("utf-8"))
            elif final_report:
                st.markdown(final_report)
        except Exception:
            if final_report:
                st.markdown(final_report)
    elif final_report:
        st.markdown(final_report)

    # ===== 下载 =====
    st.subheader("📥 导出下载")
    col1, col2, col3 = st.columns(3)

    with col1:
        if final_report:
            st.download_button(
                label="📄 Markdown",
                data=final_report.encode("utf-8"),
                file_name=f"{stock_code}_analysis.md",
                mime="text/markdown",
                width="stretch",
            )

    with col2:
        if task_id:
            try:
                html_resp = requests.get(f"{API_BASE}/api/reports/{task_id}/html", timeout=30)
                if html_resp.status_code == 200:
                    st.download_button(
                        label="🌐 HTML 报告",
                        data=html_resp.content,
                        file_name=f"{stock_code}_analysis.html",
                        mime="text/html",
                        width="stretch",
                    )
            except Exception:
                pass

    with col3:
        if task_id:
            try:
                xlsx_resp = requests.get(f"{API_BASE}/api/reports/{task_id}/excel", timeout=30)
                if xlsx_resp.status_code == 200:
                    st.download_button(
                        label="📊 Excel 数据底稿",
                        data=xlsx_resp.content,
                        file_name=f"{stock_code}_data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch",
                    )
            except Exception:
                pass


def render_main(max_rounds: int):
    st.title("📊 A股多智能体金融分析")
    st.caption("基于 LangGraph 的多智能体系统")

    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input(
            "请输入分析目标",
            value=st.session_state.query,
            placeholder="输入股票代码或公司名称，如 600519、贵州茅台、科大讯飞",
            key="query_input",
        )
    with col2:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        analyze_button = st.button("🔍 开始分析", type="primary", width="stretch")

    if query:
        st.session_state.query = query

    if analyze_button and query:
        st.session_state.is_analyzing = True
        st.session_state.analysis_result = None
        try:
            resp = submit_analysis(query, max_rounds)
            task_id = resp.get("task_id")
            if not task_id:
                st.error(f"提交失败: {resp}")
                st.session_state.is_analyzing = False
                return
            st.session_state.task_id = task_id

            progress_bar = st.progress(0)
            status_text = st.empty()
            status_text.text("⏳ 分析中，请耐心等待...")

            result = poll_until_done(task_id, progress_bar, status_text)
            st.session_state.analysis_result = result
            st.session_state.is_analyzing = False
            status_text.text("✅ 分析完成！" if result.get("status") == "completed" else f"❌ {result.get('error', '')}")

        except requests.ConnectionError:
            st.error("❌ 无法连接 API，请先启动: `python run.py server`")
            st.session_state.is_analyzing = False
        except Exception as e:
            st.error(f"❌ {e}")
            st.session_state.is_analyzing = False

    if st.session_state.analysis_result:
        render_result(st.session_state.analysis_result)


def main():
    init_session_state()
    st.set_page_config(page_title="A股多智能体金融分析", page_icon="📊", layout="wide")
    max_rounds = render_sidebar()
    render_main(max_rounds)


if __name__ == "__main__":
    main()
