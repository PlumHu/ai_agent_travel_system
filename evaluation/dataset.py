"""
评估数据集管理
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CASES_DIR = Path(__file__).parent / "test_cases"


class EvalDataset:
    """
    评估数据集管理器

    数据格式：
    [
        {
            "id": "TC001",
            "input": "用户输入文本",
            "expected": { ... },      // 预期输出
            "category": "分类标签",
            "difficulty": "easy|medium|hard"
        }
    ]
    """

    def __init__(self, cases_path: Optional[str] = None):
        self.cases_path = Path(cases_path) if cases_path else _DEFAULT_CASES_DIR / "travel_cases.json"
        self.cases: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """加载测试用例"""
        if not self.cases_path.exists():
            logger.warning(f"[EvalDataset] 数据文件不存在: {self.cases_path}")
            return

        try:
            with open(self.cases_path, "r", encoding="utf-8") as f:
                self.cases = json.load(f)
            logger.info(f"[EvalDataset] 加载了 {len(self.cases)} 个测试用例")
        except Exception as e:
            logger.error(f"[EvalDataset] 加载失败: {e}")

    def get_all(self) -> List[Dict[str, Any]]:
        """获取所有测试用例"""
        return self.cases

    def get_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按分类筛选"""
        return [c for c in self.cases if c.get("category") == category]

    def get_by_id(self, case_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取单个用例"""
        for c in self.cases:
            if c.get("id") == case_id:
                return c
        return None

    def get_categories(self) -> List[str]:
        """获取所有分类"""
        return list(set(c.get("category", "unknown") for c in self.cases))

    def __len__(self) -> int:
        return len(self.cases)

    def __iter__(self):
        return iter(self.cases)
