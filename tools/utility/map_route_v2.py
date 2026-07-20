"""
地图/路线规划工具 V2 - 支持百度地图 MCP
优先使用百度地图 MCP Server，失败时降级到模拟数据
"""
import json
import logging
from typing import Optional, Dict, Any

from mcp_client import get_mcp_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def search_place(query: str, city: str, use_mcp: bool = True) -> str:
    """
    搜索地点

    Args:
        query: 搜索关键词（如"餐厅"、"酒店"）
        city: 城市名称
        use_mcp: 是否使用 MCP Server

    Returns:
        搜索结果的 JSON 字符串
    """
    logger.info(f"[Tool] 搜索地点: {query} in {city}")

    if use_mcp:
        try:
            mcp = get_mcp_manager()
            result = mcp.call_tool(
                "baidu_maps",
                "place_search",
                {
                    "query": query,
                    "region": city,
                    "limit": 10
                }
            )

            logger.info(f"✅ 使用百度地图 MCP 搜索成功")
            return json.dumps(result, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"MCP 调用失败，降级到模拟数据: {e}")

    # 降级：返回模拟数据
    return _get_mock_places(query, city)


def get_route_suggestion(origin: str, destination: str, mode: str = "driving", use_mcp: bool = True) -> str:
    """
    获取路线规划建议

    Args:
        origin: 起点
        destination: 终点
        mode: 出行方式（driving/transit/walking/riding）
        use_mcp: 是否使用 MCP Server

    Returns:
        路线信息的 JSON 字符串
    """
    logger.info(f"[Tool] 路线规划: {origin} -> {destination} ({mode})")

    if use_mcp:
        try:
            mcp = get_mcp_manager()
            result = mcp.call_tool(
                "baidu_maps",
                "direction",
                {
                    "origin": origin,
                    "destination": destination,
                    "mode": mode
                }
            )

            logger.info(f"✅ 使用百度地图 MCP 规划成功")
            return json.dumps(result, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"MCP 调用失败，降级到模拟数据: {e}")

    # 降级：返回模拟数据
    return _get_mock_route(origin, destination, mode)


def geocoding(address: str, city: Optional[str] = None, use_mcp: bool = True) -> str:
    """
    地址解析（地址 → 坐标）

    Args:
        address: 地址
        city: 城市名称（可选）
        use_mcp: 是否使用 MCP Server

    Returns:
        坐标信息的 JSON 字符串
    """
    logger.info(f"[Tool] 地址解析: {address}")

    if use_mcp:
        try:
            mcp = get_mcp_manager()
            params = {"address": address}
            if city:
                params["city"] = city

            result = mcp.call_tool("baidu_maps", "geocoding", params)

            logger.info(f"✅ 使用百度地图 MCP 地址解析成功")
            return json.dumps(result, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"MCP 调用失败: {e}")

    return json.dumps({"error": "地址解析失败，MCP 不可用且无降级方案"}, ensure_ascii=False)


def _get_mock_places(query: str, city: str) -> str:
    """模拟地点搜索数据"""
    logger.info("使用模拟地点数据")

    mock_data = {
        "query": query,
        "region": city,
        "total": 3,
        "places": [
            {
                "name": f"{city}某某{query}",
                "address": f"{city}市中心大道123号",
                "location": {"lat": 39.915, "lng": 116.404},
                "tel": "010-12345678",
                "rating": 4.5
            },
            {
                "name": f"{city}推荐{query}",
                "address": f"{city}市人民路456号",
                "location": {"lat": 39.916, "lng": 116.405},
                "tel": "010-87654321",
                "rating": 4.3
            },
            {
                "name": f"{city}热门{query}",
                "address": f"{city}市建设街789号",
                "location": {"lat": 39.917, "lng": 116.406},
                "tel": "010-11112222",
                "rating": 4.7
            }
        ],
        "data_source": "mock"
    }

    return json.dumps(mock_data, ensure_ascii=False, indent=2)


def _get_mock_route(origin: str, destination: str, mode: str) -> str:
    """模拟路线规划数据"""
    logger.info("使用模拟路线数据")

    # 根据出行方式设置不同的时间和距离
    mock_configs = {
        "driving": {
            "distance": 15000,  # 15公里
            "duration": 1800,   # 30分钟
            "steps": 12,
            "description": "驾车"
        },
        "transit": {
            "distance": 16000,
            "duration": 2400,   # 40分钟
            "steps": 8,
            "description": "公交+地铁"
        },
        "walking": {
            "distance": 14000,
            "duration": 10800,  # 3小时
            "steps": 20,
            "description": "步行"
        },
        "riding": {
            "distance": 14500,
            "duration": 3600,   # 1小时
            "steps": 15,
            "description": "骑行"
        }
    }

    config = mock_configs.get(mode, mock_configs["driving"])

    mock_data = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "routes": [
            {
                "distance": config["distance"],
                "duration": config["duration"],
                "steps": config["steps"],
                "description": f"经由主干道，{config['description']}约{config['duration']//60}分钟"
            }
        ],
        "recommendation": f"推荐使用{config['description']}方式，预计{config['duration']//60}分钟到达",
        "data_source": "mock"
    }

    return json.dumps(mock_data, ensure_ascii=False, indent=2)


# ============ 测试代码 ============

if __name__ == "__main__":
    # 测试 1：搜索地点（MCP）
    print("\n" + "=" * 60)
    print("测试 1：使用百度地图 MCP 搜索地点")
    print("=" * 60)
    result = search_place("餐厅", "北京", use_mcp=True)
    print(result)

    # 测试 2：路线规划（MCP）
    print("\n" + "=" * 60)
    print("测试 2：使用百度地图 MCP 规划路线")
    print("=" * 60)
    result = get_route_suggestion("天安门", "故宫", "walking", use_mcp=True)
    print(result)

    # 测试 3：强制使用模拟数据
    print("\n" + "=" * 60)
    print("测试 3：使用模拟数据")
    print("=" * 60)
    result = search_place("酒店", "上海", use_mcp=False)
    print(result)
