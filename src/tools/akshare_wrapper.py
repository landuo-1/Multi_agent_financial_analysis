"""
AKShare 数据封装
提供估值数据、行业数据等补充信息

内置重试机制：AKShare 接口不稳定，自动重试最多 3 次
"""

import time
from typing import Any, Dict, Optional
from src.cache.sqlite_cache import get_cache
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _retry(max_retries: int = 3, delay: float = 2.0):
    """重试装饰器（指数退避）"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    wait = delay * (2 ** attempt)
                    logger.warning(f"[{func.__name__}] 第{attempt+1}次失败: {e}，{wait:.0f}s后重试")
                    time.sleep(wait)
            logger.error(f"[{func.__name__}] {max_retries}次重试均失败")
            raise last_error
        return wrapper
    return decorator


def _safe_float(value) -> Optional[float]:
    """安全转换为 float，失败返回 None"""
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


@_retry(max_retries=3, delay=2.0)
def get_stock_info(stock_code: str) -> Dict[str, Any]:
    """
    获取股票基本信息（公司名称、行业、市值等）
    使用 AKShare 的 stock_individual_info_em 接口
    """
    cache = get_cache()
    cache_key = f"akshare_info_{stock_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=stock_code)
        if df is None or df.empty:
            result = {"status": "empty", "data": {}, "message": "无数据"}
            cache.set(cache_key, result)
            return result

        info = {}
        for _, row in df.iterrows():
            info[row.get("item", "")] = row.get("value", "")

        result = {
            "status": "success",
            "data": info,
            "stock_name": info.get("股票简称", ""),
            "industry": info.get("行业", ""),
            "market_cap": info.get("总市值", ""),
        }
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"AKShare 股票信息查询失败: {e}")
        return {"status": "error", "data": {}, "message": str(e)}


@_retry(max_retries=3, delay=2.0)
def get_stock_valuation(stock_code: str) -> Dict[str, Any]:
    """
    获取估值数据（PE、PB、股价等）
    使用单股查询接口（stock_individual_info_em），速度快
    缓存 TTL: 1小时（实时数据需要更短的缓存）
    """
    cache = get_cache()
    cache_key = f"akshare_valuation_{stock_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        import akshare as ak

        # 使用单股接口（比 stock_zh_a_spot_em 快100倍）
        df = ak.stock_individual_info_em(symbol=stock_code)
        if df is None or df.empty:
            result = {"status": "empty", "data": {}, "message": "无数据"}
            cache.set(cache_key, result, ttl_seconds=300)  # 5分钟
            return result

        # 解析为字典 {item: value}
        info = {}
        for _, row in df.iterrows():
            info[str(row.get("item", ""))] = row.get("value", "")

        valuation = {
            "current_price": _safe_float(info.get("最新价")),
            "pe_ttm": _safe_float(info.get("市盈率(动态)")),
            "pb": _safe_float(info.get("市净率")),
            "total_market_cap": _safe_float(info.get("总市值")),
            "circulating_market_cap": _safe_float(info.get("流通市值")),
            "volume": _safe_float(info.get("成交量")),
            "amount": _safe_float(info.get("成交额")),
            "change_pct": _safe_float(info.get("涨跌幅")),
            "stock_name": info.get("股票简称", ""),
            "industry": info.get("行业", ""),
        }

        result = {"status": "success", "data": valuation}
        # 实时数据缓存1小时
        cache.set(cache_key, result, ttl_seconds=3600)
        return result

    except Exception as e:
        logger.error(f"AKShare 估值数据查询失败: {e}")
        return {"status": "error", "data": {}, "message": str(e)}


@_retry(max_retries=3, delay=2.0)
def get_industry_pe(industry: str) -> Dict[str, Any]:
    """获取行业平均 PE"""
    cache = get_cache()
    cache_key = f"akshare_industry_pe_{industry}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        import akshare as ak
        df = ak.stock_board_industry_hist_em(
            symbol=industry,
            period="日k",
            adjust="qfq"
        )
        if df is None or df.empty:
            result = {"status": "empty", "data": {}, "message": f"无行业 {industry} 数据"}
            cache.set(cache_key, result)
            return result

        result = {
            "status": "success",
            "data": df.tail(30).to_dict(orient="records"),
        }
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"AKShare 行业数据查询失败: {e}")
        return {"status": "error", "data": {}, "message": str(e)}


@_retry(max_retries=3, delay=2.0)
def get_stock_news(stock_code: str, stock_name: str = "") -> Dict[str, Any]:
    """获取股票相关新闻（用于舆情分析）"""
    cache = get_cache()
    cache_key = f"akshare_news_{stock_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        import akshare as ak
        # 使用东方财富新闻接口
        keyword = stock_name or stock_code
        df = ak.stock_news_em(symbol=stock_code)
        if df is None or df.empty:
            result = {"status": "empty", "data": [], "message": "无新闻数据"}
            cache.set(cache_key, result)
            return result

        news_list = []
        for _, row in df.head(20).iterrows():
            news_list.append({
                "title": str(row.get("新闻标题", "")),
                "content": str(row.get("新闻内容", ""))[:500],
                "source": str(row.get("文章来源", "")),
                "time": str(row.get("发布时间", "")),
            })

        result = {
            "status": "success",
            "data": news_list,
            "count": len(news_list),
        }
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.warning(f"AKShare 新闻查询失败（可能不支持该接口）: {e}")
        return {"status": "error", "data": [], "message": str(e)}


@_retry(max_retries=3, delay=2.0)
def search_company_by_name(name: str) -> Dict[str, Any]:
    """
    根据公司名称模糊搜索股票代码
    使用 stock_info_a_code_name 接口（轻量，覆盖全量 A 股 5500+ 只）
    结果缓存 24 小时
    """
    cache = get_cache()
    cache_key = "akshare_all_stock_names"
    cached = cache.get(cache_key)

    try:
        import akshare as ak

        if cached is not None:
            all_stocks = cached
        else:
            # 获取全量 A 股代码+名称（轻量接口，~6秒）
            df = ak.stock_info_a_code_name()
            if df is None or df.empty:
                return {"status": "error", "results": [], "message": "无法获取股票列表"}
            all_stocks = df.to_dict(orient="records")
            # 缓存 24 小时
            cache.set(cache_key, all_stocks, ttl_seconds=86400)

        # 模糊匹配
        results = []
        for stock in all_stocks:
            stock_name = stock.get("name", "")
            if name in stock_name:
                results.append({
                    "stock_code": str(stock.get("code", "")),
                    "stock_name": stock_name,
                    "confidence": 0.85,
                    "source": "akshare_search",
                })

        return {
            "status": "success",
            "results": results[:10],
            "count": len(results),
        }

    except Exception as e:
        logger.error(f"公司搜索失败: {e}")
        return {"status": "error", "results": [], "message": str(e)}
