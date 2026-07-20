"""
酒店搜索工具
优先通过 DuckDuckGo 搜索真实酒店信息，失败时降级到静态参考数据
"""
import json
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


def _search_hotels_online(destination: str, check_in: str = None, check_out: str = None) -> List[Dict]:
    """使用 DuckDuckGo 搜索真实酒店信息"""
    try:
        from duckduckgo_search import DDGS

        query = f"{destination}酒店推荐 民宿"
        if check_in:
            query += f" {check_in}"

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


def _mock_hotels(destination: str) -> List[Dict]:
    """静态参考数据（仅在搜索失败时使用）"""
    return [
        {
            "note": "以下为参考数据，实际价格和可用性请以预订平台为准",
            "destination": destination,
            "tips": [
                f"可在携程/美团/Booking搜索 {destination}酒店",
                "入住古城或景区附近交通最方便",
                "提前2-4周预订价格更优惠"
            ]
        }
    ]


def search_hotels(
    destination: str,
    check_in: str = None,
    check_out: str = None,
    guests: int = 2,
    rooms: int = 1,
    price_level: str = "all"
) -> str:
    """
    搜索酒店信息。优先使用 DuckDuckGo 搜索真实数据，失败时返回参考建议。

    Args:
        destination: 目的地城市
        check_in: 入住日期（YYYY-MM-DD）
        check_out: 离店日期（YYYY-MM-DD）
        guests: 入住人数
        rooms: 房间数
        price_level: 价格档次（budget/medium/luxury/all）
    """
    logger.info(f"[Tool] 搜索酒店: {destination}, 入住: {check_in}, 离店: {check_out}")

    nights = 1
    if check_in and check_out:
        try:
            nights = max(1, (datetime.strptime(check_out, "%Y-%m-%d") - datetime.strptime(check_in, "%Y-%m-%d")).days)
        except Exception:
            pass

    search_results = _search_hotels_online(destination, check_in, check_out)
    source = "DuckDuckGo"

    if not search_results:
        search_results = _mock_hotels(destination)
        source = "参考数据（搜索不可用）"

    result = {
        "source": source,
        "query": {
            "destination": destination,
            "check_in": check_in,
            "check_out": check_out,
            "nights": nights,
            "guests": guests,
            "rooms": rooms,
            "price_level": price_level,
        },
        "results": search_results,
        "booking_channels": [
            "携程 https://www.ctrip.com",
            "美团 https://www.meituan.com",
            "Booking https://www.booking.com",
        ],
    }

    logger.info(f"酒店搜索完成，来源: {source}，结果数: {len(search_results)}")
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(search_hotels("大理", "2026-07-01", "2026-07-03"))
