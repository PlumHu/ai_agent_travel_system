"""
门票和活动搜索工具
优先通过 DuckDuckGo 搜索真实门票信息，失败时降级到静态参考数据
"""
import json
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def _search_tickets_online(destination: str, date: str = None) -> List[Dict]:
    """使用 DuckDuckGo 搜索真实门票信息"""
    try:
        from duckduckgo_search import DDGS

        query = f"{destination}景点门票 攻略"
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


def _mock_tickets(destination: str) -> List[Dict]:
    """静态参考数据（仅在搜索失败时使用）"""
    return [
        {
            "note": "以下为参考数据，实际价格请以官方渠道为准",
            "destination": destination,
            "tips": [
                f"可在携程/美团/去哪儿搜索 {destination}景点门票",
                "部分景点可在微信小程序或官方App预订",
                "节假日热门景点建议提前3-7天预订"
            ]
        }
    ]


def search_tickets(
    destination: str,
    date: str = None,
    adults: int = 2,
    children: int = 0
) -> str:
    """
    搜索景点门票。优先使用 DuckDuckGo 搜索真实数据，失败时返回参考建议。

    Args:
        destination: 目的地
        date: 游玩日期（YYYY-MM-DD）
        adults: 成人数量
        children: 儿童数量
    """
    logger.info(f"[Tool] 搜索门票: {destination}, 日期: {date}")

    search_results = _search_tickets_online(destination, date)
    source = "DuckDuckGo"

    if not search_results:
        search_results = _mock_tickets(destination)
        source = "参考数据（搜索不可用）"

    result = {
        "source": source,
        "query": {
            "destination": destination,
            "date": date,
            "adults": adults,
            "children": children,
        },
        "results": search_results,
        "booking_channels": [
            "携程 https://www.ctrip.com",
            "美团 https://www.meituan.com",
            "去哪儿 https://www.qunar.com",
        ],
    }

    logger.info(f"门票搜索完成，来源: {source}，结果数: {len(search_results)}")
    return json.dumps(result, ensure_ascii=False, indent=2)


def get_popular_activities(destination: str, category: str = "all") -> str:
    """
    搜索目的地热门活动。

    Args:
        destination: 目的地
        category: 活动类型（all/户外/文化/水上）
    """
    logger.info(f"[Tool] 获取热门活动: {destination}, 类型: {category}")

    query_map = {
        "户外": f"{destination}户外活动 徒步骑行",
        "文化": f"{destination}文化体验 非遗",
        "水上": f"{destination}水上运动 潜水",
        "all": f"{destination}特色活动 推荐体验",
    }
    query = query_map.get(category, query_map["all"])

    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="cn-zh", max_results=6):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                })
        source = "DuckDuckGo"
    except Exception as e:
        logger.warning(f"活动搜索失败: {e}")
        results = [{"note": f"请在携程/马蜂窝搜索 {destination}{category}活动"}]
        source = "参考数据"

    return json.dumps({
        "source": source,
        "destination": destination,
        "category": category,
        "activities": results,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(search_tickets("大理", "2026-07-01"))
