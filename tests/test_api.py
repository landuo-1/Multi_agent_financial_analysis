"""
FastAPI API 测试

覆盖范围：
- 健康检查端点
- 实体解析端点
- 分析任务端点（提交、查询、SSE）
- 报告下载端点（Markdown、HTML、Excel）
- 任务列表端点
- 任务管理器单元测试
- 错误处理和边界条件
"""

import pytest
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from src.api.app import create_app
from src.api.schemas import TaskStatus, ProgressEvent, TaskListResponse
from src.api.tasks import TaskManager, TaskRecord


@pytest.fixture
def client():
    """创建测试客户端"""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def task_manager():
    """创建独立的任务管理器（每次测试隔离）"""
    return TaskManager()


# ============================================================
# 健康检查
# ============================================================

class TestHealthEndpoint:

    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "llm_configured" in data
        assert "cache_stats" in data

    def test_health_has_version(self, client):
        data = client.get("/api/health").json()
        assert data["version"] == "1.0.0"


# ============================================================
# 根端点
# ============================================================

class TestRootEndpoint:

    def test_root_returns_system_info(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert data["version"] == "1.0.0"
        assert "docs" in data
        assert "health" in data


# ============================================================
# 实体解析
# ============================================================

class TestResolveEndpoint:

    def test_resolve_common_alias(self, client):
        """别名表精确匹配（默认 use_llm=true，测试环境无 LLM 自动降级）"""
        resp = client.post("/api/resolve", json={"query": "分析茅台"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_code"] == "600519"
        assert data["stock_name"] == "贵州茅台"
        assert data["confidence"] >= 0.9
        assert data["action"] in ("auto_confirm", "need_confirm")

    def test_resolve_by_code(self, client):
        """直接股票代码匹配"""
        resp = client.post("/api/resolve", json={"query": "600519"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_code"] == "600519"

    def test_resolve_full_name(self, client):
        """全称匹配"""
        resp = client.post("/api/resolve", json={"query": "科大讯飞"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_code"] == "002230"
        assert data["stock_name"] == "科大讯飞"

    def test_resolve_not_found(self, client):
        """无法识别的输入"""
        resp = client.post("/api/resolve", json={"query": "xyz_not_exist_12345"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "not_found"
        assert data["stock_code"] == ""

    def test_resolve_empty_query_returns_422(self, client):
        """空查询返回校验错误"""
        resp = client.post("/api/resolve", json={"query": ""})
        assert resp.status_code == 422

    def test_resolve_response_has_candidates(self, client):
        """响应包含候选列表"""
        resp = client.post("/api/resolve", json={"query": "茅台"})
        data = resp.json()
        assert "candidates" in data
        assert isinstance(data["candidates"], list)

    def test_resolve_without_llm(self, client):
        """显式关闭 LLM，纯规则匹配"""
        resp = client.post("/api/resolve", json={"query": "茅台", "use_llm": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_code"] == "600519"
        assert data["stock_name"] == "贵州茅台"

    def test_resolve_with_llm_graceful_degradation(self, client):
        """开启 LLM 但测试环境无 LLM 时应优雅降级"""
        resp = client.post("/api/resolve", json={"query": "茅台", "use_llm": True})
        assert resp.status_code == 200
        data = resp.json()
        # 降级后仍能通过别名表匹配
        assert data["stock_code"] == "600519"

    def test_resolve_code_with_llm_flag(self, client):
        """带 use_llm 标志的代码匹配"""
        resp = client.post("/api/resolve", json={"query": "002230", "use_llm": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_code"] == "002230"


# ============================================================
# 分析任务
# ============================================================

class TestAnalyzeEndpoint:

    def test_submit_empty_query_returns_422(self, client):
        """空查询返回校验错误"""
        resp = client.post("/api/analyze", json={"query": ""})
        assert resp.status_code == 422

    def test_get_nonexistent_task_returns_404(self, client):
        """查询不存在的任务返回 404"""
        resp = client.get("/api/analyze/nonexistent_task")
        assert resp.status_code == 404

    def test_sse_nonexistent_task_returns_404(self, client):
        """订阅不存在的任务 SSE 返回 404"""
        resp = client.get("/api/analyze/nonexistent_task/stream")
        assert resp.status_code == 404

    def test_report_nonexistent_task_returns_404(self, client):
        """下载不存在任务的报告返回 404"""
        resp = client.get("/api/reports/nonexistent_task")
        assert resp.status_code == 404

    def test_html_nonexistent_task_returns_404(self, client):
        """预览不存在任务的 HTML 返回 404"""
        resp = client.get("/api/reports/nonexistent_task/html")
        assert resp.status_code == 404

    def test_excel_nonexistent_task_returns_404(self, client):
        """下载不存在任务的 Excel 返回 404"""
        resp = client.get("/api/reports/nonexistent_task/excel")
        assert resp.status_code == 404

    def test_submit_valid_query_returns_task_id(self, client, monkeypatch):
        """有效查询返回 task_id（mock 后台任务避免实际执行）"""
        # Mock 后台任务，避免实际执行分析
        async def mock_run(*args, **kwargs):
            pass
        from src.api import routes
        monkeypatch.setattr(routes, "_run_analysis_task", mock_run)

        resp = client.post("/api/analyze", json={"query": "茅台"})
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "running"
        assert "message" in data

    def test_get_pending_task_returns_running_status(self, client, monkeypatch):
        """查询刚提交的任务返回 running 状态"""
        async def mock_run(*args, **kwargs):
            pass
        from src.api import routes
        monkeypatch.setattr(routes, "_run_analysis_task", mock_run)

        # 提交任务
        resp = client.post("/api/analyze", json={"query": "茅台"})
        task_id = resp.json()["task_id"]

        # 立即查询
        resp = client.get(f"/api/analyze/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("running", "completed", "failed")


# ============================================================
# 任务列表
# ============================================================

class TestTasksEndpoint:

    def test_list_tasks_returns_array(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert isinstance(data["tasks"], list)

    def test_list_tasks_after_submit(self, client, monkeypatch):
        """提交任务后列表中应该有记录"""
        async def mock_run(*args, **kwargs):
            pass
        from src.api import routes
        monkeypatch.setattr(routes, "_run_analysis_task", mock_run)

        client.post("/api/analyze", json={"query": "茅台"})
        resp = client.get("/api/tasks")
        data = resp.json()
        assert len(data["tasks"]) >= 1


# ============================================================
# TaskRecord 单元测试
# ============================================================

class TestTaskRecord:

    def test_initial_state(self):
        task = TaskRecord("task_001", "test query")
        assert task.task_id == "task_001"
        assert task.query == "test query"
        assert task.status == TaskStatus.PENDING
        assert task.progress_pct == 0
        assert task.result is None
        assert task.error is None
        assert task.end_time is None

    def test_elapsed_is_positive(self):
        task = TaskRecord("task_001", "test")
        assert task.elapsed >= 0

    def test_set_progress(self):
        task = TaskRecord("task_001", "test")
        task.set_progress("phase1", 50, "processing")
        assert task.current_phase == "phase1"
        assert task.progress_pct == 50
        assert task.message == "processing"

    def test_set_completed(self):
        task = TaskRecord("task_001", "test")
        task.set_completed({"result": "ok"})
        assert task.status == TaskStatus.COMPLETED
        assert task.result == {"result": "ok"}
        assert task.end_time is not None
        assert task.progress_pct == 100
        assert task.elapsed >= 0

    def test_set_failed(self):
        task = TaskRecord("task_001", "test")
        task.set_failed("error message")
        assert task.status == TaskStatus.FAILED
        assert task.error == "error message"
        assert task.end_time is not None

    def test_to_dict(self):
        task = TaskRecord("task_001", "test query")
        d = task.to_dict()
        assert d["task_id"] == "task_001"
        assert d["query"] == "test query"
        assert d["status"] == "pending"
        assert "elapsed" in d

    def test_repr(self):
        task = TaskRecord("task_001", "test")
        r = repr(task)
        assert "task_001" in r
        assert "test" in r

    @pytest.mark.asyncio
    async def test_wait_times_out(self):
        """未完成的任务等待应超时"""
        task = TaskRecord("task_001", "test")
        result = await task.wait(timeout=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_completes(self):
        """已完成的任务等待应立即返回"""
        task = TaskRecord("task_001", "test")
        task.set_completed({"done": True})
        result = await task.wait(timeout=1)
        assert result is True


# ============================================================
# TaskManager 单元测试
# ============================================================

class TestTaskManager:

    def test_create_task(self, task_manager):
        task = task_manager.create_task("test")
        assert task.task_id.startswith("task_")
        assert task.query == "test"
        assert task.status == TaskStatus.PENDING

    def test_get_task(self, task_manager):
        task = task_manager.create_task("test")
        retrieved = task_manager.get_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id

    def test_get_nonexistent_task(self, task_manager):
        assert task_manager.get_task("nonexistent") is None

    def test_list_tasks(self, task_manager):
        task_manager.create_task("test1")
        task_manager.create_task("test2")
        tasks = task_manager.list_tasks()
        assert len(tasks) >= 2

    def test_cleanup_expired(self, task_manager):
        """创建一个超龄任务并清理"""
        task = task_manager.create_task("old task")
        # 手动将 start_time 设为 2 小时前
        task.start_time -= 7200
        cleaned = task_manager.cleanup_expired(max_age=3600)
        assert cleaned == 1
        assert task_manager.get_task(task.task_id) is None

    def test_cleanup_preserves_recent(self, task_manager):
        """近期任务不应被清理"""
        task_manager.create_task("recent task")
        cleaned = task_manager.cleanup_expired(max_age=3600)
        assert cleaned == 0
        assert len(task_manager.list_tasks()) >= 1

    def test_get_stats(self, task_manager):
        task_manager.create_task("test1")
        task_manager.create_task("test2")
        stats = task_manager.get_stats()
        assert stats["total"] >= 2
        assert "pending" in stats
        assert "running" in stats
        assert "completed" in stats
        assert "failed" in stats


# ============================================================
# Pydantic Schema 测试
# ============================================================

class TestProgressEvent:

    def test_progress_event_creation(self):
        event = ProgressEvent(
            status="running",
            phase="数据采集",
            progress=30,
            message="正在拉取财务数据",
            elapsed=5.0,
        )
        assert event.status == "running"
        assert event.progress == 30

    def test_progress_event_json(self):
        event = ProgressEvent(status="completed", progress=100)
        json_str = event.model_dump_json()
        assert "completed" in json_str
        assert "100" in json_str


class TestTaskListResponse:

    def test_empty_list(self):
        resp = TaskListResponse(tasks=[])
        assert len(resp.tasks) == 0

    def test_with_items(self):
        from src.api.schemas import TaskListItem
        resp = TaskListResponse(tasks=[
            TaskListItem(task_id="t1", query="test", status=TaskStatus.RUNNING, elapsed=1.0),
        ])
        assert len(resp.tasks) == 1


# ============================================================
# 错误处理
# ============================================================

class TestErrorHandling:

    def test_422_returns_structured_error(self, client):
        """校验错误应返回结构化的错误信息"""
        resp = client.post("/api/resolve", json={"query": ""})
        assert resp.status_code == 422
        data = resp.json()
        # 应包含 error 和 detail 字段
        assert "error" in data or "detail" in data

    def test_404_returns_detail(self, client):
        """404 应返回具体原因"""
        resp = client.get("/api/analyze/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
