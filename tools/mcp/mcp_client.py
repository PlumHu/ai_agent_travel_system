"""
MCP 客户端管理器
管理 MCP 协议服务器的连接和调用
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPClient:
    """MCP 客户端管理器（单例模式）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.servers = {}
        self.config = {}
        self._load_config()

    def _load_config(self):
        """加载 MCP 配置"""
        config_path = Path(__file__).parent.parent.parent / "mcp_config.yaml"

        if config_path.exists():
            try:
                import yaml
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
                logger.info(f"加载 MCP 配置: {config_path}")
            except Exception as e:
                logger.warning(f"加载配置失败: {e}")
                self.config = {}
        else:
            logger.warning(f"MCP 配置文件不存在: {config_path}")
            self.config = {}

    def get_server_config(self, server_name: str) -> Optional[Dict]:
        """获取服务器配置"""
        servers = self.config.get("servers", {})
        return servers.get(server_name)

    def is_server_enabled(self, server_name: str) -> bool:
        """检查服务器是否启用"""
        server_config = self.get_server_config(server_name)
        return server_config.get("enabled", False) if server_config else False

    async def call_weather_server(self, location: str) -> str:
        """
        调用天气 MCP 服务器

        Args:
            location: 地点名称

        Returns:
            天气信息 JSON
        """
        logger.info(f"[MCP] 调用天气服务器: {location}")

        if not self.is_server_enabled("weather"):
            logger.warning("天气服务器未启用")
            return self._get_mock_weather(location)

        try:
            # 尝试调用真实 MCP 服务器
            # 实际项目中需要实现 MCP 协议通信
            result = await self._call_mcp_server("weather", {
                "action": "get_weather",
                "location": location
            })
            return result
        except Exception as e:
            logger.error(f"天气服务器调用失败: {e}")
            return self._get_mock_weather(location)

    async def call_maps_server(self, action: str, params: Dict) -> str:
        """
        调用百度地图 MCP 服务器

        Args:
            action: 操作类型（search/route/geocode）
            params: 参数

        Returns:
            地图信息 JSON
        """
        logger.info(f"[MCP] 调用地图服务器: {action}")

        if not self.is_server_enabled("baidu_maps"):
            logger.warning("地图服务器未启用")
            return self._get_mock_maps(action, params)

        try:
            result = await self._call_mcp_server("baidu_maps", {
                "action": action,
                **params
            })
            return result
        except Exception as e:
            logger.error(f"地图服务器调用失败: {e}")
            return self._get_mock_maps(action, params)

    async def _call_mcp_server(self, server_name: str, params: Dict) -> str:
        """调用 MCP 服务器（内部方法）"""
        # 这里需要实现实际的 MCP 协议通信
        # 目前返回模拟数据
        logger.info(f"[MCP] 内部调用 {server_name}: {params}")
        raise NotImplementedError("MCP 服务器通信待实现")

    def _get_mock_weather(self, location: str) -> str:
        """获取模拟天气数据"""
        from datetime import datetime
        import random

        return json.dumps({
            "source": "模拟数据",
            "location": location,
            "current": {
                "temp": random.randint(15, 30),
                "humidity": random.randint(40, 80),
                "condition": "晴"
            },
            "forecast": [
                {"date": "今天", "high": 25, "low": 15, "condition": "晴"},
                {"date": "明天", "high": 24, "low": 14, "condition": "多云"}
            ]
        }, ensure_ascii=False, indent=2)

    def _get_mock_maps(self, action: str, params: Dict) -> str:
        """获取模拟地图数据"""
        if action == "search":
            return json.dumps({
                "source": "模拟数据",
                "query": params.get("query", ""),
                "results": [
                    {"name": "示例地点1", "address": "示例地址1", "rating": 4.5},
                    {"name": "示例地点2", "address": "示例地址2", "rating": 4.3}
                ]
            }, ensure_ascii=False, indent=2)
        elif action == "route":
            return json.dumps({
                "source": "模拟数据",
                "origin": params.get("origin", ""),
                "destination": params.get("destination", ""),
                "distance": "10.5公里",
                "duration": "25分钟",
                "steps": ["出发", "沿主路行驶", "到达目的地"]
            }, ensure_ascii=False, indent=2)

        return json.dumps({"error": "未知操作"}, ensure_ascii=False)

    def list_available_servers(self) -> List[str]:
        """列出可用的服务器"""
        servers = []
        for name, config in self.config.get("servers", {}).items():
            if config.get("enabled", False):
                servers.append(name)
        return servers


# 全局单例实例
mcp_client = MCPClient()


# 便捷函数
async def get_weather_via_mcp(location: str) -> str:
    """通过 MCP 获取天气"""
    return await mcp_client.call_weather_server(location)


async def search_places_via_mcp(query: str) -> str:
    """通过 MCP 搜索地点"""
    return await mcp_client.call_maps_server("search", {"query": query})


async def get_route_via_mcp(origin: str, destination: str) -> str:
    """通过 MCP 获取路线"""
    return await mcp_client.call_maps_server("route", {
        "origin": origin,
        "destination": destination
    })


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("MCP 客户端测试")
    print("=" * 60)

    client = MCPClient()

    print("\n可用服务器:", client.list_available_servers())

    # 测试天气
    async def test_weather():
        result = await client.call_weather_server("北京")
        print("\n天气查询结果:")
        print(result[:300])

    asyncio.run(test_weather())
