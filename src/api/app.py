"""
FastAPI 应用工厂

职责：
- 创建和配置 FastAPI 实例
- 注册中间件（CORS、请求日志）
- 注册全局异常处理器
- 管理应用生命周期（启动/关闭）

用法：
    from src.api.app import create_app
    app = create_app()
    # 或直接：python run.py server
"""

import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.utils.logger import setup_logger, get_logger, log_api_request


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化日志，关闭时清理资源"""
    setup_logger()
    logger = get_logger()
    logger.info("[System] FastAPI 应用启动")

    # 启动时清理过期任务
    try:
        from src.api.tasks import get_task_manager
        get_task_manager().cleanup_expired()
    except Exception:
        pass

    yield

    logger.info("[System] FastAPI 应用关闭")


def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用

    Returns:
        配置完成的 FastAPI 实例
    """
    app = FastAPI(
        title="A股多智能体金融分析系统",
        description=(
            "基于 LangGraph 的生产级多智能体系统，对 A 股上市公司进行深度金融分析。"
            "支持实体解析、多维分析、多空辩论、报告生成等完整流程。"
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ---- CORS 中间件 ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- 全局异常处理器 ----

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """请求参数校验失败时返回 422 + 人类可读的错误详情"""
        errors = exc.errors()
        detail = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in errors
        )
        return JSONResponse(
            status_code=422,
            content={"error": "请求参数校验失败", "detail": detail},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """兜底异常处理：捕获所有未处理的异常，返回 500"""
        logger = get_logger()
        logger.error(f"[API] 未处理异常: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "服务器内部错误", "detail": str(exc)},
        )

    # ---- 请求日志中间件 ----

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """
        记录 API 请求日志

        规则：
        - 只记录 /api/ 路径
        - 跳过 SSE 流式端点（高频轮询会产生大量日志）
        - 跳过文档路径
        """
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        path = request.url.path
        if path.startswith("/api/") and "/stream" not in path and "/docs" not in path:
            # 跳过 /api/analyze/{task_id} 这种高频轮询端点
            if not (path.startswith("/api/analyze/") and path.count("/") == 3):
                log_api_request(request.method, path, response.status_code, duration_ms)

        return response

    # ---- 注册路由 ----
    app.include_router(router)

    # ---- 根端点 ----

    @app.get("/", tags=["root"], summary="系统信息")
    async def root():
        return {
            "name": "A股多智能体金融分析系统",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
        }

    return app
