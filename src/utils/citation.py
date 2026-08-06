"""
溯源脚注生成器
为报告中的数据引用生成可追溯的脚注标记
"""

from typing import Dict, List, Optional
import re


class CitationManager:
    """管理报告中的数据引用和脚注"""

    def __init__(self):
        self._citations: List[Dict[str, str]] = []
        self._counter = 0
        self._ref_map: Dict[str, int] = {}  # full_report_ref -> footnote number

    def add_citation(self, source: str, ref_id: str, description: str = "") -> str:
        """
        添加一个引用，返回脚注标记 [^n]
        source: 数据来源（如 "Financial Agent"）
        ref_id: 引用 ID（如 "fin_600519_001"）
        description: 可选描述
        """
        # 去重：相同 ref_id 只编号一次
        if ref_id in self._ref_map:
            n = self._ref_map[ref_id]
            return f"[^{n}]"

        self._counter += 1
        n = self._counter
        self._ref_map[ref_id] = n
        self._citations.append({
            "number": n,
            "source": source,
            "ref_id": ref_id,
            "description": description,
        })
        return f"[^{n}]"

    def get_footnotes(self) -> str:
        """生成脚注文本块"""
        if not self._citations:
            return ""

        lines = ["\n---", "**数据来源与引用**：\n"]
        for cite in self._citations:
            desc = f"，{cite['description']}" if cite['description'] else ""
            lines.append(f"[^{cite['number']}]: {cite['source']}，引用 ID: {cite['ref_id']}{desc}")
        return "\n".join(lines)

    def get_all_citations(self) -> List[Dict[str, str]]:
        """获取所有引用记录"""
        return self._citations.copy()

    def reset(self):
        """重置引用管理器"""
        self._citations.clear()
        self._counter = 0
        self._ref_map.clear()

    @staticmethod
    def inline_ref(text: str, source: str, ref_id: str, cm: "CitationManager") -> str:
        """在文本中插入引用标记"""
        marker = cm.add_citation(source, ref_id)
        return f"{text} {marker}"
