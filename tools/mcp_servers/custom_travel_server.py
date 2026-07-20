#!/usr/bin/env python3
"""
自定义 MCP Server
提供旅行数据相关的工具，目的地信息优先从 knowledge/raw_data/destinations/ 读取真实 JSON 数据。
"""
import json
import sys
import re
from pathlib import Path
from typing import Dict, Any, List

# 知识库路径
_ROOT = Path(__file__).parent.parent.parent
_DEST_DIR = _ROOT / "knowledge" / "raw_data" / "destinations"

# 中文名 → 文件名映射（可扩展）
_NAME_MAP = {
    "大理": "dali",
    "丽江": "lijiang",
    "三亚": "sanya",
}


def _load_destination(name: str) -> Dict:
    """从本地 JSON 文件加载目的地数据，失败返回空字典"""
    candidates = [
        _DEST_DIR / f"{name}.json",
        _DEST_DIR / f"{_NAME_MAP.get(name, name)}.json",
        _DEST_DIR / f"{name.lower()}.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


class TravelMCPServer:
    """自定义旅行数据 MCP Server"""

    def __init__(self):
        self.tools = {
            "get_destination_info": {
                "description": "获取目的地详细信息（景点、美食、住宿、交通等）",
                "parameters": {
                    "destination": {"type": "string", "required": True}
                }
            },
            "calculate_budget": {
                "description": "计算旅行预算",
                "parameters": {
                    "destination": {"type": "string", "required": True},
                    "days": {"type": "integer", "required": True},
                    "people": {"type": "integer", "default": 1}
                }
            },
            "recommend_route": {
                "description": "推荐旅行路线",
                "parameters": {
                    "start": {"type": "string", "required": True},
                    "end": {"type": "string", "required": True},
                    "transport": {"type": "string", "default": "all"}
                }
            }
        }

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method = request.get("method")
        params = request.get("params", {})
        if method == "tools/list":
            return self._list_tools()
        elif method == "tools/call":
            return self._call_tool(params)
        return {"error": f"未知方法: {method}"}

    def _list_tools(self) -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": name,
                    "description": tool["description"],
                    "inputSchema": {"type": "object", "properties": tool["parameters"]}
                }
                for name, tool in self.tools.items()
            ]
        }

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        dispatch = {
            "get_destination_info": self._get_destination_info,
            "calculate_budget": self._calculate_budget,
            "recommend_route": self._recommend_route,
        }
        fn = dispatch.get(tool_name)
        if fn:
            return fn(arguments)
        return {"error": f"未知工具: {tool_name}"}

    # ── 工具实现 ─────────────────────────────────────────────

    def _get_destination_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """优先从本地知识库读取，未找到时返回提示，不返回硬编码假数据"""
        destination = args.get("destination", "")
        data = _load_destination(destination)
        if data:
            return {
                "destination": destination,
                "data_source": "本地知识库",
                "info": data
            }
        return {
            "destination": destination,
            "data_source": "未找到",
            "message": f"暂无 {destination} 的本地数据，建议通过 RAG 检索或 DuckDuckGo 搜索获取",
            "suggestion": "可运行 python3 knowledge/build_index.py --sample 构建知识库索引"
        }

    def _calculate_budget(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """预算估算：优先使用知识库中的住宿均价，否则通用估算"""
        destination = args.get("destination", "")
        days = args.get("days", 7)
        people = args.get("people", 1)

        dest_data = _load_destination(destination)
        avg_hotel = None

        # 从知识库提取住宿价格参考
        accommodation = dest_data.get("accommodation", {})
        options = accommodation.get("options", []) if isinstance(accommodation, dict) else []
        prices = []
        for opt in options:
            nums = re.findall(r"\d+", opt.get("price_range", ""))
            if nums:
                prices.append(int(nums[0]))
        if prices:
            avg_hotel = sum(prices) // len(prices)

        hotel = avg_hotel or 400
        food = 150
        activity = 100
        local_transport = 50
        roundtrip = 1200

        daily = hotel + food + activity + local_transport
        total = (daily * days + roundtrip) * people

        return {
            "destination": destination,
            "days": days,
            "people": people,
            "data_source": "本地知识库估算" if avg_hotel else "通用估算",
            "breakdown": {
                "accommodation": hotel * days * people,
                "food": food * days * people,
                "local_transport": local_transport * days * people,
                "activities": activity * days * people,
                "roundtrip_transport": roundtrip * people
            },
            "total_estimated": total,
            "currency": "CNY",
            "note": "以上为估算值，实际花费因出行方式和消费习惯不同会有差异"
        }

    def _recommend_route(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """推荐路线：通用交通方式 + 知识库本地交通信息"""
        start = args.get("start", "")
        end = args.get("end", "")
        transport = args.get("transport", "all")

        dest_data = _load_destination(end)
        dest_transport = dest_data.get("transportation", {})

        routes = []
        if transport in ("all", "plane"):
            routes.append({
                "type": "飞机",
                "pros": ["速度最快"],
                "cons": ["价格较高"],
                "booking": f"携程/去哪儿/飞猪搜索 {start}到{end}机票"
            })
        if transport in ("all", "train"):
            routes.append({
                "type": "高铁/火车",
                "pros": ["舒适准时"],
                "cons": ["部分路线耗时较长"],
                "booking": "12306.cn"
            })
        if transport in ("all", "drive"):
            routes.append({
                "type": "自驾",
                "pros": ["自由灵活"],
                "cons": ["长途疲劳"],
                "booking": "高德地图/百度地图规划路线"
            })

        result: Dict[str, Any] = {
            "from": start,
            "to": end,
            "data_source": "通用建议",
            "routes": routes
        }
        if dest_transport:
            result["local_transport_at_destination"] = dest_transport
            result["data_source"] = "通用建议 + 本地知识库"

        return result

    # ── MCP stdio 运行入口 ───────────────────────────────────

    def run(self):
        print("自定义旅行数据 MCP Server 已启动", file=sys.stderr)
        for line in sys.stdin:
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": response
                }))
                sys.stdout.flush()
            except Exception as e:
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)}
                }))
                sys.stdout.flush()


if __name__ == "__main__":
    server = TravelMCPServer()
    server.run()
