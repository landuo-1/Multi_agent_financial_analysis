"""
做空方（Bear）辩论 Agent
基于利空事实寻找逻辑漏洞和风险点
"""

import json
from typing import Any, Dict, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from src.prompts.agent_prompts import BEAR_SYSTEM
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BearAgent:
    """做空方辩论 Agent"""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """解析 LLM 响应"""
        import re
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        matches = re.findall(json_pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _build_argument(self, state: Dict[str, Any], round_num: int,
                        bull_argument: str = None) -> Dict[str, Any]:
        """构建辩论论点"""
        debate_briefing = state.get("debate_briefing", {})
        debate_history = state.get("debate_history", [])

        # 提取利空事实
        facts_pool = debate_briefing.get("facts_pool", {})
        bullish_facts = facts_pool.get("bullish_facts", [])
        bearish_facts = facts_pool.get("bearish_facts", [])

        stock_name = debate_briefing.get("stock_name", "")

        if round_num == 1:
            # 第一轮：提出核心质疑点
            user_prompt = f"""这是关于 {stock_name} 的投资辩论第 1 轮。

**利空事实**：
{json.dumps(bearish_facts, ensure_ascii=False, indent=2)}

**利好事实**（供你寻找漏洞）：
{json.dumps(bullish_facts, ensure_ascii=False, indent=2)}

请提出你的核心质疑点（3-5 个），每个质疑必须有数据支撑。
输出 JSON 格式："""
        else:
            # 后续轮次：针对做多方的论点进行反驳
            bull_text = bull_argument or "无"
            prev_rounds = json.dumps(debate_history, ensure_ascii=False, indent=2)

            user_prompt = f"""这是关于 {stock_name} 的投资辩论第 {round_num} 轮。

**做多方上一轮论点**：
{bull_text}

**历史辩论记录**：
{prev_rounds}

**可用利空事实**：
{json.dumps(bearish_facts, ensure_ascii=False, indent=2)}

请针对做多方的具体论点进行针对性反驳。
输出 JSON 格式："""

        messages = [
            SystemMessage(content=BEAR_SYSTEM),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        parsed = self._parse_response(response.content)

        if parsed is None:
            return {
                "role": "bear",
                "round": round_num,
                "argument": "无法解析论点",
                "rebuttal_to": f"bull_round_{round_num - 1}" if round_num > 1 else None,
                "confidence": 50,
                "evidence_refs": [],
            }

        # 确保字段完整
        parsed.setdefault("role", "bear")
        parsed.setdefault("round", round_num)
        parsed.setdefault("rebuttal_to", f"bull_round_{round_num - 1}" if round_num > 1 else None)
        parsed.setdefault("confidence", 50)
        parsed.setdefault("evidence_refs", [])

        return parsed

    def __call__(self, state: Dict[str, Any], round_num: int = 1,
                 bull_argument: str = None) -> Dict[str, Any]:
        """执行一轮辩论"""
        logger.info(f"[Bear] 第 {round_num} 轮辩论")
        argument = self._build_argument(state, round_num, bull_argument)
        return argument
