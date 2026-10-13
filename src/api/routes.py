"""
FastAPI 路由定义

提供以下端点：
- POST   /api/analyze              提交分析任务（异步）
- GET    /api/analyze/{task_id}     获取分析结果
- GET    /api/analyze/{task_id}/stream  SSE 流式进度
- GET    /api/reports/{task_id}     下载 Markdown 报告
- GET    /api/reports/{task_id}/html    在线预览 HTML 报告
- GET    /api/reports/{task_id}/excel   下载 Excel 数据底稿
- POST   /api/resolve               实体解析（支持 LLM 增强，可识别错别字）
- GET    /api/health                健康检查
- GET    /api/tasks                 列出所有任务
"""

import asyncio
import json
import os
import time

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse

from src.api.schemas import (
    AnalyzeRequest, AnalyzeResponse, AnalyzeResult,
    ResolveRequest, ResolveResponse, ResolveCandidate,
    HealthResponse, AgentOutputSummary, DebateSummary,
    TaskStatus, TaskListItem, TaskListResponse, ProgressEvent,
)
from src.api.tasks import get_task_manager
from src.api.llm_factory import create_llm, create_light_llm, is_llm_configured
from src.config import get_config
from src.utils.logger import get_logger, TaskTimer

logger = get_logger()

router = APIRouter(prefix="/api", tags=["analysis"])


# ============================================================
# 辅助函数
# ============================================================

def _task_or_404(task_id: str):
    """获取任务，不存在则抛 404"""
    tm = get_task_manager()
    task = tm.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return task


def _completed_task_or_404(task_id: str):
    """获取已完成的任务，未完成或不存在则抛 404"""
    task = _task_or_404(task_id)
    if task.status != TaskStatus.COMPLETED or task.result is None:
        raise HTTPException(status_code=404, detail="任务未完成或结果不可用")
    return task


# ============================================================
# 健康检查
# ============================================================

@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health_check():
    """
    检查 API 服务状态、LLM 配置、缓存统计。
    前端可用此端点判断后端是否就绪。
    """
    config = get_config()
    llm_ok = is_llm_configured(config)

    cache_stats = {"status": "unavailable"}
    try:
        from src.cache.sqlite_cache import get_cache
        cache_stats = get_cache().get_stats()
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        version="1.0.0",
        llm_configured=llm_ok,
        cache_stats=cache_stats,
    )


# ============================================================
# 实体解析
# ============================================================

# 模块级轻量 LLM 缓存（避免每次请求都创建实例）
_resolve_llm = None


def _get_resolve_llm():
    """获取实体解析用的轻量 LLM（惰性创建，单例缓存）"""
    global _resolve_llm
    if _resolve_llm is None:
        if not is_llm_configured():
            return None
        try:
            _resolve_llm = create_light_llm()
        except Exception as e:
            logger.warning(f"[Resolve] 创建轻量 LLM 失败: {e}")
            _resolve_llm = None
    return _resolve_llm


@router.post("/resolve", response_model=ResolveResponse, summary="实体解析")
async def resolve_entity(req: ResolveRequest):
    """
    从用户输入中提取公司名称或股票代码，匹配到唯一的 A 股公司。

    默认使用 LLM 辅助提取，可识别错别字和自然语言描述。
    设置 use_llm=false 可关闭 LLM，仅使用别名表 + AKShare 搜索（更快但不支持错别字）。
    """
    from src.agents.resolver import resolve_entity as do_resolve

    # 根据 use_llm 参数决定是否使用 LLM
    llm = _get_resolve_llm() if req.use_llm else None

    # 如果用户要求 LLM 但 LLM 不可用，降级到无 LLM 模式
    if req.use_llm and llm is None:
        logger.info("[Resolve] LLM 不可用，降级到纯规则匹配")

    result = do_resolve(req.query, llm=llm)

    candidates = [
        ResolveCandidate(
            stock_code=c["stock_code"],
            stock_name=c["stock_name"],
            confidence=c["confidence"],
            source=c.get("source", ""),
        )
        for c in result.get("candidates", [])
    ]

    return ResolveResponse(
        stock_code=result.get("stock_code", ""),
        stock_name=result.get("stock_name", ""),
        confidence=result.get("confidence", 0),
        action=result.get("action", "not_found"),
        message=result.get("message", ""),
        candidates=candidates,
    )


# ============================================================
# 分析任务：提交
# ============================================================

@router.post("/analyze", response_model=AnalyzeResponse, summary="提交分析任务")
async def submit_analysis(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    提交一个异步分析任务。

    立即返回 task_id，前端通过 /api/analyze/{task_id}/stream 轮询进度，
    或通过 /api/analyze/{task_id} 获取最终结果。
    """
    tm = get_task_manager()

    # 提交前清理过期任务（避免内存泄漏）
    tm.cleanup_expired()

    task = tm.create_task(req.query)
    task.status = TaskStatus.RUNNING
    task.set_progress("queued", 5, "任务已排队")

    background_tasks.add_task(
        _run_analysis_task,
        task.task_id,
        req.query,
        req.max_debate_rounds,
        req.output_dir,
    )

    return AnalyzeResponse(
        task_id=task.task_id,
        status=TaskStatus.RUNNING,
        message=f"分析任务已提交: {req.query}",
    )


async def _run_analysis_task(
    task_id: str,
    query: str,
    max_debate_rounds: int,
    output_dir: str = None,
):
    """
    后台执行分析任务的完整流程

    流程：创建 LLM → 编译图 → 执行分析 → 保存结果
    超时控制：540 秒（9 分钟）
    """
    tm = get_task_manager()
    task = tm.get_task(task_id)
    if task is None:
        return

    timer = TaskTimer(task_id)
    TASK_TIMEOUT = 540

    try:
        timer.log(f"开始执行: {query}")
        timer.phase("初始化")

        config = get_config()
        report_dir = output_dir or config.report.output_dir
        os.makedirs(report_dir, exist_ok=True)

        # 创建 LLM 实例
        llm = create_llm(config)
        light_llm = create_light_llm(config)

        # 编译 LangGraph 图
        timer.phase("编译图")
        from src.graph import compile_graph
        app = compile_graph(
            llm=llm,
            light_llm=light_llm,
            max_debate_rounds=max_debate_rounds,
            report_output_dir=report_dir,
        )

        # 执行分析
        timer.phase("执行分析图")
        from src.state import create_initial_state
        import uuid as _uuid
        initial_state = create_initial_state(query)
        config = {"configurable": {"thread_id": _uuid.uuid4().hex[:12]}}

        loop = asyncio.get_event_loop()
        final_state = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: app.invoke(initial_state, config=config)),
            timeout=TASK_TIMEOUT,
        )

        # 检查结果
        if final_state is None:
            timer.error("分析未返回结果")
            task.set_failed("分析未返回结果")
            timer.done(False)
            return

        # 检查实体解析是否成功
        resolved = final_state.get("resolved_entity", {})
        if resolved and resolved.get("action") == "not_found":
            msg = resolved.get("message", "未找到匹配的公司")
            timer.error(msg)
            task.set_failed(msg)
            timer.done(False)
            return

        # 成功
        timer.phase("完成")
        task.set_completed(final_state)
        timer.done(True)

    except asyncio.TimeoutError:
        timer.error(f"超时 ({TASK_TIMEOUT}s)")
        task.set_failed(f"分析超时（超过 {TASK_TIMEOUT} 秒）")
        timer.done(False)
    except ValueError as e:
        # LLM 配置错误等
        timer.error(f"配置错误: {e}")
        task.set_failed(str(e))
        timer.done(False)
    except Exception as e:
        timer.error(f"异常: {e}")
        logger.error(f"[{task_id}] 分析异常", exc_info=True)
        task.set_failed(str(e))
        timer.done(False)


# ============================================================
# 分析任务：SSE 流式进度
# ============================================================

@router.get("/analyze/{task_id}/stream", summary="SSE 流式进度")
async def stream_progress(task_id: str):
    """
    Server-Sent Events 流式输出分析进度。

    前端通过 EventSource 订阅此端点，实时显示分析阶段和进度百分比。
    每 3 秒轮询一次任务状态，完成后发送最终事件并关闭连接。
    """
    task = _task_or_404(task_id)

    async def event_generator():
        last_phase = ""
        while True:
            # 任务结束 → 发送最终事件
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                event = ProgressEvent(
                    status=task.status.value,
                    phase=task.current_phase,
                    progress=100 if task.status == TaskStatus.COMPLETED else task.progress_pct,
                    message="分析完成" if task.status == TaskStatus.COMPLETED else f"失败: {task.error}",
                    elapsed=task.elapsed,
                )
                yield f"data: {event.model_dump_json()}\n\n"
                break

            # 阶段变化 → 发送进度事件
            if task.current_phase != last_phase:
                last_phase = task.current_phase
                event = ProgressEvent(
                    status=task.status.value,
                    phase=task.current_phase,
                    progress=task.progress_pct,
                    message=task.message,
                    elapsed=task.elapsed,
                )
                yield f"data: {event.model_dump_json()}\n\n"

            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# 分析任务：获取结果
# ============================================================

@router.get("/analyze/{task_id}", response_model=AnalyzeResult, summary="获取分析结果")
async def get_result(task_id: str):
    """
    获取分析任务的结果。

    - 任务未完成时返回当前状态（前端可轮询）
    - 任务完成时返回完整的分析结果
    - 任务失败时返回错误信息
    """
    task = _task_or_404(task_id)

    # 未完成 → 返回当前状态
    if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
        return AnalyzeResult(
            task_id=task_id,
            status=task.status,
            elapsed_seconds=task.elapsed,
        )

    # 失败 → 返回错误
    if task.status == TaskStatus.FAILED:
        return AnalyzeResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            elapsed_seconds=task.elapsed,
            error=task.error,
        )

    # 成功 → 构建完整结果
    result = task.result or {}
    resolved = result.get("resolved_entity", {})
    agent_outputs_raw = result.get("agent_outputs", {})
    consensus_raw = result.get("debate_consensus", {})

    # 构建 Agent 输出摘要
    agent_summaries = []
    for agent_id, output in agent_outputs_raw.items():
        agent_summaries.append(AgentOutputSummary(
            agent_name=output.get("agent_name", agent_id),
            status=output.get("status", "unknown"),
            confidence_score=output.get("confidence_score"),
            brief_summary=output.get("brief_summary", ""),
            fact_sheet=output.get("fact_sheet", {}),
        ))

    # 构建辩论摘要
    debate_summary = None
    if consensus_raw:
        debate_summary = DebateSummary(
            final_bull_confidence=consensus_raw.get("final_bull_confidence", 50),
            final_bear_confidence=consensus_raw.get("final_bear_confidence", 50),
            winner=consensus_raw.get("winner", "undecided"),
            debate_rounds=consensus_raw.get("debate_rounds", 0),
            risk_warning=consensus_raw.get("risk_warning", ""),
            consensus=consensus_raw.get("consensus", []),
        )

    return AnalyzeResult(
        task_id=task_id,
        status=TaskStatus.COMPLETED,
        stock_code=resolved.get("stock_code", ""),
        stock_name=resolved.get("stock_name", ""),
        confidence=resolved.get("confidence", 0),
        agent_outputs=agent_summaries,
        debate_summary=debate_summary,
        final_report=result.get("final_report"),
        report_path=result.get("report_id"),
        elapsed_seconds=task.elapsed,
    )


# ============================================================
# 报告下载与预览
# ============================================================

@router.get("/reports/{task_id}", summary="下载 Markdown 报告")
async def download_report(task_id: str):
    """下载原始 Markdown 格式的分析报告"""
    task = _completed_task_or_404(task_id)

    report_path = task.result.get("report_id", "")
    if not report_path or not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="报告文件不存在")

    return FileResponse(
        path=report_path,
        media_type="text/markdown",
        filename=os.path.basename(report_path),
    )


@router.get("/reports/{task_id}/html", summary="在线预览 HTML 报告")
async def preview_html(task_id: str):
    """
    生成并返回 HTML 格式的分析报告。

    包含数据表格、辩论结论、Agent 详情、图表等完整内容。
    同时将 HTML 文件保存到 reports/ 目录。
    """
    task = _completed_task_or_404(task_id)
    final_report = task.result.get("final_report", "")

    if not final_report:
        raise HTTPException(status_code=404, detail="无报告内容")

    from src.utils.html_report import generate_html_report, save_html_report
    from src.utils.charts import generate_all_charts

    resolved = task.result.get("resolved_entity", {})
    stock_code = resolved.get("stock_code", "report")
    stock_name = resolved.get("stock_name", "")

    # 收集所有 Agent 的 fact_sheet 用于图表生成
    all_facts = {}
    for output in task.result.get("agent_outputs", {}).values():
        for k, v in output.get("fact_sheet", {}).items():
            if k not in ("风险信号", "risk_signals", "risk_alerts", "风险预警") and v is not None:
                all_facts[k] = v

    # 生成图表
    debate = task.result.get("debate_consensus", {})
    charts = generate_all_charts(
        all_facts,
        bull_conf=debate.get("final_bull_confidence", 50) if debate else 50,
        bear_conf=debate.get("final_bear_confidence", 50) if debate else 50,
        stock_name=stock_name,
    )

    # 生成 HTML
    shared_ctx = task.result.get("shared_context", {})
    html = generate_html_report(
        stock_code=stock_code,
        stock_name=stock_name,
        final_report=final_report,
        agent_outputs=task.result.get("agent_outputs", {}),
        debate_consensus=debate,
        charts=charts,
        data_freshness=shared_ctx.get("data_freshness", ""),
        data_period=shared_ctx.get("data_period", ""),
    )

    # 保存到文件
    save_html_report(html, "./reports", stock_code)

    return HTMLResponse(content=html)


@router.get("/reports/{task_id}/excel", summary="下载 Excel 数据底稿")
async def download_excel(task_id: str):
    """
    导出并下载 Excel 格式的数据底稿。

    包含两个 Sheet：
    - 分析数据：各 Agent 的指标明细
    - 辩论结论：多空辩论结果
    """
    task = _completed_task_or_404(task_id)

    from src.utils.export import export_financial_data_excel

    stock_code = task.result.get("resolved_entity", {}).get("stock_code", "report")
    xlsx_path = os.path.join("./reports", f"{stock_code}_{task_id}.xlsx")

    try:
        shared_ctx = task.result.get("shared_context", {})
        export_financial_data_excel(
            task.result.get("agent_outputs", {}),
            xlsx_path,
            task.result.get("debate_consensus"),
            data_freshness=shared_ctx.get("data_freshness", ""),
            data_period=shared_ctx.get("data_period", ""),
        )
        return FileResponse(
            path=xlsx_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=os.path.basename(xlsx_path),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel 导出失败: {e}")


# ============================================================
# 任务列表
# ============================================================

@router.get("/tasks", response_model=TaskListResponse, summary="列出所有任务")
async def list_tasks():
    """返回所有任务的状态概览（用于调试和监控）"""
    tm = get_task_manager()
    tasks = tm.list_tasks()

    items = [
        TaskListItem(
            task_id=t.task_id,
            query=t.query,
            status=t.status,
            elapsed=t.elapsed,
        )
        for t in tasks.values()
    ]

    return TaskListResponse(tasks=items)
