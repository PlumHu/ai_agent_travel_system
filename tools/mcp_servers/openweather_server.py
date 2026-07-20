#!/usr/bin/env python3
"""
OpenWeather MCP Server
提供天气查询功能的 MCP 服务器
"""
import os
import sys
import json
import logging
from typing import Dict, Any, List
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OpenWeatherMCPServer:
    """OpenWeather MCP Server"""

    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.base_url = "https://api.openweathermap.org/data/2.5"

        self.tools = {
            "current_weather": {
                "name": "current_weather",
                "description": "获取指定城市的当前天气信息",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称（英文或拼音）"
                        },
                        "country": {
                            "type": "string",
                            "description": "国家代码（可选，如 CN, US）"
                        },
                        "units": {
                            "type": "string",
                            "description": "单位系统：metric（摄氏度）或 imperial（华氏度）",
                            "enum": ["metric", "imperial"],
                            "default": "metric"
                        }
                    },
                    "required": ["city"]
                }
            },
            "weather_forecast": {
                "name": "weather_forecast",
                "description": "获取指定城市的5天天气预报（每3小时一次）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称（英文或拼音）"
                        },
                        "country": {
                            "type": "string",
                            "description": "国家代码（可选，如 CN, US）"
                        },
                        "units": {
                            "type": "string",
                            "description": "单位系统：metric（摄氏度）或 imperial（华氏度）",
                            "enum": ["metric", "imperial"],
                            "default": "metric"
                        }
                    },
                    "required": ["city"]
                }
            },
            "weather_by_coordinates": {
                "name": "weather_by_coordinates",
                "description": "根据经纬度获取当前天气",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "lat": {
                            "type": "number",
                            "description": "纬度"
                        },
                        "lon": {
                            "type": "number",
                            "description": "经度"
                        },
                        "units": {
                            "type": "string",
                            "description": "单位系统",
                            "enum": ["metric", "imperial"],
                            "default": "metric"
                        }
                    },
                    "required": ["lat", "lon"]
                }
            }
        }

    def _current_weather(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """获取当前天气"""
        city = args.get("city")
        country = args.get("country")
        units = args.get("units", "metric")

        # 构建查询字符串
        q = f"{city},{country}" if country else city

        url = f"{self.base_url}/weather"
        params = {
            "q": q,
            "appid": self.api_key,
            "units": units,
            "lang": "zh_cn"
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # 格式化返回结果
            result = {
                "city": data.get("name"),
                "country": data.get("sys", {}).get("country"),
                "temperature": data.get("main", {}).get("temp"),
                "feels_like": data.get("main", {}).get("feels_like"),
                "temp_min": data.get("main", {}).get("temp_min"),
                "temp_max": data.get("main", {}).get("temp_max"),
                "humidity": data.get("main", {}).get("humidity"),
                "pressure": data.get("main", {}).get("pressure"),
                "weather": data.get("weather", [{}])[0].get("description"),
                "wind_speed": data.get("wind", {}).get("speed"),
                "clouds": data.get("clouds", {}).get("all"),
                "visibility": data.get("visibility"),
                "dt": data.get("dt"),
                "timezone": data.get("timezone")
            }

            return {"success": True, "data": result}

        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {e}")
            return {"success": False, "error": str(e)}

    def _weather_forecast(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """获取天气预报"""
        city = args.get("city")
        country = args.get("country")
        units = args.get("units", "metric")

        q = f"{city},{country}" if country else city

        url = f"{self.base_url}/forecast"
        params = {
            "q": q,
            "appid": self.api_key,
            "units": units,
            "lang": "zh_cn"
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # 格式化预报列表
            forecasts = []
            for item in data.get("list", [])[:16]:  # 只返回前48小时
                forecasts.append({
                    "dt": item.get("dt"),
                    "dt_txt": item.get("dt_txt"),
                    "temperature": item.get("main", {}).get("temp"),
                    "feels_like": item.get("main", {}).get("feels_like"),
                    "temp_min": item.get("main", {}).get("temp_min"),
                    "temp_max": item.get("main", {}).get("temp_max"),
                    "humidity": item.get("main", {}).get("humidity"),
                    "weather": item.get("weather", [{}])[0].get("description"),
                    "clouds": item.get("clouds", {}).get("all"),
                    "wind_speed": item.get("wind", {}).get("speed"),
                    "pop": item.get("pop")  # 降水概率
                })

            result = {
                "city": data.get("city", {}).get("name"),
                "country": data.get("city", {}).get("country"),
                "forecasts": forecasts
            }

            return {"success": True, "data": result}

        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {e}")
            return {"success": False, "error": str(e)}

    def _weather_by_coordinates(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """根据坐标获取天气"""
        lat = args.get("lat")
        lon = args.get("lon")
        units = args.get("units", "metric")

        url = f"{self.base_url}/weather"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key,
            "units": units,
            "lang": "zh_cn"
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            result = {
                "city": data.get("name"),
                "country": data.get("sys", {}).get("country"),
                "coordinates": {"lat": lat, "lon": lon},
                "temperature": data.get("main", {}).get("temp"),
                "feels_like": data.get("main", {}).get("feels_like"),
                "humidity": data.get("main", {}).get("humidity"),
                "weather": data.get("weather", [{}])[0].get("description"),
                "wind_speed": data.get("wind", {}).get("speed")
            }

            return {"success": True, "data": result}

        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {e}")
            return {"success": False, "error": str(e)}

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理 JSON-RPC 请求"""
        method = request.get("method")
        params = request.get("params", {})

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {"tools": list(self.tools.values())}
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "current_weather":
                result = self._current_weather(arguments)
            elif tool_name == "weather_forecast":
                result = self._weather_forecast(arguments)
            elif tool_name == "weather_by_coordinates":
                result = self._weather_by_coordinates(arguments)
            else:
                result = {"success": False, "error": f"未知工具: {tool_name}"}

            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32601, "message": f"未知方法: {method}"}
            }

    def run(self):
        """运行 MCP 服务器（JSON-RPC over stdio）"""
        logger.info("OpenWeather MCP Server 启动...")

        if not self.api_key:
            logger.warning("警告: 未设置 OPENWEATHER_API_KEY 环境变量")

        for line in sys.stdin:
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                print(json.dumps(response), flush=True)
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析错误: {e}")
            except Exception as e:
                logger.error(f"处理请求时出错: {e}", exc_info=True)


def test_server():
    """测试服务器功能"""
    server = OpenWeatherMCPServer()

    print("=" * 60)
    print("OpenWeather MCP Server 测试")
    print("=" * 60)

    # 检查 API Key
    if not server.api_key:
        print("\n❌ 错误: 未设置 OPENWEATHER_API_KEY 环境变量")
        print("请在 .env 文件中设置: OPENWEATHER_API_KEY=your_api_key")
        return False

    print(f"\n✓ API Key 已配置: {server.api_key[:10]}...")

    # 测试获取北京天气
    print("\n测试 1: 获取北京当前天气")
    print("-" * 60)
    result = server._current_weather({"city": "Beijing", "country": "CN", "units": "metric"})

    if result.get("success"):
        data = result["data"]
        print(f"✓ 城市: {data.get('city')}, {data.get('country')}")
        print(f"✓ 温度: {data.get('temperature')}°C")
        print(f"✓ 体感: {data.get('feels_like')}°C")
        print(f"✓ 湿度: {data.get('humidity')}%")
        print(f"✓ 天气: {data.get('weather')}")
        print(f"✓ 风速: {data.get('wind_speed')} m/s")
    else:
        print(f"❌ 请求失败: {result.get('error')}")
        return False

    # 测试天气预报
    print("\n测试 2: 获取上海天气预报")
    print("-" * 60)
    result = server._weather_forecast({"city": "Shanghai", "country": "CN", "units": "metric"})

    if result.get("success"):
        data = result["data"]
        print(f"✓ 城市: {data.get('city')}, {data.get('country')}")
        print(f"✓ 预报数据点数: {len(data.get('forecasts', []))}")

        # 显示前3个预报
        for i, forecast in enumerate(data.get("forecasts", [])[:3], 1):
            print(f"\n  [{i}] {forecast.get('dt_txt')}")
            print(f"      温度: {forecast.get('temperature')}°C, 天气: {forecast.get('weather')}")
    else:
        print(f"❌ 请求失败: {result.get('error')}")
        return False

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！OpenWeather MCP Server 工作正常")
    print("=" * 60)
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # 加载 .env 文件
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        success = test_server()
        sys.exit(0 if success else 1)
    else:
        server = OpenWeatherMCPServer()
        server.run()
