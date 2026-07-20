"""
搜索工具 V2 - 支持真实 MCP 调用
支持 Brave Search MCP Server
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from mcp_client import get_mcp_manager
from config import RAW_DATA_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def search_travel_info(query: str, use_mcp: bool = True, use_local: bool = True) -> str:
    """
    搜索旅行信息

    搜索策略：
    1. 优先使用本地知识库（快速）
    2. 如果本地无结果，使用 MCP Search（联网搜索）
    3. 如果 MCP 失败，返回建议

    Args:
        query: 搜索查询
        use_mcp: 是否使用 MCP Server
        use_local: 是否使用本地知识库

    Returns:
        搜索结果的 JSON 字符串
    """
    logger.info(f"[Tool] 搜索旅行信息: {query}")

    results = {
        "query": query,
        "local_results": [],
        "web_results": [],
        "data_source": []
    }

    # Step 1: 搜索本地知识库
    if use_local:
        local_results = _search_local_knowledge(query)
        if local_results:
            results["local_results"] = local_results
            results["data_source"].append("local_knowledge")
            logger.info(f"本地知识库找到 {len(local_results)} 条结果")

    # Step 2: 如果本地无结果，使用 MCP 联网搜索
    if not results["local_results"] and use_mcp:
        try:
            mcp = get_mcp_manager()
            mcp_result = mcp.call_tool(
                "brave_search",
                "search",
                {
                    "query": query,
                    "count": 5
                }
            )

            if mcp_result and "results" in mcp_result:
                results["web_results"] = mcp_result["results"]
                results["data_source"].append("brave_search_mcp")
                logger.info(f"✅ MCP 搜索成功，找到 {len(mcp_result['results'])} 条结果")

        except Exception as e:
            logger.warning(f"MCP 搜索失败: {e}")
            results["data_source"].append("mcp_failed")

    # Step 3: 如果都没有结果，返回建议
    if not results["local_results"] and not results["web_results"]:
        results["suggestions"] = [
            "建议搜索该目的地的官方旅游网站",
            "查看其他旅行者的游记和评价",
            "咨询当地旅游局或导游"
        ]
        results["data_source"].append("suggestions")

    return json.dumps(results, ensure_ascii=False, indent=2)


def _search_local_knowledge(query: str) -> List[Dict[str, Any]]:
    """
    搜索本地知识库

    Args:
        query: 查询文本

    Returns:
        匹配的结果列表
    """
    destinations_dir = RAW_DATA_PATH / "destinations"

    if not destinations_dir.exists():
        logger.warning(f"本地知识库目录不存在: {destinations_dir}")
        return []

    results = []

    # 简单的关键词匹配
    query_lower = query.lower()

    for json_file in destinations_dir.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            destination = data.get("destination", "")

            # 检查是否匹配
            if query_lower in destination.lower():
                results.append({
                    "destination": destination,
                    "description": data.get("description", ""),
                    "best_season": data.get("best_season", ""),
                    "source": "local",
                    "file": str(json_file.name)
                })

        except Exception as e:
            logger.error(f"读取文件失败 {json_file}: {e}")

    return results


# ============ 使用示例 ============

if __name__ == "__main__":
    # 示例 1：本地知识库搜索
    print("\n" + "=" * 60)
    print("示例 1：搜索本地知识库")
    print("=" * 60)
    result = search_travel_info("大理", use_mcp=False)
    print(result)

    # 示例 2：本地+MCP 搜索
    print("\n" + "=" * 60)
    print("示例 2：本地 + MCP 联网搜索")
    print("=" * 60)
    result = search_travel_info("冰岛旅行攻略", use_mcp=True)
    print(result)

    # 示例 3：纯 MCP 搜索
    print("\n" + "=" * 60)
    print("示例 3：纯 MCP 联网搜索")
    print("=" * 60)
    result = search_travel_info("best time to visit Iceland", use_mcp=True, use_local=False)
    print(result)
