"""
Supervisor 监督智能体
预置专家池 + 智能路由模式

核心设计：
1. AGENT_POOL 预置所有可用 Agent（代码写死，不动态生成）
2. 轻量意图分类器（关键词匹配）先做粗筛
3. LLM 只做"选择题"——从池中选 2-4 个 Agent 激活
4. 按需激活 = 节省 Token + 加快速度
"""

import json
import re
from typing import Any, Dict, List, Optional, Set
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 预置专家池（写死在代码里，不动态生成）
# ============================================================

AGENT_POOL = {
    "financial_agent": {
        "agent_id": "financial_agent_001",
        "capability": "财务健康度分析：杜邦分解、盈利质量、偿债能力、现金流质量",
        "input_schema": ["financials"],
        "tools": ["calculate_dupont", "calculate_cashflow_quality", "calculate_debt_ratio"],
        "priority": 1,
        "keywords": ["财务", "盈利", "利润", "现金流", "负债", "偿债", "ROE", "毛利率", "净利率",
                     "杜邦", "资产负债率", "流动比率", "速动比率", "周转率", "应收账款"],
        "description": "分析公司财务报表，评估盈利能力和财务健康度",
    },
    "industry_agent": {
        "agent_id": "industry_agent_001",
        "capability": "行业竞争格局与产业链地位分析",
        "input_schema": ["basic_info", "valuation"],
        "tools": ["get_industry_pe"],
        "priority": 2,
        "keywords": ["行业", "竞争", "市占率", "龙头", "产业链", "对手", "格局", "景气",
                     "周期", "政策", "集中度", "护城河", "壁垒"],
        "description": "分析公司在行业中的竞争地位和产业链议价能力",
    },
    "sentiment_agent": {
        "agent_id": "sentiment_agent_001",
        "capability": "舆情与市场情绪分析",
        "input_schema": ["stock_name", "stock_code"],
        "tools": ["get_stock_news"],
        "priority": 3,
        "keywords": ["舆情", "新闻", "情绪", "资金", "主力", "北向", "机构", "调研",
                     "评级", "预期", "市场", "热度", "关注度"],
        "description": "分析市场情绪、资金流向和机构动向",
    },
    "valuation_agent": {
        "agent_id": "valuation_agent_001",
        "capability": "估值分析：DCF 绝对估值 + PE/PB 相对估值",
        "input_schema": ["financials", "valuation"],
        "tools": ["calculate_dcf", "calculate_pe_valuation"],
        "priority": 4,
        "keywords": ["估值", "PE", "PB", "DCF", "市盈率", "市净率", "折现", "便宜",
                     "贵", "合理", "目标价", "上涨空间", "安全边际"],
        "description": "使用多种估值方法评估公司合理价值",
    },
}

# 默认激活所有 Agent（用户问题模糊时的兜底策略）
DEFAULT_ACTIVATED = list(AGENT_POOL.keys())


def _lightweight_intent_classify(query: str) -> Set[str]:
    """
    轻量级意图分类器（纯关键词匹配，不调 LLM）
    返回可能相关的 agent_id 集合
    """
    query_lower = query.lower()
    matched = set()

    for agent_type, config in AGENT_POOL.items():
        for kw in config["keywords"]:
            if kw.lower() in query_lower:
                matched.add(agent_type)
                break

    return matched


def _build_routing_prompt(query: str, stock_name: str, stock_code: str,
                          candidates: Set[str], available_data: List[str]) -> str:
    """构建路由选择 Prompt（只做选择题，不生成代码）"""

    # 构建候选 Agent 描述
    agent_descriptions = []
    for agent_type in candidates:
        config = AGENT_POOL[agent_type]
        agent_descriptions.append(
            f"- {agent_type}: {config['description']}"
        )

    candidates_text = "\n".join(agent_descriptions)
    data_text = ", ".join(available_data) if available_data else "无"

    return f"""你是金融分析系统的任务路由器。根据用户问题，从候选 Agent 池中选择最相关的 2-4 个 Agent。

**用户问题**：{query}
**分析目标**：{stock_name}（{stock_code}）
**可用数据**：{data_text}

**候选 Agent 池**：
{candidates_text}

规则：
1. 只输出 JSON 数组，包含选中的 agent_type 名称
2. 简单问题选 2 个，复杂问题选 3-4 个
3. 如果用户问题涉及"全面分析"，选全部

输出格式（仅 JSON 数组）：
["financial_agent", "valuation_agent"]"""


def _parse_routing_response(text: str) -> Optional[List[str]]:
    """解析 LLM 路由响应（只接受 JSON 数组）"""
    # 尝试直接解析
    try:
        result = json.loads(text.strip())
        if isinstance(result, list):
            return [str(x) for x in result]
    except json.JSONDecodeError:
        pass

    # 从 code block 提取
    json_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    matches = re.findall(json_pattern, text, re.DOTALL)
    for match in matches:
        try:
            result = json.loads(match.strip())
            if isinstance(result, list):
                return [str(x) for x in result]
        except json.JSONDecodeError:
            continue

    # 尝试找 [ ... ]
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, list):
                return [str(x) for x in result]
        except json.JSONDecodeError:
            pass

    return None


def _allocate_data(agent_registry: List[Dict[str, Any]],
                   shared_context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """为每个子 Agent 分配精准数据子集"""
    allocations = {}

    for agent in agent_registry:
        agent_id = agent["agent_id"]
        input_schema = agent.get("input_schema", [])

        data_subset = {}
        for key in input_schema:
            if key in shared_context:
                data_subset[key] = shared_context[key]
            elif key == "stock_name":
                data_subset["stock_name"] = shared_context.get("stock_name", "")
            elif key == "stock_code":
                data_subset["stock_code"] = shared_context.get("stock_code", "")

        allocations[agent_id] = data_subset

    return allocations


def _build_agent_registry(activated_types: List[str]) -> List[Dict[str, Any]]:
    """从预置池中构建 Agent 注册表"""
    registry = []
    for agent_type in activated_types:
        if agent_type in AGENT_POOL:
            config = AGENT_POOL[agent_type]
            registry.append({
                "agent_id": config["agent_id"],
                "agent_type": agent_type,
                "capability": config["capability"],
                "input_schema": config["input_schema"],
                "tools": config["tools"],
                "priority": config["priority"],
                "status": "pending",
            })
    # 按优先级排序
    registry.sort(key=lambda x: x.get("priority", 99))
    return registry


class Supervisor:
    """
    监督智能体（LangGraph 节点）

    设计模式：预置专家池 + 智能路由
    - Agent 代码全部预置在 AGENT_POOL 中（稳定、可测试）
    - Supervisor 只做选择题：哪些 Agent 需要激活
    - 轻量分类器先粗筛，LLM 再精调（节省 Token）
    """

    def __init__(self, llm: BaseChatModel, light_llm: Optional[BaseChatModel] = None):
        self.llm = llm
        self.light_llm = light_llm or llm

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph 节点入口"""
        user_query = state.get("user_query", "")
        shared_context = state.get("shared_context") or {}
        stock_code = shared_context.get("stock_code", "")
        stock_name = shared_context.get("stock_name", "")

        logger.info(f"[Supervisor] 路由决策: {user_query}")

        # ===== 第一步：轻量意图分类（关键词匹配，零成本） =====
        keyword_candidates = _lightweight_intent_classify(user_query)
        logger.info(f"[Supervisor] 关键词粗筛: {keyword_candidates}")

        # 如果关键词没命中任何 Agent，使用全量池
        if not keyword_candidates:
            keyword_candidates = set(DEFAULT_ACTIVATED)
            logger.info("[Supervisor] 关键词未命中，使用全量 Agent 池")

        # ===== 第二步：LLM 精调路由（从候选中选择） =====
        activated_types = self._llm_route(
            user_query, stock_name, stock_code,
            keyword_candidates,
            list(shared_context.keys()) if shared_context else [],
        )

        # ===== 第三步：构建 Agent 注册表 =====
        agent_registry = _build_agent_registry(activated_types)

        # ===== 第四步：精准数据分配 =====
        data_allocations = _allocate_data(agent_registry, shared_context)
        for agent in agent_registry:
            agent["data_subset"] = data_allocations.get(agent["agent_id"], {})

        logger.info(f"[Supervisor] 激活 {len(agent_registry)} 个 Agent: "
                    f"{[a['agent_type'] for a in agent_registry]}")

        return {
            "agent_registry": agent_registry,
            "current_phase": "supervisor_done",
            "messages": [{"role": "system", "content": f"Supervisor 激活了 {len(agent_registry)} 个 Agent"}],
        }

    def _llm_route(self, query: str, stock_name: str, stock_code: str,
                   candidates: Set[str], available_data: List[str]) -> List[str]:
        """LLM 路由选择"""

        routing_prompt = _build_routing_prompt(
            query, stock_name, stock_code, candidates, available_data
        )

        try:
            messages = [
                SystemMessage(content="你是任务路由器，只输出 JSON 数组。"),
                HumanMessage(content=routing_prompt),
            ]
            response = self.light_llm.invoke(messages)
            parsed = _parse_routing_response(response.content)

            if parsed:
                # 校验：只接受池中存在的 agent_type
                valid = [t for t in parsed if t in AGENT_POOL]
                if valid:
                    logger.info(f"[Supervisor] LLM 选择: {valid}")
                    return valid

        except Exception as e:
            logger.warning(f"[Supervisor] LLM 路由失败: {e}，使用关键词结果")

        # 降级：使用关键词匹配结果
        return list(candidates) if candidates else DEFAULT_ACTIVATED
