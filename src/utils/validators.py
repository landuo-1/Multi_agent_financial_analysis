"""
数据校验工具
Pydantic 校验器和数据质量检查
"""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import ValidationError
from src.state import AgentEnvelope, ToolRequest, DebateArgument
from src.utils.logger import get_logger

logger = get_logger(__name__)


def validate_agent_envelope(data: Dict[str, Any]) -> Tuple[bool, Optional[AgentEnvelope], Optional[str]]:
    """
    校验子 Agent 输出信封格式
    返回: (是否成功, 校验后的对象, 错误信息)
    """
    try:
        envelope = AgentEnvelope(**data)
        return True, envelope, None
    except ValidationError as e:
        error_msg = f"信封校验失败: {e}"
        logger.warning(error_msg)
        return False, None, error_msg


def validate_tool_request(data: Dict[str, Any]) -> Tuple[bool, Optional[ToolRequest], Optional[str]]:
    """校验工具申请格式"""
    try:
        request = ToolRequest(**data)
        return True, request, None
    except ValidationError as e:
        error_msg = f"工具申请校验失败: {e}"
        logger.warning(error_msg)
        return False, None, error_msg


def validate_debate_argument(data: Dict[str, Any]) -> Tuple[bool, Optional[DebateArgument], Optional[str]]:
    """校辩论论点格式"""
    try:
        arg = DebateArgument(**data)
        return True, arg, None
    except ValidationError as e:
        error_msg = f"辩论论点校验失败: {e}"
        logger.warning(error_msg)
        return False, None, error_msg


def check_data_quality(value: Any, field_name: str) -> Dict[str, Any]:
    """
    数据质量检查
    返回: {"valid": bool, "warnings": list, "value": any}
    """
    warnings = []

    if value is None:
        return {"valid": False, "warnings": [f"{field_name}: 值为 None"], "value": None}

    if isinstance(value, (int, float)):
        if value < 0 and field_name in ["pe_ttm", "pb", "ps"]:
            warnings.append(f"{field_name}: 负值 {value}，可能是亏损公司")
        if value == 0 and field_name in ["roe", "gross_margin"]:
            warnings.append(f"{field_name}: 值为 0，请核实数据准确性")
        if abs(value) > 1000 and field_name in ["pe_ttm"]:
            warnings.append(f"{field_name}: 极端值 {value}，可能是数据异常")

    if isinstance(value, str) and value.strip() == "":
        return {"valid": False, "warnings": [f"{field_name}: 空字符串"], "value": value}

    return {"valid": True, "warnings": warnings, "value": value}


def validate_financial_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    批量校验财务数据质量
    返回: {"valid_count": int, "invalid_count": int, "warnings": list, "cleaned_data": dict}
    """
    cleaned = {}
    all_warnings = []
    valid_count = 0
    invalid_count = 0

    for key, value in data.items():
        result = check_data_quality(value, key)
        if result["valid"]:
            valid_count += 1
            cleaned[key] = result["value"]
        else:
            invalid_count += 1
        all_warnings.extend(result["warnings"])

    return {
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "warnings": all_warnings,
        "cleaned_data": cleaned,
    }
