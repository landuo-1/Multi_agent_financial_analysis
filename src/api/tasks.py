"""
异步任务管理器

管理后台分析任务的生命周期：创建 → 执行 → 完成/失败。

设计要点：
- 内存存储，适合单实例部署（进程重启后任务丢失）
- asyncio.Event 用于异步等待任务完成
- TaskRecord 自动记录耗时，支持进度上报
"""

import asyncio
import time
import uuid
from typing import Any, Dict, Optional
from src.api.schemas import TaskStatus
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TaskRecord:
    """
    单个任务的运行时记录

    生命周期：
        PENDING → RUNNING → COMPLETED / FAILED

    Usage:
        task = TaskRecord("task_abc123", "分析贵州茅台")
        task.set_progress("数据采集", 30, "正在拉取财务数据...")
        task.set_completed({"final_report": "..."})
    """

    def __init__(self, task_id: str, query: str):
        self.task_id: str = task_id
        self.query: str = query
        self.status: TaskStatus = TaskStatus.PENDING
        self.current_phase: str = ""
        self.progress_pct: int = 0
        self.message: str = ""
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self._event: Optional[asyncio.Event] = None

    def _ensure_event(self) -> asyncio.Event:
        """
        惰性创建 asyncio.Event。

        原因：Event 必须在运行中的事件循环内创建，否则在 Python 3.10+ 会报错。
        TaskRecord 可能在非异步上下文中创建（如 CLI 模式），因此延迟到需要时再创建。
        """
        if self._event is None:
            self._event = asyncio.Event()
        return self._event

    @property
    def elapsed(self) -> float:
        """已耗时（秒），任务未结束则返回实时耗时"""
        end = self.end_time or time.time()
        return round(end - self.start_time, 2)

    def set_progress(self, phase: str, pct: int, message: str = ""):
        """更新执行进度"""
        self.current_phase = phase
        self.progress_pct = pct
        self.message = message

    def set_completed(self, result: Dict[str, Any]):
        """标记任务完成"""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.end_time = time.time()
        self.progress_pct = 100
        self._ensure_event().set()

    def set_failed(self, error: str):
        """标记任务失败"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.end_time = time.time()
        self._ensure_event().set()

    async def wait(self, timeout: float = 540) -> bool:
        """
        异步等待任务完成

        Returns:
            True: 任务在超时前完成
            False: 超时
        """
        try:
            await asyncio.wait_for(self._ensure_event().wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于 API 响应）"""
        return {
            "task_id": self.task_id,
            "query": self.query,
            "status": self.status.value,
            "phase": self.current_phase,
            "progress": self.progress_pct,
            "message": self.message,
            "elapsed": self.elapsed,
            "error": self.error,
        }

    def __repr__(self) -> str:
        return (
            f"TaskRecord(id={self.task_id!r}, query={self.query!r}, "
            f"status={self.status.value!r}, elapsed={self.elapsed}s)"
        )


class TaskManager:
    """
    任务管理器

    管理所有分析任务的创建、查询和清理。
    线程安全性：当前为单进程内存存储，不涉及多线程竞争。
    如需多进程部署，应替换为 Redis 或数据库存储。
    """

    def __init__(self):
        self._tasks: Dict[str, TaskRecord] = {}

    def create_task(self, query: str) -> TaskRecord:
        """创建新任务，返回 TaskRecord"""
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = TaskRecord(task_id, query)
        self._tasks[task_id] = task
        logger.info(f"任务创建: {task}")
        return task

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """根据 task_id 获取任务，不存在返回 None"""
        return self._tasks.get(task_id)

    def list_tasks(self) -> Dict[str, TaskRecord]:
        """返回所有任务的快照"""
        return self._tasks.copy()

    def cleanup_expired(self, max_age: float = 3600) -> int:
        """
        清理超时任务（默认 1 小时）

        Returns:
            清理的任务数量
        """
        now = time.time()
        expired = [
            tid for tid, task in self._tasks.items()
            if now - task.start_time > max_age
        ]
        for tid in expired:
            del self._tasks[tid]
        if expired:
            logger.info(f"清理了 {len(expired)} 个过期任务")
        return len(expired)

    def get_stats(self) -> Dict[str, Any]:
        """获取任务统计信息"""
        tasks = list(self._tasks.values())
        return {
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t.status == TaskStatus.PENDING),
            "running": sum(1 for t in tasks if t.status == TaskStatus.RUNNING),
            "completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in tasks if t.status == TaskStatus.FAILED),
        }


# ============================================================
# 全局任务管理器单例
# ============================================================

_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取全局任务管理器（懒加载单例）"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
