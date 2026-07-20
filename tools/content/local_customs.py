"""
当地风俗禁忌工具
优先从本地数据读取，未找到时使用 DuckDuckGo 搜索真实信息
"""
import json
import logging
from typing import List, Dict
from pathlib import Path

from config import RAW_DATA_PATH

logger = logging.getLogger(__name__)


def _search_online(destination: str) -> List[Dict]:
    """使用 DuckDuckGo 搜索风俗禁忌信息"""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(f"{destination}风俗习惯 禁忌 注意事项", region="cn-zh", max_results=6):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                })
        return results
    except Exception as e:
        logger.warning(f"DuckDuckGo 搜索失败: {e}")
        return []


def get_local_customs(destination: str) -> str:
    """
    获取目的地风俗禁忌信息。
    优先从本地 JSON 文件读取，未找到时使用 DuckDuckGo 搜索。

    Args:
        destination: 目的地名称
    """
    logger.info(f"[Tool] 查询风俗禁忌: {destination}")

    # 1. 本地文件
    customs_file = RAW_DATA_PATH / "customs" / f"{destination}.json"
    if customs_file.exists():
        try:
            with open(customs_file, "r", encoding="utf-8") as f:
                return json.dumps({"source": "本地数据", "data": json.load(f)}, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"读取风俗文件失败: {e}")

    # 2. DuckDuckGo 搜索
    results = _search_online(destination)
    if results:
        logger.info(f"DuckDuckGo 搜索风俗信息成功: {destination}")
        return json.dumps({
            "source": "DuckDuckGo",
            "destination": destination,
            "customs_info": results,
            "general_tips": [
                "尊重当地宗教信仰，寺庙内保持安静",
                "着装得体，特别是宗教场所",
                "拍照前征得当地人同意",
                "保护环境，不乱丢垃圾",
            ],
        }, ensure_ascii=False, indent=2)

    # 3. 兜底
    return json.dumps({
        "destination": destination,
        "message": "暂无详细风俗信息",
        "general_tips": [
            "出行前了解当地文化习俗",
            "尊重当地宗教信仰",
            "着装得体，特别是宗教场所",
        ],
    }, ensure_ascii=False, indent=2)


def get_festival_calendar(destination: str, year: int = None) -> str:
    """
    搜索目的地节日日历。

    Args:
        destination: 目的地名称
        year: 年份（默认当前年份）
    """
    import datetime
    if year is None:
        year = datetime.datetime.now().year

    logger.info(f"[Tool] 查询节日日历: {destination}, {year}年")

    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(f"{destination} {year}年节日 传统节庆", region="cn-zh", max_results=6):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                })
        source = "DuckDuckGo"
    except Exception as e:
        logger.warning(f"节日搜索失败: {e}")
        results = []
        source = "搜索不可用"

    return json.dumps({
        "source": source,
        "destination": destination,
        "year": year,
        "festivals": results,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(get_local_customs("大理"))
