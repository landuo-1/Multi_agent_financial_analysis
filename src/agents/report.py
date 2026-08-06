"""
报告主笔（Report Agent）
基于辩论结论生成结构化 Markdown 报告
"""

import json
import time
import os
from typing import Any, Dict, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from src.prompts.agent_prompts import REPORT_SYSTEM, COMPLIANCE_DISCLAIMER
from src.utils.citation import CitationManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ReportAgent:
    """报告主笔 Agent"""

    def __init__(self, llm: BaseChatModel, output_dir: str = "./reports"):
        self.llm = llm
        self.output_dir = output_dir
        self.citation_mgr = CitationManager()

    def _parse_response(self, text: str) -> str:
        """提取 Markdown 报告内容"""
        # 如果响应中包含 markdown 代码块，提取内容
        import re
        md_pattern = r'```(?:markdown)?\s*\n(.*?)\n```'
        matches = re.findall(md_pattern, text, re.DOTALL)
        if matches:
            return matches[0].strip()
        return text.strip()

    def _build_report_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """构建报告上下文"""
        shared_context = state.get("shared_context", {})
        debate_consensus = state.get("debate_consensus", {})
        debate_briefing = state.get("debate_briefing", {})
        agent_outputs = state.get("agent_outputs", {})
        debate_history = state.get("debate_history", [])

        # 提取关键财务数据
        financials = shared_context.get("financials", {})
        valuation = shared_context.get("valuation", {})

        # 提取各 Agent 分析结果
        agent_summaries = []
        for agent_id, output in agent_outputs.items():
            agent_summaries.append({
                "agent_name": output.get("agent_name", agent_id),
                "status": output.get("status", "unknown"),
                "fact_sheet": output.get("fact_sheet", {}),
                "brief_summary": output.get("brief_summary", ""),
                "confidence_score": output.get("confidence_score", 0),
            })

        return {
            "stock_code": shared_context.get("stock_code", ""),
            "stock_name": shared_context.get("stock_name", ""),
            "data_freshness": shared_context.get("data_freshness", ""),
            "agent_summaries": agent_summaries,
            "debate_consensus": debate_consensus,
            "debate_history": debate_history,
            "bullish_facts": debate_briefing.get("facts_pool", {}).get("bullish_facts", []),
            "bearish_facts": debate_briefing.get("facts_pool", {}).get("bearish_facts", []),
            "conflicts": debate_briefing.get("facts_pool", {}).get("conflicts", []),
            "missing_data": debate_briefing.get("missing_data", []),
        }

    def generate_report(self, state: Dict[str, Any]) -> str:
        """生成投资分析报告"""
        context = self._build_report_context(state)
        stock_name = context["stock_name"]
        stock_code = context["stock_code"]

        logger.info(f"[Report] 开始生成报告: {stock_name}({stock_code})")

        # 构建 LLM Prompt
        context_str = json.dumps(context, ensure_ascii=False, indent=2, default=str)

        user_prompt = f"""请基于以下分析数据生成 {stock_name}（{stock_code}）的投资价值分析报告。

**分析数据**：
{context_str}

请按照报告模板生成完整的 Markdown 报告。不要添加脚注或引用标记。"""

        try:
            messages = [
                SystemMessage(content=REPORT_SYSTEM),
                HumanMessage(content=user_prompt),
            ]
            response = self.llm.invoke(messages)
            report = self._parse_response(response.content)

            # 添加免责声明（如果没有）
            if "免责声明" not in report:
                report = report + "\n\n---\n" + COMPLIANCE_DISCLAIMER

            logger.info(f"[Report] 报告生成完成，长度: {len(report)} 字符")
            return report

        except Exception as e:
            logger.error(f"[Report] LLM 调用失败: {e}")
            return self._generate_fallback_report(context)

    def _generate_fallback_report(self, context: Dict[str, Any]) -> str:
        """LLM 失败时的降级报告"""
        stock_name = context["stock_name"]
        stock_code = context["stock_code"]
        today = time.strftime("%Y-%m-%d")

        report = f"""# {stock_name}（{stock_code}）投资价值分析报告

> 生成时间：{today} | 数据截止：{context.get('data_freshness', today)}

## 一、执行摘要

本报告由 AI 多智能体系统自动生成。由于 LLM 服务异常，本报告为降级版本，仅展示各 Agent 的原始分析结果。

## 二、各 Agent 分析结果

"""
        for agent in context.get("agent_summaries", []):
            report += f"### {agent['agent_name']}\n"
            report += f"- **状态**: {agent['status']}\n"
            report += f"- **置信度**: {agent['confidence_score']}\n"
            report += f"- **核心结论**: {agent['brief_summary']}\n\n"

            if agent.get("fact_sheet"):
                report += "**关键指标**：\n"
                for k, v in agent["fact_sheet"].items():
                    if k != "risk_signals":
                        report += f"- {k}: {v}\n"
                report += "\n"

        # 辩论结论
        consensus = context.get("debate_consensus", {})
        if consensus:
            report += "## 三、辩论结论\n\n"
            report += f"- **多方置信度**: {consensus.get('final_bull_confidence', 'N/A')}\n"
            report += f"- **空方置信度**: {consensus.get('final_bear_confidence', 'N/A')}\n"
            report += f"- **胜方**: {consensus.get('winner', 'N/A')}\n"
            report += f"- **风险提示**: {consensus.get('risk_warning', 'N/A')}\n\n"

            if consensus.get("consensus"):
                report += "**共识点**：\n"
                for c in consensus["consensus"]:
                    report += f"- {c}\n"

        report += "\n---\n" + COMPLIANCE_DISCLAIMER
        return report

    def save_report(self, report: str, stock_code: str) -> str:
        """保存报告到文件"""
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{stock_code}_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)

        logger.info(f"[Report] 报告已保存: {filepath}")
        return filepath

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph 节点入口"""
        report = self.generate_report(state)

        # 保存报告
        stock_code = state.get("shared_context", {}).get("stock_code", "unknown")
        report_path = self.save_report(report, stock_code)

        return {
            "final_report": report,
            "report_id": report_path,
            "current_phase": "report_done",
            "messages": [{"role": "system", "content": f"报告已生成: {report_path}"}],
        }
