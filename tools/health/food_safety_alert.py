"""
食品安全预警工具
使用 DuckDuckGo 搜索目的地真实食品安全信息，失败时返回通用建议
"""
import json
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)

# 急救电话（固定）
EMERGENCY_NUMBERS = {"急救": "120", "报警": "110", "旅游投诉": "12301"}


def _search_online(destination: str, query_suffix: str) -> List[Dict]:
    """使用 DuckDuckGo 搜索"""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(f"{destination} {query_suffix}", region="cn-zh", max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                })
        return results
    except Exception as e:
        logger.warning(f"搜索失败: {e}")
        return []


def get_food_safety_alert(destination: str) -> str:
    """
    获取目的地食品安全预警。
    优先使用 DuckDuckGo 搜索真实信息，失败时给出通用建议。

    Args:
        destination: 目的地名称
    """
    logger.info(f"[Tool] 获取食品安全预警: {destination}")

    results = _search_online(destination, "食品安全 饮食注意 避免")
    source = "DuckDuckGo" if results else "搜索不可用"

    return json.dumps({
        "source": source,
        "destination": destination,
        "search_results": results,
        "general_precautions": [
            "选择卫生条件好的正规餐厅",
            "注意食物新鲜度，避免生冷食物",
            "野生菌等特殊食材必须煮熟",
            "保留消费凭证，方便维权",
        ],
        "emergency_numbers": EMERGENCY_NUMBERS,
    }, ensure_ascii=False, indent=2)


def get_emergency_info(destination: str) -> str:
    """
    获取目的地紧急医疗信息。
    使用 DuckDuckGo 搜索当地医院信息，失败时返回通用急救号码。

    Args:
        destination: 目的地
    """
    logger.info(f"[Tool] 获取紧急医疗信息: {destination}")

    results = _search_online(destination, "医院 急救 人民医院 地址电话")
    source = "DuckDuckGo" if results else "搜索不可用"

    return json.dumps({
        "source": source,
        "destination": destination,
        "hospitals": results,
        "emergency_numbers": EMERGENCY_NUMBERS,
        "tips": [
            "保留就诊记录和票据（旅游保险理赔需要）",
            "告知医生具体食用了什么食物",
        ],
    }, ensure_ascii=False, indent=2)


def check_food_hazard(food_type: str) -> str:
    """
    查询特定食物类型的安全风险。

    Args:
        food_type: 食物类型描述（如"野生菌"、"海鲜"）
    """
    logger.info(f"[Tool] 检查食物风险: {food_type}")

    results = _search_online(food_type, "食品安全 中毒 注意事项 预防")
    source = "DuckDuckGo" if results else "搜索不可用"

    return json.dumps({
        "source": source,
        "food_type": food_type,
        "safety_info": results,
        "first_aid": "如出现不适请立即拨打 120 急救电话",
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(get_food_safety_alert("大理"))
    print(get_emergency_info("三亚"))
