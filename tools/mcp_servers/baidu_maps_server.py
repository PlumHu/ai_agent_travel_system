#!/usr/bin/env python3
"""
百度地图 MCP Server
提供地图搜索、路线规划、地点详情等功能
"""
import json
import sys
import os
import requests
from typing import Dict, Any, List


class BaiduMapsMCPServer:
    """百度地图 MCP Server"""

    def __init__(self):
        self.ak = os.getenv("BAIDU_MAPS_API_KEY", "")
        self.base_url = "https://api.map.baidu.com"

        # 定义工具
        self.tools = {
            "place_search": {
                "description": "搜索地点（POI）",
                "parameters": {
                    "query": {"type": "string", "required": True, "description": "搜索关键词"},
                    "region": {"type": "string", "required": True, "description": "城市名称"},
                    "limit": {"type": "integer", "default": 10, "description": "返回结果数量"}
                }
            },
            "geocoding": {
                "description": "地址解析（地址 → 坐标）",
                "parameters": {
                    "address": {"type": "string", "required": True, "description": "地址"},
                    "city": {"type": "string", "description": "城市名称"}
                }
            },
            "reverse_geocoding": {
                "description": "逆地址解析（坐标 → 地址）",
                "parameters": {
                    "lat": {"type": "number", "required": True, "description": "纬度"},
                    "lng": {"type": "number", "required": True, "description": "经度"}
                }
            },
            "direction": {
                "description": "路线规划",
                "parameters": {
                    "origin": {"type": "string", "required": True, "description": "起点（地址或坐标）"},
                    "destination": {"type": "string", "required": True, "description": "终点（地址或坐标）"},
                    "mode": {"type": "string", "default": "driving", "description": "出行方式：driving/transit/walking/riding"}
                }
            },
            "place_detail": {
                "description": "获取地点详情",
                "parameters": {
                    "uid": {"type": "string", "required": True, "description": "地点 UID"},
                    "scope": {"type": "integer", "default": 2, "description": "返回详细程度：1=基础信息，2=详细信息"}
                }
            },
            "district": {
                "description": "行政区划查询",
                "parameters": {
                    "keywords": {"type": "string", "required": True, "description": "区域名称"},
                    "sub_admin": {"type": "integer", "default": 0, "description": "是否返回下级行政区"}
                }
            }
        }

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理 JSON-RPC 请求"""
        method = request.get("method")
        params = request.get("params", {})

        if method == "tools/list":
            return self._list_tools()
        elif method == "tools/call":
            return self._call_tool(params)
        else:
            return {"error": f"未知方法: {method}"}

    def _list_tools(self) -> Dict[str, Any]:
        """列出所有可用工具"""
        return {
            "tools": [
                {
                    "name": name,
                    "description": tool["description"],
                    "inputSchema": {
                        "type": "object",
                        "properties": tool["parameters"]
                    }
                }
                for name, tool in self.tools.items()
            ]
        }

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not self.ak:
            return {"error": "缺少百度地图 API Key (BAIDU_MAPS_API_KEY)"}

        try:
            if tool_name == "place_search":
                return self._place_search(arguments)
            elif tool_name == "geocoding":
                return self._geocoding(arguments)
            elif tool_name == "reverse_geocoding":
                return self._reverse_geocoding(arguments)
            elif tool_name == "direction":
                return self._direction(arguments)
            elif tool_name == "place_detail":
                return self._place_detail(arguments)
            elif tool_name == "district":
                return self._district(arguments)
            else:
                return {"error": f"未知工具: {tool_name}"}

        except Exception as e:
            return {"error": f"API 调用失败: {str(e)}"}

    def _place_search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """地点搜索"""
        url = f"{self.base_url}/place/v2/search"
        params = {
            "ak": self.ak,
            "query": args.get("query"),
            "region": args.get("region"),
            "output": "json",
            "page_size": args.get("limit", 10)
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == 0:
            results = data.get("results", [])
            return {
                "total": data.get("total", 0),
                "places": [
                    {
                        "name": place.get("name"),
                        "address": place.get("address"),
                        "province": place.get("province"),
                        "city": place.get("city"),
                        "area": place.get("area"),
                        "location": place.get("location"),
                        "uid": place.get("uid"),
                        "tel": place.get("telephone"),
                        "detail_url": place.get("detail_info", {}).get("detail_url")
                    }
                    for place in results
                ]
            }
        else:
            return {"error": f"百度地图 API 错误: {data.get('message')}"}

    def _geocoding(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """地址解析"""
        url = f"{self.base_url}/geocoding/v3/"
        params = {
            "ak": self.ak,
            "address": args.get("address"),
            "city": args.get("city", ""),
            "output": "json"
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == 0:
            result = data.get("result", {})
            return {
                "location": result.get("location"),
                "precise": result.get("precise"),
                "confidence": result.get("confidence"),
                "comprehension": result.get("comprehension"),
                "level": result.get("level")
            }
        else:
            return {"error": f"百度地图 API 错误: {data.get('message')}"}

    def _reverse_geocoding(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """逆地址解析"""
        url = f"{self.base_url}/reverse_geocoding/v3/"
        params = {
            "ak": self.ak,
            "location": f"{args.get('lat')},{args.get('lng')}",
            "output": "json"
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == 0:
            result = data.get("result", {})
            return {
                "formatted_address": result.get("formatted_address"),
                "business": result.get("business"),
                "addressComponent": result.get("addressComponent"),
                "pois": result.get("pois", []),
                "sematic_description": result.get("sematic_description")
            }
        else:
            return {"error": f"百度地图 API 错误: {data.get('message')}"}

    def _direction(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """路线规划"""
        mode = args.get("mode", "driving")

        # 根据模式选择 API 端点
        api_map = {
            "driving": "/directionlite/v1/driving",
            "transit": "/directionlite/v1/transit",
            "walking": "/directionlite/v1/walking",
            "riding": "/directionlite/v1/riding"
        }

        url = f"{self.base_url}{api_map.get(mode, api_map['driving'])}"
        params = {
            "ak": self.ak,
            "origin": args.get("origin"),
            "destination": args.get("destination"),
            "output": "json"
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == 0:
            result = data.get("result", {})
            routes = result.get("routes", [])

            return {
                "mode": mode,
                "origin": result.get("origin"),
                "destination": result.get("destination"),
                "routes": [
                    {
                        "distance": route.get("distance"),  # 米
                        "duration": route.get("duration"),  # 秒
                        "steps": len(route.get("steps", [])),
                        "toll": route.get("toll"),  # 过路费（驾车）
                        "traffic_condition": route.get("traffic_condition")  # 路况
                    }
                    for route in routes
                ]
            }
        else:
            return {"error": f"百度地图 API 错误: {data.get('message')}"}

    def _place_detail(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """地点详情"""
        url = f"{self.base_url}/place/v2/detail"
        params = {
            "ak": self.ak,
            "uid": args.get("uid"),
            "scope": args.get("scope", 2),
            "output": "json"
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == 0:
            result = data.get("result", {})
            return {
                "name": result.get("name"),
                "address": result.get("address"),
                "location": result.get("location"),
                "telephone": result.get("telephone"),
                "detail_info": result.get("detail_info", {}),
                "tag": result.get("tag"),
                "type": result.get("type"),
                "alias": result.get("alias")
            }
        else:
            return {"error": f"百度地图 API 错误: {data.get('message')}"}

    def _district(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """行政区划查询"""
        url = f"{self.base_url}/api_region_search/v1/"
        params = {
            "ak": self.ak,
            "keyword": args.get("keywords"),
            "sub_admin": args.get("sub_admin", 0),
            "output": "json"
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") == 0:
            districts = data.get("districts", [])
            return {
                "total": len(districts),
                "districts": [
                    {
                        "name": d.get("name"),
                        "adcode": d.get("adcode"),
                        "level": d.get("level"),
                        "center": d.get("center")
                    }
                    for d in districts
                ]
            }
        else:
            return {"error": f"百度地图 API 错误: {data.get('message')}"}

    def run(self):
        """运行 MCP Server"""
        print("百度地图 MCP Server 已启动", file=sys.stderr)

        for line in sys.stdin:
            try:
                request = json.loads(line)
                response = self.handle_request(request)

                # 构造 JSON-RPC 响应
                result = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": response
                }

                print(json.dumps(result))
                sys.stdout.flush()

            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id") if "request" in locals() else None,
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    }
                }
                print(json.dumps(error_response))
                sys.stdout.flush()


if __name__ == "__main__":
    server = BaiduMapsMCPServer()
    server.run()
