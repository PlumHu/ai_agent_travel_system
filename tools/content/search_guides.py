"""
搜索旅行攻略工具
优先从本地知识库读取，未找到时使用 DuckDuckGo 搜索真实攻略
"""
import json
import logging
from pathlib import Path
from typing import List, Dict

from config import RAW_DATA_PATH

logger = logging.getLogger(__name__)


def _load_from_knowledge_base(destination: str) -> dict:
    """从本地 JSON 知识库加载"""
    destinations_dir = RAW_DATA_PATH / "destinations"
    if not destinations_dir.exists():
        return {}
    for json_file in destinations_dir.glob("*.json"):
        try:
            import json as _json
            with open(json_file, "r", encoding="utf-8") as f:
                data = _json.load(f)
            if destination.lower() in data.get("destination", "").lower():
                return data
        except Exception as e:
            logger.error(f"读取文件失败 {json_file}: {e}")
    return {}


def _search_online(destination: str) -> List[Dict]:
    """使用 DuckDuckGo 搜索真实攻略"""
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(f"{destination}旅游攻略 景点推荐", region="cn-zh", max_results=8):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                })
        return results
    except Exception as e:
        logger.warning(f"DuckDuckGo 搜索失败: {e}")
        return []


def search_travel_guides(destination: str) -> str:
    """
    搜索旅行攻略。
    优先从本地知识库读取，未找到时使用 DuckDuckGo 搜索。

    Args:
        destination: 目的地名称

    Returns:
        攻略信息的 JSON 字符串
    """
    logger.info(f"[Tool] 搜索旅行攻略: {destination}")

    # 1. 本地知识库
    local_data = _load_from_knowledge_base(destination)
    if local_data:
        logger.info(f"从本地知识库加载: {destination}")
        return json.dumps({"source": "本地知识库", "data": local_data}, ensure_ascii=False, indent=2)

    # 2. DuckDuckGo 在线搜索
    online_results = _search_online(destination)
    if online_results:
        logger.info(f"DuckDuckGo 搜索成功: {destination}, 结果数: {len(online_results)}")
        return json.dumps({
            "source": "DuckDuckGo",
            "destination": destination,
            "guides": online_results,
        }, ensure_ascii=False, indent=2)

    # 3. 无结果兜底
    logger.warning(f"未找到攻略: {destination}")
    return json.dumps({
        "destination": destination,
        "message": "暂未找到详细攻略",
        "suggestions": [
            "建议搜索该目的地的官方旅游网站",
            "查看马蜂窝、穷游等旅游平台的游记",
        ],
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(search_travel_guides("大理"))
