"""
LLM 实例工厂

集中管理 LLM 实例的创建，供 API 后台任务和 CLI 模式共用。

设计要点：
- 主 LLM（mimo-v2.5-pro）：用于 Agent 分析、辩论、报告生成
- 轻量 LLM（mimo-v2.5）：用于实体解析、Supervisor 路由等简单任务
- 两个实例共享相同的 API Key 和 Base URL
"""

from typing import Optional
from langchain_core.language_models import BaseChatModel
from src.config import AppConfig, get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _validate_config(config: AppConfig) -> None:
    """
    校验 LLM 配置完整性

    Raises:
        ValueError: 缺少必要配置项
    """
    if not config.llm.api_key:
        raise ValueError(
            "LLM_API_KEY 未配置。请在 .env 文件中设置 LLM_API_KEY=your-api-key"
        )


def is_llm_configured(config: Optional[AppConfig] = None) -> bool:
    """
    检查 LLM 是否已正确配置（不抛异常）

    用于健康检查等场景，返回 True/False。
    """
    try:
        if config is None:
            config = get_config()
        return bool(config.llm.api_key)
    except Exception:
        return False


def create_llm(config: Optional[AppConfig] = None) -> BaseChatModel:
    """
    创建主 LLM 实例（用于分析、辩论、报告）

    Args:
        config: 应用配置，为 None 时使用全局配置

    Returns:
        ChatOpenAI 实例

    Raises:
        ValueError: API Key 未配置
    """
    if config is None:
        config = get_config()
    _validate_config(config)

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=config.llm.model,
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
    )
    logger.info(f"主 LLM 创建: {config.llm.model} (max_tokens={config.llm.max_tokens})")
    return llm


def create_light_llm(config: Optional[AppConfig] = None) -> BaseChatModel:
    """
    创建轻量 LLM 实例（用于实体解析、路由等简单任务）

    特点：
    - temperature=0.0：输出确定性高，适合结构化任务
    - max_tokens=2048：简单任务不需要长输出
    """
    if config is None:
        config = get_config()
    _validate_config(config)

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=config.llm.light_model,
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        temperature=0.0,
        max_tokens=2048,
    )
    logger.info(f"轻量 LLM 创建: {config.llm.light_model}")
    return llm
