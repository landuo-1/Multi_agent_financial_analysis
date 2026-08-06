"""
LangGraph 编排入口
定义完整的状态图，连接所有节点

架构模式：预置专家池 + 智能路由 + 动态图裁剪
- Agent 代码全部预置（稳定）
- Supervisor 按需激活子集（节省 Token）
- 子 Agent 执行时跳过未激活的
"""

import time
from typing import Any, Dict, List, Optional, Callable
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.language_models import BaseChatModel

from src.state import FinancialAnalysisState, create_initial_state
from src.agents.resolver import EntityResolver
from src.agents.context_agent import ContextAgent
from src.agents.supervisor import Supervisor, AGENT_POOL
from src.agents.financial import FinancialAgent, IndustryAgent, SentimentAgent, ValuationAgent
from src.agents.aggregator import AggregatorAgent
from src.agents.bull import BullAgent
from src.agents.bear import BearAgent
from src.agents.arbiter import ArbiterAgent
from src.agents.report import ReportAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Agent 类型 → 实例化类的映射（预置，写死）
AGENT_CLASS_MAP = {
    "financial_agent": FinancialAgent,
    "industry_agent": IndustryAgent,
    "sentiment_agent": SentimentAgent,
    "valuation_agent": ValuationAgent,
}


def _run_sub_agents(state: Dict[str, Any], llm: BaseChatModel) -> Dict[str, Any]:
    """
    执行 Supervisor 选中的子 Agent（按需激活，非全量执行）

    关键设计：
    - 只执行 agent_registry 中列出的 Agent（Supervisor 已筛选）
    - 每个 Agent 只拿到自己需要的数据子集（精准隔离）
    - 失败的 Agent 不阻塞流程，标记为 failed 继续
    """
    agent_registry = state.get("agent_registry", [])
    shared_context = state.get("shared_context", {})

    if not agent_registry:
        logger.warning("[Graph] 无子 Agent 可执行")
        return {"agent_outputs": {}, "messages": [{"role": "system", "content": "无子 Agent 可执行"}]}

    logger.info(f"[Graph] 开始执行 {len(agent_registry)} 个子 Agent")

    agent_outputs = {}

    for agent_config in agent_registry:
        agent_id = agent_config.get("agent_id", "")
        agent_type = agent_config.get("agent_type", "")

        # 从预置映射中获取 Agent 类
        agent_class = AGENT_CLASS_MAP.get(agent_type)
        if agent_class is None:
            logger.warning(f"[Graph] 未知 Agent 类型: {agent_type}，跳过")
            from src.state import AgentEnvelope
            agent_outputs[agent_id] = AgentEnvelope(
                agent_name=agent_id,
                status="failed",
                fact_sheet={},
                brief_summary=f"未知 Agent 类型: {agent_type}",
                confidence_score=0,
            ).model_dump()
            continue

        logger.info(f"[Graph] 执行子 Agent: {agent_id} (类型: {agent_type})")

        try:
            agent = agent_class(llm)

            # 精准数据注入：只给该 Agent 需要的数据
            agent_state = {
                **state,
                "shared_context": {
                    **shared_context,
                    **agent_config.get("data_subset", {}),
                },
            }

            result = agent.execute(agent_state)
            agent_outputs[agent_id] = result

            status = result.get("status", "unknown")
            confidence = result.get("confidence_score", 0)
            logger.info(f"[Graph] {agent_id} 完成, 状态: {status}, 置信度: {confidence}")

        except Exception as e:
            logger.error(f"[Graph] {agent_id} 执行异常: {e}")
            from src.state import AgentEnvelope
            agent_outputs[agent_id] = AgentEnvelope(
                agent_name=agent_id,
                status="failed",
                fact_sheet={},
                brief_summary=f"执行异常: {str(e)}",
                confidence_score=0,
            ).model_dump()

    logger.info(f"[Graph] 子 Agent 执行完成: {len(agent_outputs)}/{len(agent_registry)} 成功")
    return {
        "agent_outputs": agent_outputs,
        "current_phase": "sub_agents_done",
        "messages": [{"role": "system", "content": f"子 Agent 执行完成: {len(agent_outputs)} 个"}],
    }


def _run_debate(state: Dict[str, Any], llm: BaseChatModel,
                max_rounds: int = 5) -> Dict[str, Any]:
    """
    执行对抗辩论
    置信度驱动的动态终止
    """
    logger.info("[Graph] 开始对抗辩论")

    bull = BullAgent(llm)
    bear = BearAgent(llm)

    debate_history = state.get("debate_history", [])
    round_num = 1

    bull_confidence = 50
    bear_confidence = 50

    while round_num <= max_rounds:
        logger.info(f"[Graph] 辩论第 {round_num} 轮")

        # Bull 先发言
        bear_last_arg = None
        for arg in reversed(debate_history):
            if arg.get("role") == "bear":
                bear_last_arg = arg.get("argument", "")
                break

        bull_arg = bull(state, round_num=round_num, bear_argument=bear_last_arg)
        debate_history.append(bull_arg)
        bull_confidence = bull_arg.get("confidence", 50)

        # Bear 回应
        bull_last_arg = bull_arg.get("argument", "")
        bear_arg = bear(state, round_num=round_num, bull_argument=bull_last_arg)
        debate_history.append(bear_arg)
        bear_confidence = bear_arg.get("confidence", 50)

        # 检查终止条件
        diff = abs(bull_confidence - bear_confidence)

        # 条件 A：达成共识
        if diff < 15:
            logger.info(f"[Graph] 辩论达成共识 (差值: {diff})")
            break

        # 条件 B：一方溃败
        if bull_confidence < 20:
            logger.info(f"[Graph] 多方溃败 (置信度: {bull_confidence})")
            break
        if bear_confidence < 20:
            logger.info(f"[Graph] 空方溃败 (置信度: {bear_confidence})")
            break

        # 条件 C：僵局
        if round_num >= 4 and diff > 40:
            logger.info(f"[Graph] 辩论陷入僵局 (轮次: {round_num}, 差值: {diff})")
            break

        round_num += 1

    logger.info(f"[Graph] 辩论结束，共 {round_num} 轮, "
                f"多方: {bull_confidence}, 空方: {bear_confidence}")

    return {
        "debate_history": debate_history,
        "current_phase": "debate_done",
        "messages": [{"role": "system", "content": f"辩论结束: {round_num} 轮, 多方{bull_confidence} vs 空方{bear_confidence}"}],
    }


def build_graph(llm: BaseChatModel, light_llm: Optional[BaseChatModel] = None,
                max_debate_rounds: int = 5, report_output_dir: str = "./reports") -> StateGraph:
    """
    构建 LangGraph 状态图

    节点：
    - entity_resolver: 实体解析（轻量 LLM）
    - context_init: 上下文初始化（数据拉取，无 LLM）
    - supervisor: 智能路由（轻量 LLM，从预置池选择激活哪些 Agent）
    - sub_agents: 执行选中的子 Agent（主 LLM）
    - aggregator: 汇聚结果 + 极性判断（规则引擎，无 LLM）
    - debate: 多空辩论（主 LLM）
    - arbiter: 辩论仲裁（主 LLM）
    - report: 报告生成（主 LLM）
    """
    _llm = llm
    _light_llm = light_llm or llm
    _max_rounds = max_debate_rounds
    _report_dir = report_output_dir

    # 定义节点函数
    def entity_resolver_node(state: Dict[str, Any]) -> Dict[str, Any]:
        resolver = EntityResolver(_light_llm)
        return resolver(state)

    def context_init_node(state: Dict[str, Any]) -> Dict[str, Any]:
        ctx = ContextAgent()
        return ctx(state)

    def supervisor_node(state: Dict[str, Any]) -> Dict[str, Any]:
        sup = Supervisor(llm=_llm, light_llm=_light_llm)
        return sup(state)

    def sub_agents_node(state: Dict[str, Any]) -> Dict[str, Any]:
        return _run_sub_agents(state, _llm)

    def aggregator_node(state: Dict[str, Any]) -> Dict[str, Any]:
        agg = AggregatorAgent(_llm)
        return agg(state)

    def debate_node(state: Dict[str, Any]) -> Dict[str, Any]:
        return _run_debate(state, _llm, _max_rounds)

    def arbiter_node(state: Dict[str, Any]) -> Dict[str, Any]:
        arb = ArbiterAgent(_llm)
        return arb(state)

    def report_node(state: Dict[str, Any]) -> Dict[str, Any]:
        rpt = ReportAgent(_llm, _report_dir)
        return rpt(state)

    # 条件路由函数
    def route_after_resolver(state: Dict[str, Any]) -> str:
        """实体解析后的路由"""
        resolved = state.get("resolved_entity", {})
        action = resolved.get("action", "not_found")

        if action == "auto_confirm":
            return "context_init"
        elif action == "need_confirm":
            logger.info("[Graph] 需要用户确认，自动选择第一个候选")
            return "context_init"
        else:
            return END

    # 构建状态图
    workflow = StateGraph(FinancialAnalysisState)

    # 添加节点
    workflow.add_node("entity_resolver", entity_resolver_node)
    workflow.add_node("context_init", context_init_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("sub_agents", sub_agents_node)
    workflow.add_node("aggregator", aggregator_node)
    workflow.add_node("debate", debate_node)
    workflow.add_node("arbiter", arbiter_node)
    workflow.add_node("report", report_node)

    # 设置入口
    workflow.set_entry_point("entity_resolver")

    # 添加边
    workflow.add_conditional_edges(
        "entity_resolver",
        route_after_resolver,
        {
            "context_init": "context_init",
            END: END,
        },
    )

    workflow.add_edge("context_init", "supervisor")
    workflow.add_edge("supervisor", "sub_agents")
    workflow.add_edge("sub_agents", "aggregator")
    workflow.add_edge("aggregator", "debate")
    workflow.add_edge("debate", "arbiter")
    workflow.add_edge("arbiter", "report")
    workflow.add_edge("report", END)

    return workflow


def compile_graph(llm: BaseChatModel, light_llm: Optional[BaseChatModel] = None,
                  max_debate_rounds: int = 5, report_output_dir: str = "./reports",
                  use_checkpointer: bool = False) -> Callable:
    """编译 LangGraph 图，返回可调用的执行函数"""
    workflow = build_graph(
        llm=llm,
        light_llm=light_llm,
        max_debate_rounds=max_debate_rounds,
        report_output_dir=report_output_dir,
    )

    if use_checkpointer:
        checkpointer = MemorySaver()
        app = workflow.compile(checkpointer=checkpointer)
    else:
        app = workflow.compile()

    logger.info("[Graph] LangGraph 编译完成")
    return app


async def run_analysis_async(query: str, llm: BaseChatModel,
                             light_llm: Optional[BaseChatModel] = None,
                             max_debate_rounds: int = 5,
                             report_output_dir: str = "./reports") -> Dict[str, Any]:
    """异步执行完整分析流程"""
    app = compile_graph(
        llm=llm,
        light_llm=light_llm,
        max_debate_rounds=max_debate_rounds,
        report_output_dir=report_output_dir,
    )

    initial_state = create_initial_state(query)

    logger.info(f"[Graph] 开始分析: {query}")
    start_time = time.time()

    final_state = None
    async for event in app.astream(initial_state):
        for node_name, node_output in event.items():
            logger.info(f"[Graph] 节点完成: {node_name}")
            final_state = node_output

    elapsed = time.time() - start_time
    logger.info(f"[Graph] 分析完成，耗时: {elapsed:.1f} 秒")

    return final_state or {}


def run_analysis(query: str, llm: BaseChatModel,
                 light_llm: Optional[BaseChatModel] = None,
                 max_debate_rounds: int = 5,
                 report_output_dir: str = "./reports") -> Dict[str, Any]:
    """同步执行完整分析流程"""
    app = compile_graph(
        llm=llm,
        light_llm=light_llm,
        max_debate_rounds=max_debate_rounds,
        report_output_dir=report_output_dir,
    )

    initial_state = create_initial_state(query)

    logger.info(f"[Graph] 开始分析: {query}")
    start_time = time.time()

    final_state = app.invoke(initial_state)

    elapsed = time.time() - start_time
    logger.info(f"[Graph] 分析完成，耗时: {elapsed:.1f} 秒")

    return final_state
