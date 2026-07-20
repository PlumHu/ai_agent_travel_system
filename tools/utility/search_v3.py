"""
搜索工具 V3 - 带浏览器兜底策略
MCP → 模拟数据 → Browser Agent（最后兜底）
"""
import logging
from typing import Optional
from mcp_client import MCPManager

logger = logging.getLogger(__name__)


def search_web(query: str, use_mcp: bool = True, use_browser_fallback: bool = False) -> str:
    """
    网络搜索

    Args:
        query: 搜索关键词
        use_mcp: 是否使用 MCP（Brave Search）
        use_browser_fallback: 是否启用浏览器兜底（需要用户确认）

    Returns:
        str: 搜索结果（JSON 格式）
    """
    if use_mcp:
        try:
            mcp = MCPManager()
            result = mcp.call_tool("brave_search", "search", {
                "query": query,
                "count": 10
            })
            logger.info(f"搜索成功 (MCP): {query}")
            return str(result)
        except Exception as e:
            logger.warning(f"MCP 搜索失败，降级到模拟数据: {e}")

    # 模拟数据降级
    if not use_browser_fallback:
        return _get_mock_search_results(query)

    # 浏览器兜底（最后策略）
    try:
        from agents.browser_agent import search_with_browser
        import asyncio

        logger.info(f"使用浏览器兜底: {query}")
        result = asyncio.run(search_with_browser(query, max_results=5))
        return result
    except Exception as e:
        logger.error(f"浏览器兜底失败: {e}")
        return _get_mock_search_results(query)


def _get_mock_search_results(query: str) -> str:
    """模拟搜索结果"""
    mock_results = {
        "query": query,
        "results": [
            {
                "title": f"{query} - 相关信息（模拟数据）",
                "url": "https://example.com/1",
                "description": f"这是关于 {query} 的模拟搜索结果。实际使用时会调用真实搜索 API。"
            },
            {
                "title": f"{query} 攻略和建议",
                "url": "https://example.com/2",
                "description": "包含详细攻略和用户评价"
            }
        ]
    }

    import json
    return json.dumps(mock_results, ensure_ascii=False, indent=2)


# 示例使用
if __name__ == "__main__":
    # 1. 使用 MCP（优先）
    result = search_web("北京旅游", use_mcp=True)
    print("MCP 搜索:", result)

    # 2. 使用浏览器兜底（需要明确启用）
    result = search_web("上海美食", use_mcp=False, use_browser_fallback=True)
    print("浏览器搜索:", result)

    # 3. 使用模拟数据（默认降级）
    result = search_web("杭州景点", use_mcp=False, use_browser_fallback=False)
    print("模拟数据:", result)
