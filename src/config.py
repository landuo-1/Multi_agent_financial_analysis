"""
配置管理模块
加载环境变量，提供全局配置对象
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

# 加载 .env 文件
_project_root = Path(__file__).parent.parent
_dotenv_path = _project_root / ".env"
if _dotenv_path.exists():
    load_dotenv(_dotenv_path)


@dataclass(frozen=True)
class LLMConfig:
    """LLM 配置"""
    provider: str = "openai"
    model: str = "mimo-v2.5-pro"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    light_model: str = "mimo-v2.5"
    temperature: float = 0.1
    max_tokens: int = 4096

    @property
    def light_temperature(self) -> float:
        return 0.0


@dataclass(frozen=True)
class EmbeddingConfig:
    """Embedding 模型配置"""
    model: str = "text-embedding-3-small"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""


@dataclass(frozen=True)
class CacheConfig:
    """缓存配置"""
    cache_dir: str = "./data/cache"
    sqlite_db_path: str = "./data/cache/financial_cache.db"
    redis_url: Optional[str] = None
    cache_ttl_hours: int = 24


@dataclass(frozen=True)
class VectorStoreConfig:
    """向量库配置"""
    chroma_persist_dir: str = "./data/chroma"
    collection_name: str = "financial_reports"


@dataclass(frozen=True)
class DataSourceConfig:
    """数据源配置"""
    priority: list = field(default_factory=lambda: ["baostock", "akshare"])
    request_timeout: int = 30
    max_retries: int = 3


@dataclass(frozen=True)
class ReportConfig:
    """报告配置"""
    output_dir: str = "./reports"


@dataclass(frozen=True)
class AppConfig:
    """应用全局配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    vector_store: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    log_level: str = "INFO"
    max_debate_rounds: int = 2
    max_tool_requests: int = 2


def load_config() -> AppConfig:
    """从环境变量加载配置"""
    llm_config = LLMConfig(
        provider=os.getenv("LLM_PROVIDER", "openai"),
        model=os.getenv("LLM_MODEL", "mimo-v2.5-pro"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("LLM_API_KEY", ""),
        light_model=os.getenv("LLM_LIGHT_MODEL", "mimo-v2.5"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
    )

    embedding_config = EmbeddingConfig(
        model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        base_url=os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("EMBEDDING_API_KEY", os.getenv("LLM_API_KEY", "")),
    )

    cache_config = CacheConfig(
        cache_dir=os.getenv("CACHE_DIR", "./data/cache"),
        sqlite_db_path=os.getenv("SQLITE_DB_PATH", "./data/cache/financial_cache.db"),
        redis_url=os.getenv("REDIS_URL"),
        cache_ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "24")),
    )

    vector_store_config = VectorStoreConfig(
        chroma_persist_dir=os.getenv("CHROMA_PERSIST_DIR", "./data/chroma"),
        collection_name=os.getenv("CHROMA_COLLECTION", "financial_reports"),
    )

    data_source_priority = os.getenv("DATA_SOURCE_PRIORITY", "baostock,akshare").split(",")
    data_source_config = DataSourceConfig(
        priority=[s.strip() for s in data_source_priority],
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
    )

    report_config = ReportConfig(
        output_dir=os.getenv("REPORT_OUTPUT_DIR", "./reports"),
    )

    return AppConfig(
        llm=llm_config,
        embedding=embedding_config,
        cache=cache_config,
        vector_store=vector_store_config,
        data_source=data_source_config,
        report=report_config,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        max_debate_rounds=int(os.getenv("MAX_DEBATE_ROUNDS", "2")),
        max_tool_requests=int(os.getenv("MAX_TOOL_REQUESTS", "2")),
    )


# 全局配置单例
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置（懒加载单例）"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> AppConfig:
    """重新加载配置（用于测试）"""
    global _config
    _config = load_config()
    return _config
