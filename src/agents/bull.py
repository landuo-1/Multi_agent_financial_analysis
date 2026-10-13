"""
做多方（Bull）辩论 Agent
基于利好事实构建看多投资逻辑
"""

import json
from typing import Any, Dict, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from src.prompts.agent_prompts import BULL_SYSTEM
from src.utils.validators import parse_json_response
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BullAgent:
    """做多方辩论 Agent"""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def _build_argument(self, state: Dict[str, Any], round_num: int,
                        bear_argument: str = None) -> Dict[str, Any]:
        """构建辩论论点"""
        debate_briefing = state.get("debate_briefing", {})
        debate_history = state.get("debate_history", [])

        # 提取利好事实
        facts_pool = debate_briefing.get("facts_pool", {})
        bullish_facts = facts_pool.get("bullish_facts", [])
        bearish_facts = facts_pool.get("bearish_facts", [])

        stock_name = debate_briefing.get("stock_name", "")

        if round_num == 1:
            # 第一轮：提出核心看多论点
            user_prompt = f"""这是关于 {stock_name} 的投资辩论第 1 轮。

**利好事实**：
{json.dumps(bullish_facts, ensure_ascii=False, indent=2)}

**利空事实**（供你预判防御）：
{json.dumps(bearish_facts, ensure_ascii=False, indent=2)}

请提出你的核心看多论点（3-5 个），每个论点必须有数据支撑。
输出 JSON 格式："""
        else:
            # 后续轮次：针对做空方的质疑进行反驳
            bear_text = bear_argument or "无"
            prev_rounds = json.dumps(debate_history, ensure_ascii=False, indent=2)

            user_prompt = f"""这是关于 {stock_name} 的投资辩论第 {round_num} 轮。

**做空方上一轮论点**：
{bear_text}

**历史辩论记录**：
{prev_rounds}

**可用利好事实**：
{json.dumps(bullish_facts, ensure_ascii=False, indent=2)}

请针对做空方的具体论点进行针对性反驳。
输出 JSON 格式："""

        messages = [
            SystemMessage(content=BULL_SYSTEM),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        parsed = parse_json_response(response.content)

        if parsed is None:
            return {
                "role": "bull",
                "round": round_num,
                "argument": "无法解析论点",
                "rebuttal_to": f"bear_round_{round_num - 1}" if round_num > 1 else None,
                "confidence": 50,
                "evidence_refs": [],
            }

        # 确保字段完整
        parsed.setdefault("role", "bull")
        parsed.setdefault("round", round_num)
        parsed.setdefault("rebuttal_to", f"bear_round_{round_num - 1}" if round_num > 1 else None)
        parsed.setdefault("confidence", 50)
        parsed.setdefault("evidence_refs", [])

        return parsed

    def __call__(self, state: Dict[str, Any], round_num: int = 1,
                 bear_argument: str = None) -> Dict[str, Any]:
        """执行一轮辩论"""
        logger.info(f"[Bull] 第 {round_num} 轮辩论")
        argument = self._build_argument(state, round_num, bear_argument)
        return argument
