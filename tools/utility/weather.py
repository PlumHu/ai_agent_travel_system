"""
天气查询工具
优先调用 OpenWeather API，失败时降级到模拟数据
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# 城市英文名映射（OpenWeather 需要英文城市名）
CITY_NAME_MAP = {
    "大理": "Dali,CN",
    "丽江": "Lijiang,CN",
    "三亚": "Sanya,CN",
    "北京": "Beijing,CN",
    "上海": "Shanghai,CN",
    "广州": "Guangzhou,CN",
    "成都": "Chengdu,CN",
    "杭州": "Hangzhou,CN",
    "西安": "Xi'an,CN",
    "桂林": "Guilin,CN",
    "昆明": "Kunming,CN",
    "厦门": "Xiamen,CN",
}

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5"


def _query_openweather(city_query: str, api_key: str) -> Optional[dict]:
    """调用 OpenWeather API 获取当前天气 + 5天预报"""
    try:
        # 当前天气
        curr_resp = requests.get(
            f"{OPENWEATHER_BASE}/weather",
            params={"q": city_query, "appid": api_key, "units": "metric", "lang": "zh_cn"},
            timeout=10,
        )
        curr_resp.raise_for_status()
        curr = curr_resp.json()

        # 5天预报（每3小时一条）
        fc_resp = requests.get(
            f"{OPENWEATHER_BASE}/forecast",
            params={"q": city_query, "appid": api_key, "units": "metric", "lang": "zh_cn", "cnt": 40},
            timeout=10,
        )
        fc_resp.raise_for_status()
        fc_data = fc_resp.json()

        # 按日期汇总预报
        daily: dict = {}
        for item in fc_data.get("list", []):
            date_str = item["dt_txt"][:10]
            if date_str not in daily:
                daily[date_str] = {"temps": [], "conditions": [], "pops": []}
            daily[date_str]["temps"].append(item["main"]["temp"])
            daily[date_str]["conditions"].append(item["weather"][0]["description"])
            daily[date_str]["pops"].append(item.get("pop", 0))

        forecast_7days = []
        for date_str, info in list(daily.items())[:7]:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            forecast_7days.append({
                "date": date_str,
                "day_of_week": WEEKDAYS[d.weekday()],
                "condition": max(set(info["conditions"]), key=info["conditions"].count),
                "temperature": {
                    "high": round(max(info["temps"]), 1),
                    "low": round(min(info["temps"]), 1),
                },
                "humidity": curr["main"]["humidity"],
                "rain_chance": f"{round(max(info['pops']) * 100)}%",
            })

        return {
            "source": "OpenWeather API",
            "city": curr["name"],
            "current": {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "day_of_week": WEEKDAYS[datetime.now().weekday()],
                "condition": curr["weather"][0]["description"],
                "temperature": {
                    "high": round(curr["main"]["temp_max"], 1),
                    "low": round(curr["main"]["temp_min"], 1),
                },
                "humidity": curr["main"]["humidity"],
                "wind": f"{round(curr['wind']['speed'], 1)} m/s",
            },
            "forecast_7days": forecast_7days,
            "tips": _build_tips(curr),
        }
    except Exception as e:
        logger.warning(f"OpenWeather API 请求失败: {e}")
        return None


def _build_tips(curr: dict) -> list:
    tips = []
    temp = curr["main"]["temp"]
    if temp >= 30:
        tips.append("天气炎热，注意防晒补水")
    elif temp <= 10:
        tips.append("气温较低，注意保暖")
    else:
        tips.append("气温适宜，适合户外活动")
    if curr["main"]["humidity"] >= 80:
        tips.append("湿度较高，注意防潮")
    weather_main = curr["weather"][0]["main"]
    if weather_main in ("Rain", "Drizzle", "Thunderstorm"):
        tips.append("有降雨，建议携带雨具")
    elif weather_main == "Clear":
        tips.append("晴天紫外线较强，注意防晒")
    return tips


def _mock_weather(city: str) -> dict:
    """API 不可用时的模拟降级数据"""
    today = datetime.now()
    forecast = []
    for i in range(7):
        d = today + timedelta(days=i)
        forecast.append({
            "date": d.strftime("%Y-%m-%d"),
            "day_of_week": WEEKDAYS[d.weekday()],
            "condition": "晴" if i % 3 != 2 else "多云",
            "temperature": {"high": 25, "low": 15},
            "humidity": 60,
            "rain_chance": "10%",
        })
    return {
        "source": "模拟数据（API 不可用）",
        "city": city,
        "current": forecast[0],
        "forecast_7days": forecast,
        "tips": ["建议出行前查询实时天气"],
    }


def get_weather(city: str) -> str:
    """
    查询天气信息。优先调用 OpenWeather API，失败时使用模拟数据。

    Args:
        city: 城市名称（中文或英文）

    Returns:
        天气信息的 JSON 字符串
    """
    logger.info(f"[Tool] 查询天气: {city}")

    api_key = os.getenv("OPENWEATHER_API_KEY", "")
    city_query = CITY_NAME_MAP.get(city, city)

    result = None
    if api_key:
        result = _query_openweather(city_query, api_key)
    else:
        logger.warning("未配置 OPENWEATHER_API_KEY，使用模拟数据")

    if result is None:
        result = _mock_weather(city)

    logger.info(f"天气查询完成: {city} (来源: {result['source']})")
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(get_weather("大理"))
