"""
子 Agent 基类
定义统一接口，包含信封校验和重试逻辑
"""

import json
import re
from typing import Any, Dict, Optional, List
from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from src.state import AgentEnvelope, ToolRequest
from src.utils.validators import validate_agent_envelope, parse_json_response
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FinancialAgentBase(ABC):
    """金融分析智能体基类"""

    def __init__(self, llm: BaseChatModel, agent_name: str = "Unknown", max_retries: int = 2):
        self.llm = llm
        self.agent_name = agent_name
        self.max_retries = max_retries

    @abstractmethod
    def _build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构建系统提示词"""
        pass

    @abstractmethod
    def _build_user_prompt(self, state: Dict[str, Any]) -> str:
        """构建用户提示词"""
        pass

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """从 LLM 响应中提取 JSON（委托给共享实现）"""
        return parse_json_response(text)

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self.llm.invoke(messages)
        return response.content

    def _validate_and_retry(self, raw_output: Dict[str, Any]) -> Dict[str, Any]:
        """校验输出格式，失败则重试"""
        valid, envelope, error = validate_agent_envelope(raw_output)
        if valid and envelope:
            return envelope.model_dump()

        # 校验失败，尝试修复常见问题
        if "agent_name" not in raw_output:
            raw_output["agent_name"] = self.agent_name
        if "status" not in raw_output:
            raw_output["status"] = "partial"
        if "brief_summary" not in raw_output:
            raw_output["brief_summary"] = "分析完成，但输出格式不完整"
        if "fact_sheet" not in raw_output:
            raw_output["fact_sheet"] = {}

        valid, envelope, error = validate_agent_envelope(raw_output)
        if valid and envelope:
            return envelope.model_dump()

        # 仍然失败，返回一个默认信封
        logger.warning(f"{self.agent_name} 信封校验失败，使用默认格式: {error}")
        return AgentEnvelope(
            agent_name=self.agent_name,
            status="failed",
            fact_sheet={},
            brief_summary=f"输出格式校验失败: {error}",
            confidence_score=0,
        ).model_dump()

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 Agent 逻辑（带重试）
        返回校验后的 AgentEnvelope
        """
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"[{self.agent_name}] 执行中... (尝试 {attempt + 1})")

                system_prompt = self._build_system_prompt(state)
                user_prompt = self._build_user_prompt(state)
                raw_response = self._call_llm(system_prompt, user_prompt)

                parsed = self._parse_json_response(raw_response)
                if parsed is None:
                    logger.warning(f"[{self.agent_name}] 无法解析 JSON 响应")
                    if attempt < self.max_retries:
                        continue
                    return AgentEnvelope(
                        agent_name=self.agent_name,
                        status="failed",
                        fact_sheet={},
                        brief_summary="LLM 输出无法解析为 JSON",
                        confidence_score=0,
                    ).model_dump()

                return self._validate_and_retry(parsed)

            except Exception as e:
                logger.error(f"[{self.agent_name}] 执行异常: {e}")
                if attempt < self.max_retries:
                    continue
                return AgentEnvelope(
                    agent_name=self.agent_name,
                    status="failed",
                    fact_sheet={},
                    brief_summary=f"执行异常: {str(e)}",
                    confidence_score=0,
                ).model_dump()

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph 节点调用入口"""
        return self.execute(state)


class DynamicAgent(FinancialAgentBase):
    """动态子 Agent（由 Supervisor 动态生成）"""

    def __init__(self, llm: BaseChatModel, agent_config: Dict[str, Any]):
        super().__init__(llm, agent_name=agent_config.get("agent_id", "dynamic_agent"))
        self.capability = agent_config.get("capability", "")
        self.input_schema = agent_config.get("input_schema", [])
        self.tools = agent_config.get("tools", [])
        self.data_subset = agent_config.get("data_subset", {})

    def _build_system_prompt(self, state: Dict[str, Any]) -> str:
        return f"""你是一个专业的金融分析子 Agent，专门负责：{self.capability}

你的分析必须基于提供的数据，不得编造任何数字。
如果数据不足，标注"数据不足"并说明需要什么数据。

输出必须为 JSON 格式：
{{
    "agent_name": "{self.agent_name}",
    "status": "success" | "partial" | "failed",
    "fact_sheet": {{}},
    "brief_summary": "200字以内核心结论",
    "confidence_score": 0-100
}}"""

    def _build_user_prompt(self, state: Dict[str, Any]) -> str:
        data_str = json.dumps(self.data_subset, ensure_ascii=False, indent=2, default=str)
        return f"""请基于以下数据进行分析：

**分析任务**：{self.capability}
**可用数据**：
{data_str}

请输出分析结果（JSON 格式）："""

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行动态 Agent"""
        # 更新数据子集
        shared_context = state.get("shared_context", {})
        if shared_context:
            self.data_subset = {
                key: shared_context.get(key)
                for key in self.input_schema
                if key in shared_context
            }

        return super().execute(state)
