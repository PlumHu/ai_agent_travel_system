"""
当地特色体验工具
优先从本地数据读取，未找到时使用 DuckDuckGo 搜索真实信息
"""
import json
import logging
from typing import List, Dict
from pathlib import Path

from config import RAW_DATA_PATH

logger = logging.getLogger(__name__)


def _search_online(destination: str, query_suffix: str = "特色体验 非遗") -> List[Dict]:
    """使用 DuckDuckGo 搜索特色体验信息"""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(f"{destination} {query_suffix}", region="cn-zh", max_results=6):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                })
        return results
    except Exception as e:
        logger.warning(f"DuckDuckGo 搜索失败: {e}")
        return []


def get_local_features(destination: str) -> str:
    """
    获取目的地特色体验信息。
    优先从本地文件读取，未找到时使用 DuckDuckGo 搜索。

    Args:
        destination: 目的地名称
    """
    logger.info(f"[Tool] 查询特色体验: {destination}")

    # 1. 本地文件
    features_file = RAW_DATA_PATH / "features" / f"{destination}.json"
    if features_file.exists():
        try:
            with open(features_file, "r", encoding="utf-8") as f:
                return json.dumps({"source": "本地数据", "data": json.load(f)}, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"读取特色文件失败: {e}")

    # 2. DuckDuckGo 搜索
    results = _search_online(destination, "特色体验 必玩 非遗文化")
    if results:
        logger.info(f"DuckDuckGo 搜索特色体验成功: {destination}")
        return json.dumps({
            "source": "DuckDuckGo",
            "destination": destination,
            "features": results,
        }, ensure_ascii=False, indent=2)

    # 3. 兜底
    return json.dumps({
        "destination": destination,
        "message": "暂无详细特色体验信息",
        "suggestions": [
            "建议在马蜂窝、穷游查看游记",
            "可咨询当地旅游局了解特色活动",
        ],
    }, ensure_ascii=False, indent=2)


def get_intangible_heritage(destination: str) -> str:
    """
    搜索目的地非物质文化遗产信息。

    Args:
        destination: 目的地名称
    """
    logger.info(f"[Tool] 查询非物质文化遗产: {destination}")

    results = _search_online(destination, "非物质文化遗产 传统技艺")
    source = "DuckDuckGo" if results else "搜索不可用"

    if not results:
        results = [{"note": f"请搜索 {destination}非物质文化遗产 获取详细信息"}]

    return json.dumps({
        "source": source,
        "destination": destination,
        "heritage": results,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(get_local_features("大理"))
