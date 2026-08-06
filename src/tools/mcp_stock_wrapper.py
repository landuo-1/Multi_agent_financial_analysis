"""
MCP 中国股票数据封装
数据源：mcp-cn-a-stock (https://github.com/elsejj/mcp-cn-a-stock)
提供：基本信息、行情、财务、技术指标、资金流向

通过 HTTP 调用公共服务端，无需本地部署
"""

import json
import re
import time
from typing import Any, Dict, Optional
from src.cache.sqlite_cache import get_cache
from src.utils.logger import get_logger

logger = get_logger(__name__)

# MCP 公共服务端地址
MCP_SERVER_URL = "http://82.156.17.205/cnstock/mcp"

# 请求超时
REQUEST_TIMEOUT = 30


def _format_symbol(stock_code: str) -> str:
    """
    将股票代码转换为 MCP 格式
    600519 → SH600519, 000001 → SZ000001, 300750 → SZ300750
    """
    code = stock_code.strip()
    if code.upper().startswith(("SH", "SZ", "BJ")):
        return code.upper()
    if code.startswith("6"):
        return f"SH{code}"
    elif code.startswith(("0", "3")):
        return f"SZ{code}"
    elif code.startswith(("8", "4")):
        return f"BJ{code}"
    return f"SH{code}"


def _parse_sse_response(sse_text: str) -> Optional[str]:
    """从 SSE 响应中提取文本内容"""
    # SSE 格式: event: message\ndata: {...}
    for line in sse_text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if "result" in data:
                    result = data["result"]
                    if "content" in result:
                        contents = result["content"]
                        if contents and len(contents) > 0:
                            return contents[0].get("text", "")
                    return str(result)
            except json.JSONDecodeError:
                continue
    return None


def _call_mcp_tool(tool_name: str, symbol: str) -> Optional[str]:
    """调用 MCP 服务器的工具"""
    import httpx

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": {"symbol": symbol},
        },
    }

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.post(
                MCP_SERVER_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                return _parse_sse_response(response.text)
            else:
                data = response.json()
                if "result" in data:
                    result = data["result"]
                    if "content" in result:
                        return result["content"][0].get("text", "")
                    return str(result)
                return None

    except Exception as e:
        logger.error(f"MCP 请求失败: {tool_name}({symbol}): {e}")
        return None


def _parse_brief_text(text: str) -> Dict[str, Any]:
    """
    解析 brief 返回的 Markdown 文本为结构化数据
    使用纯数字模式匹配，避免编码问题
    """
    data = {"raw_text": text}

    # 按行解析（每行格式: - 标签: 数值）
    lines = text.split("\n")
    values = []
    for line in lines:
        # 提取每行的数值（整数或小数）
        nums = re.findall(r'-?\d+\.?\d*', line)
        values.extend(nums)

    # 基本信息（按顺序提取）
    # 行 1: 股票代码
    # 行 2: 股票名称
    # 行 3: 数据日期
    # 行 4: 行业分类
    # 行 5: 市盈率
    # 行 6: 市净率
    # 行 7: 净资产收益率

    # 用正则精确匹配关键字段
    # 市盈率
    pe_match = re.search(r'[\d.]+\s*$', text[:500], re.MULTILINE)
    # 找到 "市盈率" 后面的数字
    pe_section = text[:800]
    pe_nums = re.findall(r'(\d+\.?\d*)', pe_section)
    if len(pe_nums) >= 3:
        # 第3个数字通常是市盈率
        pass

    # 更可靠的方式：按行解析
    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("-"):
            # 去掉 "- " 前缀
            content = stripped[2:].strip() if len(stripped) > 2 else stripped
            # 分割标签和值
            if ":" in content:
                parts = content.split(":", 1)
                label = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ""
                # 尝试转为数值
                try:
                    num = float(re.search(r'-?\d+\.?\d*', value).group()) if re.search(r'-?\d+\.?\d*', value) else None
                except:
                    num = None
                # 存储（用标签的hash作为key避免编码问题）
                data[f"field_{len(data)}"] = {"label": label, "value": value, "num": num}

    # 提取关键数值（按位置顺序）
    # PE: 第5行第1个数值
    # PB: 第6行第1个数值
    # ROE: 第7行第1个数值

    # 使用数字位置提取
    all_nums = re.findall(r'(\d+\.?\d*)', text[:1000])

    # 简单映射（基于已知的输出格式）
    if len(all_nums) >= 6:
        data["pe_ttm"] = _safe_float(all_nums[4]) if len(all_nums) > 4 else None
        data["pb"] = _safe_float(all_nums[5]) if len(all_nums) > 5 else None
        data["roe"] = _safe_float(all_nums[6]) if len(all_nums) > 6 else None

    # 价格数据（格式: - 最新: 1321.000 最高: 1343.480 最低: 1312.060）
    # 用数字模式匹配：一行中有3个连续的小数
    price_line_match = re.search(r'(\d+\.\d{3})\s+\D*(\d+\.\d{3})\s+\D*(\d+\.\d{3})', text)
    if price_line_match:
        data["current_price"] = float(price_line_match.group(1))
        data["high"] = float(price_line_match.group(2))
        data["low"] = float(price_line_match.group(3))

    # 涨跌幅（第一个百分比）
    pct_matches = re.findall(r'([\d.-]+)%', text)
    if pct_matches:
        data["change_pct"] = float(pct_matches[0])
    if len(pct_matches) > 1:
        data["change_5d"] = float(pct_matches[1])

    # 资金流向
    fund_match = re.search(r'([\d.]+)亿', text)
    if fund_match:
        data["main_fund_flow"] = float(fund_match.group(1))

    return data


def _safe_float(val) -> Optional[float]:
    """安全转换为 float"""
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def get_stock_brief(stock_code: str) -> Dict[str, Any]:
    """
    获取股票简要信息（基本信息 + 行情）
    缓存 1 小时
    """
    cache = get_cache()
    cache_key = f"mcp_brief_{stock_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    symbol = _format_symbol(stock_code)
    logger.info(f"MCP 获取简要信息: {symbol}")

    text = _call_mcp_tool("brief", symbol)
    if text is None:
        result = {"status": "error", "data": {}, "message": "MCP 请求失败"}
        cache.set(cache_key, result, ttl_seconds=300)
        return result

    parsed = _parse_brief_text(text)
    result = {
        "status": "success",
        "data": parsed,
        "source": "mcp_cn_stock",
    }
    cache.set(cache_key, result, ttl_seconds=3600)
    return result


def get_stock_medium(stock_code: str) -> Dict[str, Any]:
    """
    获取股票中等信息（基本信息 + 行情 + 财务数据）
    缓存 1 小时
    """
    cache = get_cache()
    cache_key = f"mcp_medium_{stock_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    symbol = _format_symbol(stock_code)
    logger.info(f"MCP 获取中等信息: {symbol}")

    text = _call_mcp_tool("medium", symbol)
    if text is None:
        result = {"status": "error", "data": {}, "message": "MCP 请求失败"}
        cache.set(cache_key, result, ttl_seconds=300)
        return result

    result = {
        "status": "success",
        "data": {"raw_text": text},
        "source": "mcp_cn_stock",
    }
    cache.set(cache_key, result, ttl_seconds=3600)
    return result


def get_stock_full(stock_code: str) -> Dict[str, Any]:
    """
    获取股票完整信息（基本信息 + 行情 + 财务 + 技术指标）
    缓存 30 分钟
    """
    cache = get_cache()
    cache_key = f"mcp_full_{stock_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    symbol = _format_symbol(stock_code)
    logger.info(f"MCP 获取完整信息: {symbol}")

    text = _call_mcp_tool("full", symbol)
    if text is None:
        result = {"status": "error", "data": {}, "message": "MCP 请求失败"}
        cache.set(cache_key, result, ttl_seconds=300)
        return result

    result = {
        "status": "success",
        "data": {"raw_text": text},
        "source": "mcp_cn_stock",
    }
    cache.set(cache_key, result, ttl_seconds=1800)
    return result
