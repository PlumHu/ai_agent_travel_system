"""
实时搜索（Realtime Search）
==========================
把"实时性"从降级链的兜底提升为一等能力。旅行场景大量信息必须实时：
机票价格、酒店余量、天气、景点是否开放、临时管制、活动排期。

分级策略（按实时性和成本排序）：
  1. Brave Search API  —— 有 BRAVE_SEARCH_API_KEY，支持 freshness 参数，最实时
  2. Serper API        —— 有 SERPER_API_KEY，Google 结果
  3. DuckDuckGo        —— 免费兜底（复用 free_search）
  4. browser-use       —— 最后重武器（复用 browser_agent，能抓 JS 动态页）

与 free_search / search_v3 的区别：
  - free_search: 通用免费搜索，不强调时效
  - realtime_search: 优先真正实时的付费源，结果统一标注 fetched_at 时间戳和时效等级
  - 新代码应优先用本模块；旧模块保留向后兼容

关于 browser-use 为何仍是兜底：
  启动真实 Chromium 慢（秒级）、依赖 Playwright 重，但能力最强（抓 JS 动态页面）。
  所以让轻量实时源（Brave/Serper）先行，browser 只在前面全失败时唤醒。
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def realtime_search(query: str, freshness: str = "recent", max_results: int = 8) -> str:
    """
    实时联网搜索，分级降级，结果带时间戳和时效标注。

    Args:
        query: 搜索关键词
        freshness: 时效要求 —— "recent"(近期,默认) / "day"(24小时内) / "any"(不限)
        max_results: 最多返回结果数

    Returns:
        JSON 字符串，结构：
        {
          "query": ..., "source": ..., "freshness": ...,
          "fetched_at": ISO时间戳, "timeliness": "high/medium/low",
          "results": [{title, url, description, source}]
        }
    """
    logger.info(f"[realtime_search] query={query!r}, freshness={freshness}")

    # 1. Brave Search API（最实时）
    brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if brave_key:
        result = _search_brave(query, brave_key, freshness, max_results)
        if result:
            return _wrap(query, "Brave Search API", freshness, result, timeliness="high")

    # 2. Serper API
    serper_key = os.getenv("SERPER_API_KEY", "")
    if serper_key:
        result = _search_serper(query, serper_key, max_results)
        if result:
            return _wrap(query, "Serper API", freshness, result, timeliness="high")

    # 3. DuckDuckGo（免费兜底）
    try:
        from tools.utility.free_search import search_duckduckgo
        ddg = search_duckduckgo(query, max_results=max_results)
        if ddg:
            return _wrap(query, "DuckDuckGo", freshness, ddg, timeliness="medium")
    except Exception as e:
        logger.warning(f"[realtime_search] DuckDuckGo 失败: {e}")

    # 4. browser-use（最后重武器）
    try:
        from agents.browser_agent import search_with_browser
        import asyncio
        logger.info("[realtime_search] 唤醒浏览器兜底（慢）")
        browser_raw = asyncio.run(search_with_browser(query, max_results=max_results))
        # browser 返回已是 JSON 字符串，包一层时效标注
        return _wrap_raw(query, "Browser-Use", freshness, browser_raw, timeliness="medium")
    except Exception as e:
        logger.warning(f"[realtime_search] 浏览器兜底失败: {e}")

    # 全部失败
    return _wrap(query, "none", freshness, [], timeliness="low",
                 note="所有实时搜索源均不可用，建议稍后重试或配置 BRAVE_SEARCH_API_KEY")


# ── 各数据源实现 ──────────────────────────────────────────────

def _search_brave(query: str, api_key: str, freshness: str, max_results: int) -> Optional[List[Dict]]:
    """Brave Search API。支持 freshness 参数（pd=一天,pw=一周,pm=一月）"""
    try:
        import requests

        freshness_map = {"day": "pd", "recent": "pw", "any": None}
        params = {"q": query, "count": max_results}
        fresh = freshness_map.get(freshness)
        if fresh:
            params["freshness"] = fresh

        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "source": "Brave",
                "age": item.get("age", ""),  # Brave 返回的时效信息
            })
        return results or None
    except Exception as e:
        logger.warning(f"[realtime_search] Brave API 失败: {e}")
        return None


def _search_serper(query: str, api_key: str, max_results: int) -> Optional[List[Dict]]:
    """Serper API（Google 搜索结果）"""
    try:
        import requests

        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "description": item.get("snippet", ""),
                "source": "Serper",
                "date": item.get("date", ""),
            })
        return results or None
    except Exception as e:
        logger.warning(f"[realtime_search] Serper API 失败: {e}")
        return None


# ── 结果封装 ──────────────────────────────────────────────────

def _wrap(query, source, freshness, results, timeliness, note=None) -> str:
    """统一封装搜索结果，附上时间戳和时效标注"""
    payload = {
        "query": query,
        "source": source,
        "freshness": freshness,
        "fetched_at": datetime.now().isoformat(),
        "timeliness": timeliness,   # high(付费实时源) / medium(免费/浏览器) / low(失败)
        "result_count": len(results),
        "results": results,
    }
    if note:
        payload["note"] = note
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _wrap_raw(query, source, freshness, raw_json_str, timeliness) -> str:
    """封装已是 JSON 字符串的结果（如 browser 返回）"""
    try:
        parsed = json.loads(raw_json_str)
        results = parsed.get("results", parsed) if isinstance(parsed, dict) else parsed
    except Exception:
        results = [{"title": "浏览器抓取结果", "description": str(raw_json_str)[:500], "source": source}]
    return _wrap(query, source, freshness, results if isinstance(results, list) else [results], timeliness)


# ── 自测 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(realtime_search("北京到大理 机票价格", freshness="day"))
