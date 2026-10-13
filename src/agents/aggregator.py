"""
汇聚仲裁器（Aggregator）
汇总所有子 Agent 输出，检测数据冲突，生成辩论简报
"""

import json
from typing import Any, Dict, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from src.prompts.agent_prompts import AGGREGATOR_SYSTEM
from src.state import AgentEnvelope, DebateBriefing, FactsPool
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 极性判断规则（中文字段名）
BULLISH_RULES = {
    "净资产收益率": lambda v: v > 0.20 if v else False,
    "毛利率": lambda v: v > 0.40 if v else False,
    "净利率": lambda v: v > 0.15 if v else False,
    "流动比率": lambda v: v > 2.0 if v else False,
    "营收增长率": lambda v: v > 0.10 if v else False,
    "净利润增长率": lambda v: v > 0.10 if v else False,
    "情绪评分": lambda v: v > 0.6 if v else False,
    "市场份额": lambda v: v > 0.10 if v else False,
}

BEARISH_RULES = {
    "资产负债率": lambda v: v > 0.60 if v else False,
    "净现比": lambda v: v < 0.70 if v else False,
    "净资产收益率": lambda v: v < 0.08 if v else False,
    "流动比率": lambda v: v < 1.0 if v else False,
    "市盈率": lambda v: v > 50 if v else False,
    "营收增长率": lambda v: v < 0 if v else False,
    "净利润增长率": lambda v: v < 0 if v else False,
}


def _judge_polarity(key: str, value: Any) -> str:
    """判断事实极性"""
    if value is None:
        return "NEUTRAL"

    # 尝试转换为数值
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        return "NEUTRAL"

    # 检查利好规则
    if key in BULLISH_RULES and BULLISH_RULES[key](num_value):
        return "BULL"

    # 检查利空规则
    if key in BEARISH_RULES and BEARISH_RULES[key](num_value):
        return "BEAR"

    return "NEUTRAL"


def _resolve_conflicts_with_llm(conflicts: List[Dict[str, Any]], llm: BaseChatModel) -> List[Dict[str, Any]]:
    """
    使用 LLM 解析数据冲突

    当多个 Agent 对同一指标给出不同数值时，
    LLM 判断哪个值更可信并给出理由。
    """
    from src.prompts.agent_prompts import AGGREGATOR_SYSTEM

    if not conflicts:
        return conflicts

    conflicts_text = json.dumps(conflicts, ensure_ascii=False, indent=2)
    user_prompt = f"""以下是从不同分析 Agent 中检测到的数据冲突：

{conflicts_text}

请判断每个冲突中哪个值更可信，并给出理由。
输出 JSON 格式：
```json
[
  {{"fact": "指标名", "resolution": "采用的值和来源", "reason": "判断理由"}}
]
```"""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = [
            SystemMessage(content=AGGREGATOR_SYSTEM),
            HumanMessage(content=user_prompt),
        ]
        response = llm.invoke(messages)
        parsed = parse_json_response(response.content)

        if parsed and isinstance(parsed, list):
            for i, resolution in enumerate(parsed):
                if i < len(conflicts):
                    conflicts[i]["resolution"] = resolution.get("resolution", "")
                    conflicts[i]["reason"] = resolution.get("reason", "")
                    conflicts[i]["status"] = "已解析"
    except Exception as e:
        logger.warning(f"[Aggregator] LLM 冲突解析失败: {e}")

    return conflicts


def aggregate_outputs(state: Dict[str, Any], llm: BaseChatModel = None) -> Dict[str, Any]:
    """
    汇聚所有子 Agent 输出
    生成辩论简报
    """
    agent_outputs = state.get("agent_outputs", {})
    shared_context = state.get("shared_context", {})
    stock_code = shared_context.get("stock_code", "")
    stock_name = shared_context.get("stock_name", "")

    if not agent_outputs:
        logger.warning("[Aggregator] 无子 Agent 输出")
        return {
            "debate_briefing": None,
            "errors": [{"phase": "aggregator", "error": "无子 Agent 输出"}],
        }

    # 1. 过滤和分类
    valid_outputs = {}
    failed_outputs = {}

    for agent_id, output in agent_outputs.items():
        status = output.get("status", "failed")
        if status in ("success", "partial"):
            valid_outputs[agent_id] = output
        else:
            failed_outputs[agent_id] = output

    logger.info(f"[Aggregator] 有效输出: {len(valid_outputs)}, 失败输出: {len(failed_outputs)}")

    # 2. 提取事实池
    bullish_facts = []
    bearish_facts = []
    neutral_facts = []
    agent_summaries = []

    for agent_id, output in valid_outputs.items():
        agent_name = output.get("agent_name", agent_id)
        fact_sheet = output.get("fact_sheet", {})
        brief_summary = output.get("brief_summary", "")
        confidence = output.get("confidence_score", 50)

        agent_summaries.append({
            "agent": agent_name,
            "summary": brief_summary,
            "confidence": confidence,
        })

        # 对每个事实判断极性
        risk_signal_keys = {"risk_signals", "风险信号", "risk_alerts", "风险预警"}
        for key, value in fact_sheet.items():
            if key in risk_signal_keys:
                continue

            polarity = _judge_polarity(key, value)
            fact_entry = {
                "fact": f"{key}={value}",
                "source": agent_name,
                "value": value,
                "key": key,
            }

            if polarity == "BULL":
                bullish_facts.append(fact_entry)
            elif polarity == "BEAR":
                bearish_facts.append(fact_entry)
            else:
                neutral_facts.append(fact_entry)

        # 处理风险信号（兼容中英文键名）
        risk_signals = []
        for rk in risk_signal_keys:
            signals = fact_sheet.get(rk, [])
            if isinstance(signals, list):
                risk_signals.extend(signals)
            elif signals:
                risk_signals.append(str(signals))
        for signal in risk_signals:
            if signal:
                bearish_facts.append({
                    "fact": str(signal),
                    "source": agent_name,
                    "value": None,
                    "key": "risk_signal",
                })

    # 3. 检测数据冲突
    conflicts = _detect_conflicts(valid_outputs)

    # 4. LLM 辅助冲突解析（当存在冲突且 LLM 可用时）
    if conflicts and llm:
        conflicts = _resolve_conflicts_with_llm(conflicts, llm)

    # 5. 识别缺失数据
    missing_data = _identify_missing_data(valid_outputs)

    # 5. 构建辩论简报
    facts_pool = FactsPool(
        bullish_facts=bullish_facts,
        bearish_facts=bearish_facts,
        neutral_facts=neutral_facts,
        conflicts=conflicts,
    )

    briefing = DebateBriefing(
        stock_code=stock_code,
        stock_name=stock_name,
        facts_pool=facts_pool,
        agent_summaries=agent_summaries,
        missing_data=missing_data,
    )

    logger.info(f"[Aggregator] 辩论简报生成完成: {len(bullish_facts)} 条利好, "
                f"{len(bearish_facts)} 条利空, {len(conflicts)} 条冲突")

    return {
        "debate_briefing": briefing.model_dump(),
        "current_phase": "aggregator_done",
        "messages": [{"role": "system", "content": f"汇聚完成: {len(bullish_facts)} 利好, {len(bearish_facts)} 利空"}],
    }


def _detect_conflicts(outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """检测不同 Agent 之间的数据冲突"""
    conflicts = []
    value_map: Dict[str, List[Dict]] = {}

    for agent_id, output in outputs.items():
        agent_name = output.get("agent_name", agent_id)
        fact_sheet = output.get("fact_sheet", {})

        for key, value in fact_sheet.items():
            if key == "risk_signals":
                continue
            if key not in value_map:
                value_map[key] = []
            value_map[key].append({"source": agent_name, "value": value})

    # 检测同一指标不同值
    for key, entries in value_map.items():
        if len(entries) > 1:
            values = [e["value"] for e in entries]
            # 如果值不完全相同，标记为冲突
            unique_values = set(str(v) for v in values)
            if len(unique_values) > 1:
                conflicts.append({
                    "fact": key,
                    "values": entries,
                    "status": "待核实",
                })

    return conflicts


def _identify_missing_data(outputs: Dict[str, Any]) -> List[str]:
    """识别缺失的数据维度（仅报告系统有能力采集但未运行的 Agent）"""
    expected_agents = ["财务分析", "行业分析", "舆情分析", "估值分析"]

    present_agents = set()
    for output in outputs.values():
        agent_name = output.get("agent_name", "")
        present_agents.add(agent_name)

    missing = [name for name in expected_agents if name not in present_agents]
    return missing


class AggregatorAgent:
    """汇聚仲裁器节点（LangGraph 节点）"""

    def __init__(self, llm: BaseChatModel = None):
        self.llm = llm

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return aggregate_outputs(state, self.llm)
