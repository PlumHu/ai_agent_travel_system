"""
免费搜索工具集合
支持多种免费搜索API：DuckDuckGo（完全免费）、Browser-Use（已集成）
"""
import logging
from typing import List, Dict, Any, Optional
import json

logger = logging.getLogger(__name__)

# DuckDuckGo 搜索
try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    logger.warning("duckduckgo-search 未安装，运行: pip install duckduckgo-search")


def search_duckduckgo(
    query: str,
    max_results: int = 10,
    region: str = "cn-zh"
) -> List[Dict[str, Any]]:
    """
    使用 DuckDuckGo 搜索（完全免费，无需 API Key）

    Args:
        query: 搜索关键词
        max_results: 最多返回结果数
        region: 地区代码（cn-zh=中国，us-en=美国）

    Returns:
        List[Dict]: 搜索结果列表
            - title: 标题
            - href: URL
            - body: 摘要
    """
    if not DDGS_AVAILABLE:
        raise ImportError("请安装: pip install duckduckgo-search")

    try:
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, region=region, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                    "source": "DuckDuckGo"
                })

            logger.info(f"DuckDuckGo 搜索成功: {query}, 结果数: {len(results)}")
            return results

    except Exception as e:
        logger.error(f"DuckDuckGo 搜索失败: {e}")
        raise


def search_duckduckgo_news(
    query: str,
    max_results: int = 10,
    region: str = "cn-zh"
) -> List[Dict[str, Any]]:
    """
    使用 DuckDuckGo 搜索新闻（完全免费）

    Args:
        query: 搜索关键词
        max_results: 最多返回结果数
        region: 地区代码

    Returns:
        List[Dict]: 新闻结果列表
    """
    if not DDGS_AVAILABLE:
        raise ImportError("请安装: pip install duckduckgo-search")

    try:
        with DDGS() as ddgs:
            results = []
            for r in ddgs.news(query, region=region, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("body", ""),
                    "date": r.get("date", ""),
                    "source": r.get("source", ""),
                    "image": r.get("image", "")
                })

            logger.info(f"DuckDuckGo 新闻搜索成功: {query}, 结果数: {len(results)}")
            return results

    except Exception as e:
        logger.error(f"DuckDuckGo 新闻搜索失败: {e}")
        raise


def search_with_fallback(
    query: str,
    max_results: int = 10,
    use_browser: bool = False
) -> str:
    """
    智能搜索（多层降级）

    优先级：
    1. DuckDuckGo（免费）
    2. Browser-Use（需用户确认）
    3. 模拟数据

    Args:
        query: 搜索关键词
        max_results: 最多返回结果数
        use_browser: 是否允许使用浏览器兜底

    Returns:
        str: JSON 格式的搜索结果
    """
    # 1. 尝试 DuckDuckGo
    if DDGS_AVAILABLE:
        try:
            results = search_duckduckgo(query, max_results=max_results)
            return json.dumps({
                "query": query,
                "source": "DuckDuckGo（免费）",
                "results": results
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"DuckDuckGo 搜索失败: {e}")

    # 2. 浏览器兜底（需用户确认）
    if use_browser:
        try:
            from agents.browser_agent import search_with_browser
            import asyncio

            logger.info("使用浏览器搜索作为兜底")
            result = asyncio.run(search_with_browser(query, max_results=max_results))
            return result
        except Exception as e:
            logger.error(f"浏览器搜索失败: {e}")

    # 3. 模拟数据
    logger.warning("所有搜索方式失败，返回模拟数据")
    return json.dumps({
        "query": query,
        "source": "模拟数据",
        "results": [
            {
                "title": f"{query} - 相关信息（模拟）",
                "url": "https://example.com/1",
                "description": "这是模拟搜索结果，实际使用时会调用真实搜索 API",
                "source": "Mock"
            }
        ]
    }, ensure_ascii=False, indent=2)


# 便捷函数
def quick_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    快速搜索（仅返回标题和链接）

    Args:
        query: 搜索关键词
        max_results: 最多返回结果数

    Returns:
        List[Dict]: 简化的搜索结果
    """
    try:
        results = search_duckduckgo(query, max_results=max_results)
        return [
            {"title": r["title"], "url": r["url"]}
            for r in results
        ]
    except Exception as e:
        logger.error(f"快速搜索失败: {e}")
        return []


# 示例使用
if __name__ == "__main__":
    print("=" * 60)
    print("免费搜索工具测试")
    print("=" * 60)

    # 测试 1: DuckDuckGo 搜索
    print("\n测试 1: DuckDuckGo 搜索")
    print("-" * 60)
    try:
        results = search_duckduckgo("Python 教程", max_results=5)
        print(f"✓ 找到 {len(results)} 个结果")
        for i, r in enumerate(results[:3], 1):
            print(f"\n  [{i}] {r['title']}")
            print(f"      {r['url']}")
            print(f"      {r['description'][:100]}..." if len(r['description']) > 100 else f"      {r['description']}")
    except Exception as e:
        print(f"✗ 搜索失败: {e}")

    # 测试 2: 新闻搜索
    print("\n\n测试 2: DuckDuckGo 新闻搜索")
    print("-" * 60)
    try:
        results = search_duckduckgo_news("人工智能", max_results=5)
        print(f"✓ 找到 {len(results)} 条新闻")
        for i, r in enumerate(results[:3], 1):
            print(f"\n  [{i}] {r['title']}")
            print(f"      来源: {r['source']}, 时间: {r['date']}")
            print(f"      {r['url']}")
    except Exception as e:
        print(f"✗ 新闻搜索失败: {e}")

    # 测试 3: 智能降级搜索
    print("\n\n测试 3: 智能降级搜索")
    print("-" * 60)
    result = search_with_fallback("北京旅游景点", max_results=5)
    print(f"搜索结果:\n{result[:500]}..." if len(result) > 500 else f"搜索结果:\n{result}")

    print("\n" + "=" * 60)
    print("✓ 测试完成")
    print("=" * 60)
