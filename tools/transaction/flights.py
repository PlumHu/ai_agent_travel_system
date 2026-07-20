"""
机票搜索工具
优先通过 DuckDuckGo 搜索真实航班信息，失败时降级到静态参考数据
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)


def _search_flights_online(departure: str, arrival: str, date: str = None) -> List[Dict]:
    """使用 DuckDuckGo 搜索真实航班信息"""
    try:
        from duckduckgo_search import DDGS

        query = f"{departure}到{arrival}机票"
        if date:
            query += f" {date}"

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="cn-zh", max_results=8):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                    "source": "DuckDuckGo"
                })
        return results
    except Exception as e:
        logger.warning(f"DuckDuckGo 搜索失败: {e}")
        return []


def _mock_flights(departure: str, arrival: str) -> List[Dict]:
    """静态参考数据（仅在搜索失败时使用）"""
    return [
        {
            "note": "以下为参考数据，实际价格请以购票平台为准",
            "route": f"{departure} → {arrival}",
            "tips": [
                f"可在携程/去哪儿/飞猪搜索 {departure}到{arrival}机票",
                "提前21天购票通常可获较低价格",
                "周二、周三出发票价通常较低"
            ]
        }
    ]


def search_flights(
    departure: str,
    arrival: str,
    date: str = None,
    passengers: int = 1,
    cabin_class: str = "economy"
) -> str:
    """
    搜索航班信息。优先使用 DuckDuckGo 搜索真实数据，失败时返回参考建议。

    Args:
        departure: 出发城市
        arrival: 到达城市
        date: 出发日期（YYYY-MM-DD）
        passengers: 乘客人数
        cabin_class: 舱位（economy/business）
    """
    logger.info(f"[Tool] 搜索航班: {departure} -> {arrival}, 日期: {date}")

    search_results = _search_flights_online(departure, arrival, date)
    source = "DuckDuckGo"

    if not search_results:
        search_results = _mock_flights(departure, arrival)
        source = "参考数据（搜索不可用）"

    result = {
        "source": source,
        "query": {
            "departure": departure,
            "arrival": arrival,
            "date": date,
            "passengers": passengers,
            "cabin_class": cabin_class,
        },
        "results": search_results,
        "booking_channels": [
            "携程 https://www.ctrip.com",
            "去哪儿 https://www.qunar.com",
            "飞猪 https://www.fliggy.com",
        ],
    }

    logger.info(f"航班搜索完成，来源: {source}，结果数: {len(search_results)}")
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(search_flights("北京", "大理", "2026-07-01"))
