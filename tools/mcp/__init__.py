"""
tools/mcp 包初始化文件
"""
from .mcp_client import MCPClient, mcp_client, get_weather_via_mcp, search_places_via_mcp

__all__ = [
    "MCPClient",
    "mcp_client",
    "get_weather_via_mcp",
    "search_places_via_mcp"
]
