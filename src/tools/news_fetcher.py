"""
新闻采集模块
从新浪财经获取个股新闻，用于舆情分析
"""

import re
import time
from typing import Any, Dict, List
from src.cache.sqlite_cache import get_cache
from src.utils.logger import get_logger

logger = get_logger(__name__)


def fetch_stock_news(stock_code: str, stock_name: str = "") -> Dict[str, Any]:
    """
    从新浪财经获取个股新闻

    Args:
        stock_code: 股票代码（如 600519）
        stock_name: 公司名称（用于过滤相关新闻）

    Returns:
        {"status": "success", "data": [...], "count": int}
    """
    cache = get_cache()
    cache_key = f"news_{stock_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        import httpx

        # 根据股票代码判断市场前缀
        if stock_code.startswith('6'):
            market = 'sh'
        elif stock_code.startswith(('0', '3')):
            market = 'sz'
        else:
            market = 'sh'

        # 新浪财经个股页面
        url = f'https://finance.sina.com.cn/realstock/company/{market}{stock_code}/nc.shtml'

        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
            text = resp.content.decode('gb2312', errors='ignore')

        # 提取新闻标题和链接
        pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]{8,120})</a>'
        matches = re.findall(pattern, text)

        news_list = []
        seen_titles = set()

        # 噪声关键词（非新闻内容）
        noise_keywords = ['行情', '数据', 'level2', '查看详情', '更多', '股市雷达',
                          '名师团', '在线直播', '立即了解', '点这里', '配置']

        for link, title in matches:
            title = title.strip()

            # 基本过滤
            if len(title) < 8:
                continue
            if title in seen_titles:
                continue

            # 噪声过滤
            if any(noise in title for noise in noise_keywords):
                continue
            if title.startswith('用') or title.startswith('点击查看'):
                continue
            # 过滤纯符号或数字
            if re.match(r'^[\d\s\.\-\+]+$', title):
                continue

            seen_titles.add(title)
            news_list.append({
                "title": title,
                "link": link if link.startswith('http') else '',
                "source": "新浪财经",
            })

            if len(news_list) >= 20:
                break

        result = {
            "status": "success",
            "data": news_list,
            "count": len(news_list),
            "source": "sina_finance",
        }

        # 缓存 1 小时
        cache.set(cache_key, result, ttl_seconds=3600)
        return result

    except Exception as e:
        logger.error(f"新闻获取失败: {e}")
        return {"status": "error", "data": [], "count": 0, "message": str(e)}


# 情绪关键词
POSITIVE_KEYWORDS = [
    '上涨', '大涨', '涨停', '利好', '突破', '新高', '增长', '盈利',
    '复苏', '景气', '龙头', '优势', '创新', '升级', '扩张', '分红',
    '回购', '增持', '推荐', '买入', '看多', '强势', '走强', '反弹',
]

NEGATIVE_KEYWORDS = [
    '下跌', '大跌', '跌停', '利空', '破位', '新低', '下滑', '亏损',
    '衰退', '低迷', '风险', '问题', '违规', '处罚', '减持', '质押',
    '卖出', '看空', '弱势', '回调', '暴跌', '崩盘', '爆雷', '退市',
]


def analyze_sentiment(news_list: List[Dict]) -> Dict[str, Any]:
    """
    基于关键词的简单情绪分析

    Returns:
        {"sentiment_score": float, "positive_count": int, "negative_count": int, "summary": str}
    """
    if not news_list:
        return {
            "sentiment_score": 0.5,
            "positive_count": 0,
            "negative_count": 0,
            "neutral_count": 0,
            "summary": "无新闻数据",
        }

    positive_count = 0
    negative_count = 0
    neutral_count = 0
    positive_titles = []
    negative_titles = []

    for news in news_list:
        title = news.get("title", "")

        pos_match = sum(1 for kw in POSITIVE_KEYWORDS if kw in title)
        neg_match = sum(1 for kw in NEGATIVE_KEYWORDS if kw in title)

        if pos_match > neg_match:
            positive_count += 1
            positive_titles.append(title)
        elif neg_match > pos_match:
            negative_count += 1
            negative_titles.append(title)
        else:
            neutral_count += 1

    total = len(news_list)
    sentiment_score = (positive_count - negative_count) / total if total > 0 else 0
    # 归一化到 0-1
    sentiment_score = max(0, min(1, (sentiment_score + 1) / 2))

    # 生成摘要
    if sentiment_score > 0.65:
        summary = f"市场情绪偏积极，{positive_count}条正面新闻 vs {negative_count}条负面"
    elif sentiment_score < 0.35:
        summary = f"市场情绪偏消极，{negative_count}条负面新闻 vs {positive_count}条正面"
    else:
        summary = f"市场情绪中性，正面{positive_count}条，负面{negative_count}条，中性{neutral_count}条"

    return {
        "sentiment_score": round(sentiment_score, 2),
        "positive_count": positive_count,
        "negative_count": negative_count,
        "neutral_count": neutral_count,
        "positive_titles": positive_titles[:3],
        "negative_titles": negative_titles[:3],
        "total_news": total,
        "summary": summary,
    }


def get_stock_sentiment(stock_code: str, stock_name: str = "") -> Dict[str, Any]:
    """
    获取股票舆情分析（新闻 + 情绪评分）
    """
    news_result = fetch_stock_news(stock_code, stock_name)

    if news_result["status"] != "success":
        return {
            "status": "error",
            "data": {},
            "message": news_result.get("message", "新闻获取失败"),
        }

    sentiment = analyze_sentiment(news_result["data"])

    return {
        "status": "success",
        "data": {
            "sentiment_score": sentiment["sentiment_score"],
            "positive_count": sentiment["positive_count"],
            "negative_count": sentiment["negative_count"],
            "neutral_count": sentiment["neutral_count"],
            "positive_titles": sentiment["positive_titles"],
            "negative_titles": sentiment["negative_titles"],
            "total_news": sentiment["total_news"],
            "summary": sentiment["summary"],
            "recent_news": news_result["data"][:5],
        },
        "source": "sina_finance",
    }
