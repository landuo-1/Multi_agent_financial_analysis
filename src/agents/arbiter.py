"""
辩论仲裁员（Arbiter）
审阅辩论记录，提炼共识与分歧，判定胜方
"""

import json
from typing import Any, Dict, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from src.prompts.agent_prompts import ARBITER_SYSTEM
from src.utils.validators import parse_json_response
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ArbiterAgent:
    """辩论仲裁员"""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def _determine_winner(self, debate_history: List[Dict]) -> Dict[str, Any]:
        """基于置信度判定辩论结果"""
        if not debate_history:
            return {"winner": "undecided", "final_bull_confidence": 50, "final_bear_confidence": 50}

        # 获取最后一轮的置信度
        bull_confidence = 50
        bear_confidence = 50

        for arg in debate_history:
            if arg.get("role") == "bull":
                bull_confidence = arg.get("confidence", 50)
            elif arg.get("role") == "bear":
                bear_confidence = arg.get("confidence", 50)

        # 计算轮次
        debate_rounds = len(debate_history) // 2

        # 判定逻辑（与 graph.py._run_debate 终止条件一致）
        diff = abs(bull_confidence - bear_confidence)

        if bull_confidence < 20:
            winner = "bear"
        elif bear_confidence < 20:
            winner = "bull"
        elif diff < 15:
            winner = "consensus"
        elif debate_rounds >= 4 and diff > 40:
            winner = "stalemate"
        else:
            winner = "bull" if bull_confidence > bear_confidence else "bear"

        return {
            "winner": winner,
            "final_bull_confidence": bull_confidence,
            "final_bear_confidence": bear_confidence,
            "confidence_diff": diff,
        }

    def arbitrate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行仲裁"""
        debate_history = state.get("debate_history", [])
        debate_briefing = state.get("debate_briefing", {})
        stock_name = debate_briefing.get("stock_name", "")

        # 先用规则判定
        rule_result = self._determine_winner(debate_history)

        # 尝试用 LLM 生成更详细的仲裁
        debate_text = json.dumps(debate_history, ensure_ascii=False, indent=2)

        user_prompt = f"""请对以下 {stock_name} 的投资辩论进行仲裁。

**辩论记录**：
{debate_text}

**规则判定结果**：
- 多方置信度：{rule_result['final_bull_confidence']}
- 空方置信度：{rule_result['final_bear_confidence']}
- 胜方：{rule_result['winner']}

请输出仲裁结果（JSON 格式），包括：
1. 双方共识点
2. 未达成共识的分歧
3. 核心风险提示
4. 最终判定"""

        try:
            messages = [
                SystemMessage(content=ARBITER_SYSTEM),
                HumanMessage(content=user_prompt),
            ]
            response = self.llm.invoke(messages)
            parsed = parse_json_response(response.content)

            if parsed:
                # 合并规则判定和 LLM 输出
                # 置信度和轮次以规则判定为准（LLM 可能输出错误数值）
                parsed["final_bull_confidence"] = rule_result["final_bull_confidence"]
                parsed["final_bear_confidence"] = rule_result["final_bear_confidence"]
                parsed["winner"] = rule_result["winner"]
                parsed["debate_rounds"] = len(debate_history) // 2
                return parsed

        except Exception as e:
            logger.error(f"[Arbiter] LLM 调用失败: {e}")

        # LLM 失败时使用规则判定结果
        return {
            "consensus": ["基于规则判定"],
            "disagreements": [],
            "risk_warning": "LLM 仲裁失败，使用规则判定结果",
            "final_bull_confidence": rule_result["final_bull_confidence"],
            "final_bear_confidence": rule_result["final_bear_confidence"],
            "debate_rounds": len(debate_history) // 2,
            "winner": rule_result["winner"],
        }

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph 节点入口"""
        logger.info("[Arbiter] 开始仲裁")
        result = self.arbitrate(state)
        return {
            "debate_consensus": result,
            "messages": [{"role": "system", "content": f"辩论仲裁完成，胜方: {result.get('winner', 'undecided')}"}],
        }
