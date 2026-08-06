"""
日志配置模块

格式：时间 - 模块名 - 级别 - 消息
颜色：API 日志白色，功能模块日志青色，任务日志黄色

用法：
    from src.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("消息内容")
"""

import logging
import os
import time
from logging.handlers import RotatingFileHandler
from typing import Optional

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init()
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False

_configured = False

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 需要抑制的第三方库
SUPPRESSED_LOGGERS = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "urllib3": logging.WARNING,
    "baostock": logging.WARNING,
    "akshare": logging.WARNING,
    "chromadb": logging.WARNING,
    "openai": logging.WARNING,
    "langsmith": logging.WARNING,
    "langchain": logging.WARNING,
    "langchain_core": logging.WARNING,
}


class ColoredFormatter(logging.Formatter):
    """
    彩色日志格式化器

    颜色规则：
    - api 模块 → 白色（默认）
    - task 模块 → 黄色
    - 其他模块 → 青色
    - WARNING → 黄色
    - ERROR → 红色
    """

    def format(self, record):
        time_str = self.formatTime(record, LOG_DATE_FORMAT)
        module = record.name
        msg = record.getMessage()

        # 选择颜色
        if HAS_COLOR:
            if record.levelno >= logging.ERROR:
                color = Fore.RED
            elif record.levelno >= logging.WARNING:
                color = Fore.YELLOW
            elif module == "api":
                color = Fore.WHITE
            elif module == "task":
                color = Fore.YELLOW
            else:
                color = Fore.CYAN

            reset = Style.RESET_ALL
            return f"{color}{time_str} - {module} - {record.levelname} - {msg}{reset}"
        else:
            return f"{time_str} - {module} - {record.levelname} - {msg}"


class FileFormatter(logging.Formatter):
    """文件日志格式化器（纯文本）"""

    def format(self, record):
        time_str = self.formatTime(record, LOG_DATE_FORMAT)
        msg = record.getMessage()
        return f"{time_str} - {record.name} - {record.levelname} - {msg}"


def setup_logger(level: Optional[str] = None) -> logging.Logger:
    """配置全局日志系统"""
    global _configured

    if _configured:
        return logging.getLogger("financial")

    log_level = level or os.getenv("LOG_LEVEL", "INFO")
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.handlers.clear()

    # 控制台 Handler（彩色）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)

    # 文件 Handler
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(FileFormatter())
        root_logger.addHandler(file_handler)
    except Exception as e:
        root_logger.warning(f"日志文件创建失败: {e}")

    # 抑制第三方库
    for name, suppress_level in SUPPRESSED_LOGGERS.items():
        logging.getLogger(name).setLevel(suppress_level)

    # Uvicorn 日志统一
    for name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True

    _configured = True
    logger = logging.getLogger("financial")
    logger.info(f"[System] 日志系统初始化完成 | 级别: {log_level}")

    return logger


def get_logger(name: str = "financial") -> logging.Logger:
    """获取 logger"""
    if not _configured:
        setup_logger()
    return logging.getLogger(name)


class TaskTimer:
    """
    任务级计时器

    用法：
        timer = TaskTimer("task_abc123")
        timer.phase("初始化")
        timer.log("正在创建 LLM...")
        timer.done(True)
    """

    def __init__(self, task_id: str):
        self.task_id = task_id[:8]
        self.logger = get_logger("task")
        self.start_time = time.time()
        self.phase_start = time.time()
        self.phases = []

    def phase(self, name: str):
        elapsed = time.time() - self.phase_start
        if self.phases:
            self.phases[-1]["duration"] = round(elapsed, 1)
        self.phase_start = time.time()
        self.phases.append({"name": name, "duration": 0})
        self.logger.info(f"[{self.task_id}] ▶ {name}")

    def log(self, msg: str):
        self.logger.info(f"[{self.task_id}] {msg}")

    def warn(self, msg: str):
        self.logger.warning(f"[{self.task_id}] ⚠ {msg}")

    def error(self, msg: str):
        self.logger.error(f"[{self.task_id}] ✗ {msg}")

    def done(self, success: bool = True):
        elapsed = time.time() - self.phase_start
        if self.phases:
            self.phases[-1]["duration"] = round(elapsed, 1)

        total = round(time.time() - self.start_time, 1)
        icon = "✓" if success else "✗"

        self.logger.info(f"[{self.task_id}] {icon} 完成 | 总耗时: {total}s")
        for p in self.phases:
            bar = "█" * min(int(p["duration"] / 2), 30)
            self.logger.info(f"[{self.task_id}]   {p['name']:20s} {p['duration']:6.1f}s {bar}")


def log_api_request(method: str, path: str, status_code: int, duration_ms: float = 0):
    """API 请求日志"""
    logger = get_logger("api")
    logger.info(f"[API] {method} {path} → {status_code} ({duration_ms:.0f}ms)")


def log_task_event(task_id: str, event: str, detail: str = ""):
    """任务事件日志"""
    logger = get_logger("task")
    msg = f"[{task_id[:8]}] {event}"
    if detail:
        msg += f" | {detail}"
    logger.info(msg)


def log_agent_event(agent_name: str, event: str, detail: str = ""):
    """Agent 事件日志"""
    logger = get_logger(f"agents.{agent_name}")
    msg = f"[{agent_name}] {event}"
    if detail:
        msg += f" | {detail}"
    logger.info(msg)


def log_data_source(source: str, action: str, detail: str = ""):
    """数据源日志"""
    logger = get_logger(f"tools.{source}")
    msg = f"[{source}] {action}"
    if detail:
        msg += f" | {detail}"
    logger.info(msg)
