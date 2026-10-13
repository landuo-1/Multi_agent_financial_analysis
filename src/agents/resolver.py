"""
实体解析器
使用 LLM 从用户输入中提取公司名称/股票代码，再匹配到唯一 A 股公司
"""

import json
import re
from typing import Any, Dict, List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 常见公司简称映射表（LLM 提取后用于快速匹配）
COMMON_ALIASES = {
    "茅台": ("600519", "贵州茅台"),
    "宁德": ("300750", "宁德时代"),
    "宁德时代": ("300750", "宁德时代"),
    "比亚迪": ("002594", "比亚迪"),
    "平安": ("601318", "中国平安"),
    "招行": ("600036", "招商银行"),
    "招商银行": ("600036", "招商银行"),
    "工行": ("601398", "工商银行"),
    "中石油": ("601857", "中国石油"),
    "中石化": ("600028", "中国石化"),
    "万科": ("000002", "万科A"),
    "格力": ("000651", "格力电器"),
    "美的": ("000333", "美的集团"),
    "海天": ("603288", "海天味业"),
    "恒瑞": ("600276", "恒瑞医药"),
    "药明": ("603259", "药明康德"),
    "隆基": ("601012", "隆基绿能"),
    "五粮液": ("000858", "五粮液"),
    "泸州老窖": ("000568", "泸州老窖"),
    "中芯": ("688981", "中芯国际"),
    "科大讯飞": ("002230", "科大讯飞"),
    "贵州茅台": ("600519", "贵州茅台"),
    "中国平安": ("601318", "中国平安"),
    "工商银行": ("601398", "工商银行"),
    "宁德时代": ("300750", "宁德时代"),
}


def _llm_extract_entity(query: str, llm: BaseChatModel) -> Dict[str, Any]:
    """
    用 LLM 从用户问题中提取公司名称或股票代码
    支持错别字纠正和自然语言理解
    返回: {"name": "科大讯飞", "code": "002230"} 或 {"name": "", "code": ""}
    """
    system_prompt = """你是一个 A 股上市公司实体提取器。从用户输入中提取公司名称或股票代码。

规则：
1. 如果用户提到了公司名称，输出 name 字段（使用公司全称或标准简称）
2. 如果用户提到了6位股票代码，输出 code 字段
3. 如果两者都没有，输出空字符串
4. 如果用户输入有错别字或谐音字，必须纠正为正确的公司名称
   例如："嗨康威视" → "海康威视"，"矛台" → "茅台"，"平安很行" → "平安银行"
5. 如果用户用描述性语言指代公司（如"做电池的龙头"），识别为对应公司（如"宁德时代"）
6. 只输出 JSON，不要解释

输出格式：
{"name": "正确的公司名称", "code": "6位代码或空"}"""

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"用户输入：{query}"),
        ]
        response = llm.invoke(messages)
        text = response.content.strip()

        # 解析 JSON
        # 尝试直接解析
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # 从 code block 提取
            match = re.search(r'\{[^}]+\}', text)
            if match:
                result = json.loads(match.group())
            else:
                return {"name": "", "code": ""}

        return {
            "name": result.get("name", "").strip(),
            "code": result.get("code", "").strip(),
        }

    except Exception as e:
        logger.warning(f"LLM 实体提取失败: {e}")
        return {"name": "", "code": ""}


def _match_company(name: str, code: str) -> Dict[str, Any]:
    """
    将提取的名称/代码匹配到唯一 A 股公司
    优先级：代码直接匹配 → 别名表 → AKShare 搜索
    """
    # 1. 有代码，直接用
    if code and re.match(r'^\d{6}$', code):
        # 尝试从别名表找全称
        for alias, (c, full_name) in COMMON_ALIASES.items():
            if c == code:
                return {
                    "stock_code": code,
                    "stock_name": full_name,
                    "confidence": 0.95,
                    "source": "code_match",
                }
        return {
            "stock_code": code,
            "stock_name": f"股票{code}",
            "confidence": 0.8,
            "source": "code_direct",
        }

    # 2. 有名称，查别名表
    if name:
        # 精确匹配
        if name in COMMON_ALIASES:
            code, full_name = COMMON_ALIASES[name]
            return {
                "stock_code": code,
                "stock_name": full_name,
                "confidence": 0.95,
                "source": "alias_exact",
            }

        # 模糊匹配：按别名长度降序排列，优先匹配最长的别名
        # 避免 "平安银行" 匹配到 "平安"（中国平安）而非更精确的结果
        sorted_aliases = sorted(COMMON_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
        for alias, (c, full_name) in sorted_aliases:
            if name in alias or alias in name:
                return {
                    "stock_code": c,
                    "stock_name": full_name,
                    "confidence": 0.90,
                    "source": "alias_partial",
                }

        # 3. AKShare 搜索（较慢）
        try:
            from src.tools.akshare_wrapper import search_company_by_name
            result = search_company_by_name(name)
            if result["status"] == "success" and result["results"]:
                best = result["results"][0]
                return {
                    "stock_code": best["stock_code"],
                    "stock_name": best["stock_name"],
                    "confidence": 0.85,
                    "source": "akshare_search",
                }
        except Exception as e:
            logger.warning(f"AKShare 搜索失败: {e}")

    return {
        "stock_code": "",
        "stock_name": "",
        "confidence": 0,
        "source": "not_found",
    }


def resolve_entity(query: str, llm: Optional[BaseChatModel] = None) -> Dict[str, Any]:
    """
    实体解析主函数
    返回: {stock_code, stock_name, confidence, candidates, action, message}
    """
    logger.info(f"实体解析输入: '{query}'")

    # 第一步：LLM 提取实体
    if llm:
        extracted = _llm_extract_entity(query, llm)
        logger.info(f"LLM 提取结果: {extracted}")
        entity_name = extracted["name"]
        entity_code = extracted["code"]
    else:
        # 无 LLM 时的简单回退：尝试匹配别名表
        entity_name = ""
        entity_code = ""
        for alias in COMMON_ALIASES:
            if alias in query:
                entity_name = alias
                break
        code_match = re.search(r'\b(\d{6})\b', query)
        if code_match:
            entity_code = code_match.group(1)

    if not entity_name and not entity_code:
        return {
            "stock_code": "",
            "stock_name": "",
            "confidence": 0,
            "candidates": [],
            "action": "not_found",
            "message": "无法从输入中识别公司名称或股票代码，请输入更明确的信息",
        }

    # 第二步：匹配公司
    match = _match_company(entity_name, entity_code)

    if match["confidence"] == 0:
        return {
            "stock_code": "",
            "stock_name": "",
            "confidence": 0,
            "candidates": [],
            "action": "not_found",
            "message": f"未找到与'{entity_name or entity_code}'匹配的A股公司",
        }

    # 判断动作
    if match["confidence"] >= 0.90:
        action = "auto_confirm"
    elif match["confidence"] >= 0.70:
        action = "need_confirm"
    else:
        action = "not_found"

    logger.info(f"实体解析结果: {match['stock_name']}({match['stock_code']}), "
                f"置信度: {match['confidence']}, 来源: {match['source']}")

    return {
        "stock_code": match["stock_code"],
        "stock_name": match["stock_name"],
        "confidence": match["confidence"],
        "candidates": [match],
        "action": action,
        "message": f"找到: {match['stock_name']}({match['stock_code']})" if action != "not_found" else "未找到匹配",
    }


class EntityResolver:
    """实体解析器节点（LangGraph 节点）"""

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph 节点入口"""
        query = state.get("user_query", "")
        result = resolve_entity(query, self.llm)

        return {
            "resolved_entity": result,
            "messages": [{"role": "system", "content": f"实体解析: {result['message']}"}],
        }
