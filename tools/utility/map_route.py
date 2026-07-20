"""
路线规划工具
优先路由到 map_route_v2（百度地图 MCP），失败时使用 DuckDuckGo 搜索，
最终降级到通用交通建议。
"""
import json
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def _search_route_online(origin: str, destination: str) -> List[Dict]:
    """使用 DuckDuckGo 搜索路线信息"""
    try:
        from duckduckgo_search import DDGS
        query = f"{origin}到{destination}怎么去 交通攻略 飞机高铁"
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="cn-zh", max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                    "source": "DuckDuckGo"
                })
        return results
    except Exception as e:
        logger.warning(f"DuckDuckGo 路线搜索失败: {e}")
        return []


def _generic_fallback(origin: str, destination: str) -> Dict:
    """通用交通建议（最终兜底，不含硬编码时长/价格）"""
    return {
        "route": f"{origin} → {destination}",
        "note": "以下为通用交通方式建议，实际时长和价格请以购票平台为准",
        "transportation_options": [
            {
                "type": "飞机",
                "booking_tips": f"可在携程/去哪儿/飞猪搜索 {origin}到{destination}机票",
                "pros": ["速度最快"],
                "cons": ["价格较高", "需提前到机场"]
            },
            {
                "type": "高铁/火车",
                "booking_tips": "可在 12306.cn 查询余票并购票",
                "pros": ["准时稳定", "市区内接驳方便"],
                "cons": ["部分线路耗时较长"]
            },
            {
                "type": "自驾",
                "booking_tips": "可通过高德地图/百度地图规划自驾路线",
                "pros": ["自由灵活", "可沿途游览"],
                "cons": ["长途驾驶疲劳"]
            }
        ],
        "reference_links": [
            f"https://www.ctrip.com/search?keyword={origin}到{destination}",
            "https://www.12306.cn"
        ],
        "data_source": "通用建议（降级）"
    }


def get_route_suggestion(route: str) -> str:
    """
    获取路线规划建议。

    优先尝试百度地图 MCP（map_route_v2），失败时用 DuckDuckGo 搜索，
    最终降级为通用交通建议。

    Args:
        route: 路线描述，如 "北京到大理" 或 "北京,大理"

    Returns:
        路线建议的 JSON 字符串
    """
    logger.info(f"[Tool] 路线规划: {route}")

    # 解析起终点
    origin, destination = _parse_route(route)

    # 层 1：尝试 map_route_v2（百度地图 MCP）
    try:
        from tools.utility.map_route_v2 import get_route_suggestion as mcp_route
        result_str = mcp_route(origin, destination)
        result = json.loads(result_str)
        if result.get("data_source") != "mock":
            logger.info("路线规划使用百度地图 MCP 成功")
            return result_str
    except Exception as e:
        logger.warning(f"百度地图 MCP 调用失败: {e}")

    # 层 2：DuckDuckGo 搜索
    search_results = _search_route_online(origin, destination)
    if search_results:
        logger.info(f"路线规划使用 DuckDuckGo 搜索，结果数: {len(search_results)}")
        result = {
            "route": f"{origin} → {destination}",
            "data_source": "DuckDuckGo",
            "search_results": search_results,
            "booking_tips": [
                f"携程机票: https://www.ctrip.com",
                f"高铁: https://www.12306.cn",
                f"高德地图自驾: https://amap.com"
            ]
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    # 层 3：通用兜底
    logger.warning("所有路线查询方式失败，使用通用建议")
    return json.dumps(_generic_fallback(origin, destination), ensure_ascii=False, indent=2)


def _parse_route(route: str):
    """从路线描述中提取起终点"""
    for sep in ["到", "→", "->", "-", ",", "，"]:
        if sep in route:
            parts = route.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    # 无法解析时整体作为目的地
    return "出发地", route.strip()


if __name__ == "__main__":
    print(get_route_suggestion("北京到大理"))
