"""
过敏原检测工具
基于内置过敏原知识库进行关键词匹配检测；
目的地过敏原风险通过 DuckDuckGo 搜索补充真实信息
"""
import json
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# 14 类主要食物过敏原（基于国际标准）
ALLERGEN_KEYWORDS: Dict[str, List[str]] = {
    "花生":  ["花生", "peanut"],
    "坚果":  ["核桃", "杏仁", "腰果", "榛子", "松子", "栗子", "nuts"],
    "海鲜":  ["虾", "蟹", "蛤", "蚌", "贝", "鱿鱼", "章鱼", "海参", "seafood"],
    "鱼类":  ["鱼", "鲈", "鲫", "鳜", "鲑", "三文鱼", "fish"],
    "牛奶":  ["牛奶", "奶酪", "黄油", "乳清", "milk", "dairy"],
    "鸡蛋":  ["鸡蛋", "蛋清", "蛋黄", "egg"],
    "小麦":  ["小麦", "面粉", "面条", "面包", "wheat", "gluten"],
    "大豆":  ["大豆", "豆腐", "豆浆", "毛豆", "soy"],
    "芝麻":  ["芝麻", "sesame"],
    "菌类":  ["蘑菇", "香菇", "金针菇", "木耳", "菌", "mushroom"],
}

SEVERITY = {
    "花生": "高", "坚果": "高", "海鲜": "高", "鱼类": "中",
    "牛奶": "中", "鸡蛋": "中", "小麦": "低",
    "大豆": "低", "芝麻": "低", "菌类": "中",
}


def check_food_allergens(food_name: str, user_allergies: List[str] = None) -> str:
    """
    检测食物中的过敏原。

    Args:
        food_name: 食物名称
        user_allergies: 用户已知过敏原列表
    """
    logger.info(f"[Tool] 检测过敏原: {food_name}")

    if user_allergies is None:
        user_allergies = []

    detected = []
    warnings = []

    for allergen, keywords in ALLERGEN_KEYWORDS.items():
        if any(kw in food_name for kw in keywords):
            detected.append({"allergen": allergen, "severity": SEVERITY.get(allergen, "低")})
            if allergen in user_allergies or any(a in user_allergies for a in keywords):
                warnings.append(f"⚠️ 该食物含有您过敏的【{allergen}】，请勿食用！")

    return json.dumps({
        "food": food_name,
        "user_allergies": user_allergies,
        "detected_allergens": detected,
        "warnings": warnings,
        "safe_to_eat": len(warnings) == 0,
    }, ensure_ascii=False, indent=2)


def get_destination_allergen_risks(destination: str) -> str:
    """
    获取目的地过敏原风险信息。
    优先使用 DuckDuckGo 搜索真实信息，失败时给出通用建议。

    Args:
        destination: 目的地名称
    """
    logger.info(f"[Tool] 查询目的地过敏原风险: {destination}")

    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(f"{destination}特色食物 过敏原 饮食注意", region="cn-zh", max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                })
        source = "DuckDuckGo"
    except Exception as e:
        logger.warning(f"过敏原搜索失败: {e}")
        results = []
        source = "搜索不可用"

    return json.dumps({
        "source": source,
        "destination": destination,
        "search_results": results,
        "general_advice": [
            "出行前准备抗过敏药物",
            "点餐时提前告知服务员过敏情况",
            "携带过敏原信息卡（建议中英双语）",
            "了解当地急救医院位置",
        ],
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(check_food_allergens("洱海虾仁", ["海鲜"]))
    print(get_destination_allergen_risks("三亚"))
