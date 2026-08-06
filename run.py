"""
A股上市公司多智能体金融分析系统 - 统一入口

用法：
    python run.py                          # 直接启动服务器（PyCharm 右键运行）
    python run.py server                   # 启动 API 服务器
    python run.py server --port 8080       # 自定义端口
    python run.py server --reload          # 热重载
    python run.py analyze "分析贵州茅台"    # 命令行单次分析
    python run.py interactive              # 交互式模式
"""

import sys
import os
import time
from pathlib import Path

# 确保 src 在 Python 路径中
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.api.app import create_app
from src.utils.logger import setup_logger, get_logger
from src.api.llm_factory import create_llm, create_light_llm

# ============================================================
# 模块级别 app（PyCharm 可直接右键运行，也兼容 uvicorn 字符串引用）
# ============================================================

app = create_app()


# ============================================================
# CLI 模式
# ============================================================

def cmd_analyze(args):
    """执行单次分析"""
    setup_logger()
    logger = get_logger()
    from src.config import get_config
    config = get_config()

    if args.output:
        os.makedirs(args.output, exist_ok=True)
        config = config.__class__(
            llm=config.llm,
            embedding=config.embedding,
            cache=config.cache,
            vector_store=config.vector_store,
            data_source=config.data_source,
            report=config.report.__class__(output_dir=args.output),
            log_level=config.log_level,
            max_debate_rounds=args.rounds,
            max_tool_requests=config.max_tool_requests,
        )

    logger.info(f"{'=' * 60}")
    logger.info(f"开始分析: {args.query}")
    logger.info(f"{'=' * 60}")

    llm = create_llm(config)
    light_llm = create_light_llm(config)

    from src.graph import run_analysis

    start_time = time.time()
    result = run_analysis(
        query=args.query,
        llm=llm,
        light_llm=light_llm,
        max_debate_rounds=args.rounds,
        report_output_dir=config.report.output_dir,
    )
    elapsed = time.time() - start_time

    logger.info(f"\n{'=' * 60}")
    logger.info(f"分析完成，耗时: {elapsed:.1f} 秒")
    logger.info(f"{'=' * 60}")

    report_id = result.get("report_id", "")
    if report_id:
        logger.info(f"报告已保存: {report_id}")

    consensus = result.get("debate_consensus", {})
    if consensus:
        logger.info(f"\n辩论结论:")
        logger.info(f"  多方置信度: {consensus.get('final_bull_confidence', 'N/A')}")
        logger.info(f"  空方置信度: {consensus.get('final_bear_confidence', 'N/A')}")
        logger.info(f"  胜方: {consensus.get('winner', 'N/A')}")
        logger.info(f"  风险提示: {consensus.get('risk_warning', 'N/A')}")

    return result


def cmd_interactive(args):
    """交互式运行模式"""
    setup_logger()
    logger = get_logger()
    from src.config import get_config
    config = get_config()

    logger.info("=" * 60)
    logger.info("A股上市公司多智能体金融分析系统")
    logger.info("=" * 60)
    logger.info("输入股票代码或公司名称开始分析")
    logger.info("输入 'quit' 或 'exit' 退出")
    logger.info("-" * 60)

    while True:
        try:
            query = input("\n请输入分析目标（股票代码/公司名称）: ").strip()

            if not query:
                continue

            if query.lower() in ("quit", "exit", "q"):
                logger.info("再见！")
                break

            class FakeArgs:
                pass
            fake = FakeArgs()
            fake.query = query
            fake.output = None
            fake.rounds = config.max_debate_rounds

            result = cmd_analyze(fake)

            show = input("\n是否查看完整报告？(y/n): ").strip().lower()
            if show == "y":
                report = result.get("final_report", "")
                if report:
                    print("\n" + "=" * 60)
                    print(report)
                    print("=" * 60)

        except KeyboardInterrupt:
            logger.info("\n用户中断，退出...")
            break
        except Exception as e:
            logger.error(f"分析异常: {e}")
            import traceback
            traceback.print_exc()


def main():
    """主入口（需要子命令时调用）"""
    import argparse

    setup_logger()

    parser = argparse.ArgumentParser(
        description="A股上市公司多智能体金融分析系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py                          PyCharm 直接运行
  python run.py server --port 8080       自定义端口
  python run.py analyze "贵州茅台"       单次分析
  python run.py interactive              交互式模式
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # server
    p_server = subparsers.add_parser("server", help="启动 API 服务器")
    p_server.add_argument("--host", default="127.0.0.1", help="监听地址")
    p_server.add_argument("--port", type=int, default=8000, help="监听端口")
    p_server.add_argument("--reload", action="store_true", help="热重载")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="执行单次分析")
    p_analyze.add_argument("query", help="分析目标")
    p_analyze.add_argument("--output", "-o", help="报告输出目录")
    p_analyze.add_argument("--rounds", "-r", type=int, default=2, help="最大辩论轮次")

    # interactive
    p_interactive = subparsers.add_parser("interactive", help="交互式模式")
    p_interactive.add_argument("--output", "-o", help="报告输出目录")

    args = parser.parse_args()

    if args.command == "server":
        import uvicorn
        uvicorn.run(
            "run:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info",
            access_log=False,  # 关闭请求日志（减少刷屏）
        )
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "interactive":
        cmd_interactive(args)
    else:
        # 无子命令时直接启动服务器（PyCharm 右键运行的场景）
        import uvicorn
        uvicorn.run("run:app", host="127.0.0.1", port=8000, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
