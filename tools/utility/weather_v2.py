"""
天气查询工具 V2 - 支持真实 MCP 调用
优先使用 MCP Server，失败时降级到模拟数据
"""
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from mcp_client import get_mcp_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_weather(city: str, use_mcp: bool = True) -> str:
    """
    查询天气信息

    Args:
        city: 城市名称
        use_mcp: 是否使用 MCP Server（默认 True）

    Returns:
        天气信息的 JSON 字符串
    """
    logger.info(f"[Tool] 查询天气: {city}")

    # 尝试使用 MCP Server
    if use_mcp:
        try:
            mcp = get_mcp_manager()
            result = mcp.call_tool(
                "weather",
                "get_forecast",
                {
                    "location": city,
                    "days": 7,
                    "units": "metric"
                }
            )

            logger.info(f"✅ 使用 MCP Server 获取天气成功")
            return json.dumps(result, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"MCP 调用失败，降级到模拟数据: {e}")

    # 降级：返回模拟数据
    return _get_mock_weather(city)


def _get_mock_weather(city: str) -> str:
    """
    模拟天气数据（MCP 失败时的降级方案）

    Args:
        city: 城市名称

    Returns:
        天气信息的 JSON 字符串
    """
    logger.info(f"使用模拟天气数据")

    weather_conditions = ["晴", "多云", "阴", "小雨", "中雨"]
    today = datetime.now()

    forecast = []
    for i in range(7):
        date = today + timedelta(days=i)
        forecast.append({
            "date": date.strftime("%Y-%m-%d"),
            "day_of_week": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][date.weekday()],
            "condition": random.choice(weather_conditions),
            "temperature": {
                "high": random.randint(20, 30),
                "low": random.randint(10, 20)
            },
            "humidity": random.randint(40, 80),
            "wind": f"{random.choice(['北风', '南风', '东风', '西风'])}{random.randint(1, 3)}级",
            "source": "mock_data"  # 标记为模拟数据
        })

    result = {
        "city": city,
        "current": forecast[0],
        "forecast_7days": forecast,
        "tips": [
            "紫外线较强，注意防晒",
            "早晚温差大，建议携带外套",
            "适合户外活动"
        ],
        "data_source": "mock"  # 标记数据来源
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


# ============ 测试代码 ============

if __name__ == "__main__":
    # 测试 1：使用 MCP
    print("\n" + "=" * 60)
    print("测试 1：使用 MCP Server 查询天气")
    print("=" * 60)
    result = get_weather("北京", use_mcp=True)
    print(result)

    # 测试 2：强制使用模拟数据
    print("\n" + "=" * 60)
    print("测试 2：使用模拟数据")
    print("=" * 60)
    result = get_weather("上海", use_mcp=False)
    print(result)
