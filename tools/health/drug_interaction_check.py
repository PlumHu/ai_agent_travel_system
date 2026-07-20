"""
药物相互作用检查Skill

检查用户正在服用的药物是否与食物/酒精存在危险相互作用。
"""

from langchain.tools import tool
import json
from typing import List, Optional


DRUG_FOOD_INTERACTIONS = {
    "头孢类": {
        "drugs": ["头孢", "先锋", "西力欣", "希刻劳", "头孢克洛", "头孢拉定", "头孢氨苄"],
        "danger_foods": ["酒精", "酒", "啤酒", "白酒", "红酒", "料酒", "啤酒鸭", "醉蟹"],
        "risk": "双硫仑样反应：面部潮红、头痛、呕吐、呼吸困难，严重可致死",
        "severity": "fatal",
        "avoid_duration": "服药期间及停药后7天内",
        "recommendation": "绝对禁止任何含酒精的食物和饮品！料酒做的菜也要避开！"
    },
    "甲硝唑": {
        "drugs": ["甲硝唑", "灭滴灵", "替硝唑"],
        "danger_foods": ["酒精", "酒", "啤酒", "白酒"],
        "risk": "类似双硫仑反应",
        "severity": "fatal",
        "avoid_duration": "服药期间及停药后3天内",
        "recommendation": "绝对禁止饮酒"
    },
    "降压药_CCB": {
        "drugs": ["硝苯地平", "氨氯地平", "非洛地平", "拜新同", "络活喜"],
        "danger_foods": ["西柚", "葡萄柚", "柚子", "西柚汁"],
        "risk": "西柚抑制药物代谢酶，导致血药浓度升高，可能引起严重低血压",
        "severity": "severe",
        "recommendation": "服药期间完全避免西柚及其制品"
    },
    "降糖药": {
        "drugs": ["二甲双胍", "格列美脲", "胰岛素", "拜糖平"],
        "danger_foods": ["酒精（空腹饮酒导致严重低血糖）", "大量荔枝"],
        "risk": "低血糖风险，严重可昏迷",
        "severity": "severe",
        "recommendation": "不能空腹饮酒；随身带糖果防低血糖；定时监测血糖"
    },
}


@tool
def check_drug_interactions(
    user_medications: List[str],
    planned_foods: Optional[List[str]] = None,
    destination: Optional[str] = None
) -> str:
    """检查用户药物与食物的相互作用"""
    warnings = []
    fatal_warnings = []

    for med in user_medications:
        for interaction_key, data in DRUG_FOOD_INTERACTIONS.items():
            matched = any(drug_name in med for drug_name in data["drugs"])
            if not matched:
                continue

            warning = {
                "medication": med,
                "matched_category": interaction_key,
                "danger_foods": data["danger_foods"],
                "risk_description": data["risk"],
                "severity": data["severity"],
                "avoid_duration": data.get("avoid_duration", "服药期间"),
                "recommendation": data["recommendation"],
            }

            if planned_foods:
                conflicts = [food for food in planned_foods
                             if any(danger in food for danger in data["danger_foods"])]
                if conflicts:
                    warning["planned_food_conflicts"] = conflicts

            if data["severity"] in ["fatal", "severe"]:
                fatal_warnings.append(warning)
            else:
                warnings.append(warning)

    return json.dumps({
        "has_warnings": bool(warnings or fatal_warnings),
        "fatal_warnings": fatal_warnings,
        "warnings": warnings,
        "total_risks": len(fatal_warnings) + len(warnings),
        "general_advice": "旅行期间不要随意停药。如果计划饮酒，务必先确认药物说明书或咨询医生。"
    }, ensure_ascii=False, indent=2)