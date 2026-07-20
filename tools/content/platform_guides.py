"""
平台攻略抓取工具
覆盖小红书、马蜂窝、携程、飞猪四个平台的旅游攻略与路线内容。

降级策略（三层）：
  层 1 — DuckDuckGo site 过滤搜索（免费，返回搜索摘要）
  层 2 — browser-use 浏览器抓取（慢，需 playwright，返回完整正文）
  层 3 — 本地知识库 / 参考链接（兜底）
"""
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ── 平台配置 ──────────────────────────────────────────────────
PLATFORMS: Dict[str, Dict[str, Any]] = {
    "xiaohongshu": {
        "name": "小红书",
        "site": "xiaohongshu.com",
        "search_suffix": "旅游攻略 游记 种草",
        "url_tpl": "https://www.xiaohongshu.com/search_result?keyword={keyword}",
        "task_tpl": (
            "打开小红书搜索 {keyword}，找到点赞最多的 3 篇旅游攻略或游记，"
            "提取每篇的标题、主要景点、行程天数、预算、交通建议，"
            "以 JSON 格式返回。"
        ),
    },
    "mafengwo": {
        "name": "马蜂窝",
        "site": "mafengwo.cn",
        "search_suffix": "攻略 行程单 路线",
        "url_tpl": "https://www.mafengwo.cn/search/q.php?q={keyword}",
        "task_tpl": (
            "打开马蜂窝搜索 {keyword}，找到评分最高的 3 篇攻略或行程单，"
            "提取每篇的标题、行程路线、天数、花费，"
            "以 JSON 格式返回。"
        ),
    },
    "ctrip": {
        "name": "携程",
        "site": "ctrip.com",
        "search_suffix": "景点攻略 游玩路线",
        "url_tpl": "https://you.ctrip.com/searchsite/?query={keyword}",
        "task_tpl": (
            "打开携程旅游搜索 {keyword}，找到 3 篇热门攻略，"
            "提取每篇的标题、推荐景点、最佳季节、交通方式，"
            "以 JSON 格式返回。"
        ),
    },
    "fliggy": {
        "name": "飞猪",
        "site": "fliggy.com",
        "search_suffix": "旅游攻略 路线推荐",
        "url_tpl": "https://www.fliggy.com/search?q={keyword}",
        "task_tpl": (
            "打开飞猪旅游搜索 {keyword}，找到 3 篇推荐攻略或路线，"
            "提取每篇的标题、行程路线、价格参考，"
            "以 JSON 格式返回。"
        ),
    },
}


# ── 层 1：DuckDuckGo site 过滤 ────────────────────────────────

def _ddg_search(destination: str, platform_key: str, max_results: int = 5) -> List[Dict]:
    """使用 DuckDuckGo 限定 site 搜索平台内容"""
    platform = PLATFORMS[platform_key]
    site = platform["site"]
    suffix = platform["search_suffix"]
    query = f"site:{site} {destination} {suffix}"

    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="cn-zh", max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "summary": r.get("body", ""),
                    "platform": platform["name"],
                    "source": f"DuckDuckGo+{platform['name']}",
                })
        logger.info(f"[{platform['name']}] DuckDuckGo 搜索成功: {len(results)} 条")
        return results
    except ImportError:
        logger.warning("duckduckgo-search 未安装")
    except Exception as e:
        logger.warning(f"[{platform['name']}] DuckDuckGo 搜索失败: {e}")
    return []


# ── 层 2：browser-use 抓取 ────────────────────────────────────

async def _browser_fetch(destination: str, platform_key: str) -> List[Dict]:
    """使用 browser-use 打开平台页面抓取攻略正文"""
    platform = PLATFORMS[platform_key]
    keyword = f"{destination}旅游攻略"
    url = platform["url_tpl"].format(keyword=keyword)
    task = platform["task_tpl"].format(keyword=keyword)

    try:
        from agents.browser_agent import BrowserAgent, BROWSER_USE_AVAILABLE
        if not BROWSER_USE_AVAILABLE:
            return []

        agent = BrowserAgent(headless=True, max_steps=15)
        result = await agent.execute(task=task, start_url=url)

        if result.get("success"):
            raw = result.get("result", "")
            # 尝试解析 JSON，失败时原文返回
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                items = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                items = [{"raw_text": raw}]

            return [{
                **item,
                "platform": platform["name"],
                "source": f"browser-use+{platform['name']}",
                "url": url,
            } for item in items]

    except Exception as e:
        logger.warning(f"[{platform['name']}] browser-use 抓取失败: {e}")
    return []


# ── 层 3：本地知识库兜底 ──────────────────────────────────────

def _local_fallback(destination: str, platform_key: str) -> Dict:
    """本地知识库兜底：从 knowledge/raw_data 读取已有数据"""
    from pathlib import Path
    import os

    platform = PLATFORMS[platform_key]
    name_map = {"大理": "dali", "丽江": "lijiang", "三亚": "sanya"}
    fname = name_map.get(destination, destination.lower())
    dest_dir = Path(__file__).parent.parent.parent / "knowledge" / "raw_data" / "destinations"
    dest_file = dest_dir / f"{fname}.json"

    local_info = {}
    if dest_file.exists():
        try:
            with open(dest_file, "r", encoding="utf-8") as f:
                local_info = json.load(f)
        except Exception:
            pass

    return {
        "platform": platform["name"],
        "source": "本地知识库（降级）",
        "destination": destination,
        "attractions": local_info.get("attractions", []),
        "tips": local_info.get("tips", []),
        "best_season": local_info.get("best_season", ""),
        "reference_url": platform["url_tpl"].format(keyword=f"{destination}旅游攻略"),
        "note": f"无法从 {platform['name']} 实时获取数据，以下为本地知识库内容，建议访问上方链接获取最新攻略"
    }


# ── 公共接口 ─────────────────────────────────────────────────

def search_platform_guides(
    destination: str,
    platforms: Optional[List[str]] = None,
    use_browser_fallback: bool = True,
    max_results_per_platform: int = 3,
) -> str:
    """
    从多个旅游平台搜索目的地攻略与路线。

    Args:
        destination: 目的地，如 "大理"
        platforms: 要搜索的平台列表，默认全部 ["xiaohongshu", "mafengwo", "ctrip", "fliggy"]
        use_browser_fallback: DuckDuckGo 失败时是否启用 browser-use（默认 True）
        max_results_per_platform: 每个平台最多返回条数

    Returns:
        JSON 字符串，按平台分组的攻略列表
    """
    import asyncio

    if platforms is None:
        platforms = list(PLATFORMS.keys())

    all_results: Dict[str, Any] = {
        "destination": destination,
        "platforms": {}
    }

    for pk in platforms:
        if pk not in PLATFORMS:
            logger.warning(f"未知平台: {pk}")
            continue

        platform_name = PLATFORMS[pk]["name"]
        logger.info(f"开始搜索 [{platform_name}] {destination}")

        # 层 1：DuckDuckGo
        results = _ddg_search(destination, pk, max_results=max_results_per_platform)

        # 层 2：browser-use
        if not results and use_browser_fallback:
            logger.info(f"[{platform_name}] DuckDuckGo 无结果，尝试 browser-use")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, _browser_fetch(destination, pk))
                        results = future.result(timeout=60)
                else:
                    results = loop.run_until_complete(_browser_fetch(destination, pk))
            except Exception as e:
                logger.warning(f"[{platform_name}] browser-use 执行失败: {e}")

        # 层 3：本地知识库
        if not results:
            logger.warning(f"[{platform_name}] 所有方式失败，使用本地知识库兜底")
            results = [_local_fallback(destination, pk)]

        all_results["platforms"][platform_name] = results[:max_results_per_platform]

    total = sum(len(v) for v in all_results["platforms"].values())
    all_results["total_results"] = total
    logger.info(f"平台攻略搜索完成，共 {total} 条结果")
    return json.dumps(all_results, ensure_ascii=False, indent=2)


def search_travel_routes(destination: str, use_browser_fallback: bool = True) -> str:
    """
    专门搜索旅行路线（行程单）。优先马蜂窝、飞猪，其次小红书。

    Args:
        destination: 目的地，如 "大理"
        use_browser_fallback: 是否启用 browser-use 兜底

    Returns:
        JSON 字符串
    """
    return search_platform_guides(
        destination=destination,
        platforms=["mafengwo", "fliggy", "xiaohongshu"],
        use_browser_fallback=use_browser_fallback,
        max_results_per_platform=3,
    )


def search_destination_notes(destination: str, use_browser_fallback: bool = True) -> str:
    """
    专门搜索游记/种草笔记（小红书为主）。

    Args:
        destination: 目的地，如 "大理"
        use_browser_fallback: 是否启用 browser-use 兜底

    Returns:
        JSON 字符串
    """
    return search_platform_guides(
        destination=destination,
        platforms=["xiaohongshu", "mafengwo"],
        use_browser_fallback=use_browser_fallback,
        max_results_per_platform=5,
    )


if __name__ == "__main__":
    import sys
    dest = sys.argv[1] if len(sys.argv) > 1 else "大理"
    print(f"搜索 {dest} 攻略...\n")
    result = search_platform_guides(dest, use_browser_fallback=False)
    data = json.loads(result)
    for pname, items in data["platforms"].items():
        print(f"【{pname}】{len(items)} 条")
        for item in items[:2]:
            print(f"  - {item.get('title', item.get('note', ''))[:60]}")
    print(f"\n共 {data['total_results']} 条结果")
