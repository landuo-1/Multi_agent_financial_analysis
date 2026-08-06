"""
BaoStock 数据封装
提供 A 股历史数据查询，带缓存支持

关键设计：单次登录，持久连接，程序退出时自动登出
"""

import atexit
import pandas as pd
from typing import Optional, Dict, Any, List
from src.cache.sqlite_cache import get_cache
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# 持久连接（登录一次，复用全部查询）
# ============================================================

_bs_instance = None
_logged_in = False


def _get_bs():
    """获取 BaoStock 实例（懒加载，单次登录）"""
    global _bs_instance, _logged_in
    if _bs_instance is None:
        import baostock as bs
        _bs_instance = bs
    if not _logged_in:
        lg = _bs_instance.login()
        if lg.error_code != '0':
            logger.warning(f"BaoStock 登录警告: {lg.error_msg}")
        else:
            logger.info("BaoStock 登录成功")
        _logged_in = True
    return _bs_instance


def _logout_bs():
    """程序退出时登出"""
    global _bs_instance, _logged_in
    if _bs_instance is not None and _logged_in:
        _bs_instance.logout()
        _logged_in = False
        logger.info("BaoStock 已登出")


atexit.register(_logout_bs)


def _format_stock_code(code: str) -> str:
    """格式化股票代码为 BaoStock 格式 (sh.600519 或 sz.000001)"""
    code = code.strip()
    if code.startswith(("sh.", "sz.")):
        return code
    if code.startswith("6"):
        return f"sh.{code}"
    elif code.startswith(("0", "3")):
        return f"sz.{code}"
    elif code.startswith("8") or code.startswith("4"):
        return f"bj.{code}"
    return f"sh.{code}"


# ============================================================
# 数据查询函数
# ============================================================

def get_stock_kline(stock_code: str, start_date: str = "", end_date: str = "",
                    frequency: str = "d", adjustflag: str = "3") -> Dict[str, Any]:
    """获取K线数据"""
    cache = get_cache()
    cache_key = f"kline_{stock_code}_{start_date}_{end_date}_{frequency}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    bs = _get_bs()
    bs_code = _format_stock_code(stock_code)

    try:
        if not start_date:
            start_date = "2021-01-01"
        if not end_date:
            import datetime
            end_date = datetime.date.today().strftime("%Y-%m-%d")

        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg",
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            adjustflag=adjustflag,
        )

        data_list = []
        while rs.error_code == '0' and rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            result = {"status": "empty", "data": [], "message": "无数据"}
            cache.set(cache_key, result)
            return result

        df = pd.DataFrame(data_list, columns=rs.fields)
        numeric_cols = ["open", "high", "low", "close", "preclose", "volume", "amount", "turn", "pctChg"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        result = {
            "status": "success",
            "data": df.to_dict(orient="records"),
            "columns": list(df.columns),
            "count": len(df),
        }
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"BaoStock K线查询失败: {e}")
        return {"status": "error", "data": [], "message": str(e)}


def get_profit_data(stock_code: str, year: int = 2024, quarter: int = 4) -> Dict[str, Any]:
    """获取盈利能力数据"""
    cache = get_cache()
    cache_key = f"profit_{stock_code}_{year}_{quarter}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    bs = _get_bs()
    bs_code = _format_stock_code(stock_code)

    try:
        rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
        data_list = []
        while rs.error_code == '0' and rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            result = {"status": "empty", "data": {}, "message": "无盈利能力数据"}
            cache.set(cache_key, result)
            return result

        df = pd.DataFrame(data_list, columns=rs.fields)
        result = {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"BaoStock 盈利数据查询失败: {e}")
        return {"status": "error", "data": {}, "message": str(e)}


def get_balance_data(stock_code: str, year: int = 2024, quarter: int = 4) -> Dict[str, Any]:
    """获取偿债能力数据"""
    cache = get_cache()
    cache_key = f"balance_{stock_code}_{year}_{quarter}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    bs = _get_bs()
    bs_code = _format_stock_code(stock_code)

    try:
        rs = bs.query_balance_data(code=bs_code, year=year, quarter=quarter)
        data_list = []
        while rs.error_code == '0' and rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            result = {"status": "empty", "data": {}, "message": "无偿债能力数据"}
            cache.set(cache_key, result)
            return result

        df = pd.DataFrame(data_list, columns=rs.fields)
        result = {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"BaoStock 偿债数据查询失败: {e}")
        return {"status": "error", "data": {}, "message": str(e)}


def get_cashflow_data(stock_code: str, year: int = 2024, quarter: int = 4) -> Dict[str, Any]:
    """获取现金流数据"""
    cache = get_cache()
    cache_key = f"cashflow_{stock_code}_{year}_{quarter}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    bs = _get_bs()
    bs_code = _format_stock_code(stock_code)

    try:
        rs = bs.query_cash_flow_data(code=bs_code, year=year, quarter=quarter)
        data_list = []
        while rs.error_code == '0' and rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            result = {"status": "empty", "data": {}, "message": "无现金流数据"}
            cache.set(cache_key, result)
            return result

        df = pd.DataFrame(data_list, columns=rs.fields)
        result = {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"BaoStock 现金流数据查询失败: {e}")
        return {"status": "error", "data": {}, "message": str(e)}


def get_growth_data(stock_code: str, year: int = 2024, quarter: int = 4) -> Dict[str, Any]:
    """获取成长能力数据"""
    cache = get_cache()
    cache_key = f"growth_{stock_code}_{year}_{quarter}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    bs = _get_bs()
    bs_code = _format_stock_code(stock_code)

    try:
        rs = bs.query_growth_data(code=bs_code, year=year, quarter=quarter)
        data_list = []
        while rs.error_code == '0' and rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            result = {"status": "empty", "data": {}, "message": "无成长能力数据"}
            cache.set(cache_key, result)
            return result

        df = pd.DataFrame(data_list, columns=rs.fields)
        result = {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"BaoStock 成长数据查询失败: {e}")
        return {"status": "error", "data": {}, "message": str(e)}


def get_stock_basic(stock_code: str) -> Dict[str, Any]:
    """获取股票基本信息"""
    cache = get_cache()
    cache_key = f"basic_{stock_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    bs = _get_bs()
    bs_code = _format_stock_code(stock_code)

    try:
        rs = bs.query_stock_basic(code=bs_code)
        data_list = []
        while rs.error_code == '0' and rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            result = {"status": "empty", "data": {}, "message": "无基本信息"}
            cache.set(cache_key, result)
            return result

        df = pd.DataFrame(data_list, columns=rs.fields)
        result = {
            "status": "success",
            "data": df.to_dict(orient="records")[0] if len(df) > 0 else {},
            "columns": list(df.columns),
        }
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"BaoStock 基本信息查询失败: {e}")
        return {"status": "error", "data": {}, "message": str(e)}


# ============================================================
# 批量查询（减少循环开销）
# ============================================================

def get_multi_year_profit(stock_code: str, years: List[int] = None) -> Dict[str, Any]:
    """获取多年盈利能力数据（默认近3年）"""
    if years is None:
        import datetime
        current_year = datetime.date.today().year
        years = list(range(current_year - 2, current_year + 1))

    all_data = []
    for year in years:
        for quarter in [1, 2, 3, 4]:
            result = get_profit_data(stock_code, year, quarter)
            if result["status"] == "success" and result["data"]:
                records = result["data"] if isinstance(result["data"], list) else [result["data"]]
                for r in records:
                    r["year"] = year
                    r["quarter"] = quarter
                all_data.extend(records)

    return {"status": "success" if all_data else "empty", "data": all_data, "years_covered": years}


def get_multi_year_balance(stock_code: str, years: List[int] = None) -> Dict[str, Any]:
    """获取多年偿债能力数据（默认近3年）"""
    if years is None:
        import datetime
        current_year = datetime.date.today().year
        years = list(range(current_year - 2, current_year + 1))

    all_data = []
    for year in years:
        for quarter in [1, 2, 3, 4]:
            result = get_balance_data(stock_code, year, quarter)
            if result["status"] == "success" and result["data"]:
                records = result["data"] if isinstance(result["data"], list) else [result["data"]]
                for r in records:
                    r["year"] = year
                    r["quarter"] = quarter
                all_data.extend(records)

    return {"status": "success" if all_data else "empty", "data": all_data, "years_covered": years}
