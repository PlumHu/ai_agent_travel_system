"""
美食营养 Agent

功能：
1. 提供目的地美食推荐
2. 分析营养成分和健康建议
3. 过敏原检测
4. 饮食健康建议
"""

from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from llm_config import create_llm_from_env


class FoodAgent(BaseAgent):
    """美食营养 Agent"""

    def __init__(self, llm_provider: str = None):
        """
        初始化 FoodAgent

        Args:
            llm_provider: LLM 提供商（deepseek/openai/nvidia/custom）
        """
        super().__init__("FoodAgent")
        self._llm = None
        self.llm_provider = llm_provider

    @property
    def llm(self):
        if self._llm is None and not self.llm_provider:
            self._llm = create_llm_from_env()
        return self._llm

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行入口：补全状态 → 美食分析"""
        state = self._enrich_state(state)
        return self._execute_task(state)

    def _enrich_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """准备状态（勿覆盖 BaseAgent._prepare_state）"""
        if not state.get("destination"):
            inferred = self.infer_destination(state.get("user_input", ""))
            if inferred:
                state["destination"] = inferred
            else:
                state["error"] = "缺少目的地信息"

        if not state.get("travel_days"):
            state["travel_days"] = 5  # 默认5天

        if "dietary_restrictions" not in state or state.get("dietary_restrictions") is None:
            state["dietary_restrictions"] = []  # 饮食限制

        return state

    def _execute_task(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行美食推荐和营养分析"""
        if state.get("error"):
            return state

        destination = state["destination"]
        travel_days = state["travel_days"]
        dietary_restrictions = state.get("dietary_restrictions", [])

        # 1. 获取目的地特色美食
        local_foods = self._get_local_foods(destination)

        # 2. 过滤过敏原和饮食限制
        safe_foods = self._filter_foods(local_foods, dietary_restrictions)

        # 3. 营养分析
        nutrition_analysis = self._analyze_nutrition(safe_foods)

        # 4. 饮食健康建议
        health_tips = self._generate_health_tips(
            destination, travel_days, nutrition_analysis
        )

        # 5. LLM 生成完整推荐
        food_recommendations = self._generate_recommendations(
            destination, safe_foods, nutrition_analysis, health_tips
        )

        state["food_recommendations"] = food_recommendations
        state["health_tips"] = health_tips
        state["nutrition_summary"] = nutrition_analysis

        return state

    def _extract_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """提取输出"""
        return {
            "food_recommendations": state.get("food_recommendations", []),
            "health_tips": state.get("health_tips", []),
            "nutrition_summary": state.get("nutrition_summary", {}),
            "error": state.get("error")
        }

    def _get_local_foods(self, destination: str) -> List[Dict[str, Any]]:
        """获取目的地特色美食"""
        # 这里可以对接 RAG 知识库或搜索工具
        # 简化版本：返回预定义的美食数据
        foods_db = {
            "大理": [
                {
                    "name": "大理三道茶",
                    "description": "白族传统待客茶，一苦二甜三回味",
                    "category": "饮品",
                    "allergens": [],
                    "nutrition": {"calories": 50, "protein": 0, "carbs": 12}
                },
                {
                    "name": "喜洲粑粑",
                    "description": "白族传统小吃，外酥里嫩",
                    "category": "主食",
                    "allergens": ["小麦"],
                    "nutrition": {"calories": 280, "protein": 8, "carbs": 50}
                },
                {
                    "name": "洱海鱼",
                    "description": "新鲜的洱海野生鱼，肉质鲜美",
                    "category": "海鲜",
                    "allergens": ["鱼"],
                    "nutrition": {"calories": 150, "protein": 20, "carbs": 0}
                },
                {
                    "name": "乳扇",
                    "description": "白族特色乳制品，独特风味",
                    "category": "小吃",
                    "allergens": ["乳制品"],
                    "nutrition": {"calories": 200, "protein": 15, "carbs": 5}
                },
                {
                    "name": "砂锅鱼",
                    "description": "大理特色砂锅菜，汤鲜味美",
                    "category": "主菜",
                    "allergens": ["鱼", "辣椒"],
                    "nutrition": {"calories": 320, "protein": 25, "carbs": 15}
                }
            ],
            "三亚": [
                {
                    "name": "海南四角豆",
                    "description": "海南特色蔬菜，清爽可口",
                    "category": "蔬菜",
                    "allergens": [],
                    "nutrition": {"calories": 45, "protein": 3, "carbs": 8}
                },
                {
                    "name": "椰子鸡",
                    "description": "海南特色菜，椰香浓郁",
                    "category": "主菜",
                    "allergens": [],
                    "nutrition": {"calories": 280, "protein": 30, "carbs": 10}
                },
                {
                    "name": "文昌鸡",
                    "description": "海南四大名菜之首",
                    "category": "主菜",
                    "allergens": [],
                    "nutrition": {"calories": 250, "protein": 28, "carbs": 5}
                },
                {
                    "name": "海鲜粥",
                    "description": "新鲜海鲜熬制，营养丰富",
                    "category": "主食",
                    "allergens": ["海鲜"],
                    "nutrition": {"calories": 200, "protein": 15, "carbs": 30}
                },
                {
                    "name": "清补凉",
                    "description": "海南特色甜品，消暑解渴",
                    "category": "甜品",
                    "allergens": [],
                    "nutrition": {"calories": 180, "protein": 5, "carbs": 40}
                }
            ]
        }

        return foods_db.get(destination, [])

    def _filter_foods(self, foods: List[Dict], restrictions: List[str]) -> List[Dict]:
        """过滤过敏原和饮食限制"""
        if not restrictions:
            return foods

        safe_foods = []
        for food in foods:
            allergens = food.get("allergens", [])
            # 检查是否有冲突
            if not any(allergen in restrictions for allergen in allergens):
                safe_foods.append(food)

        return safe_foods

    def _analyze_nutrition(self, foods: List[Dict]) -> Dict[str, Any]:
        """营养分析"""
        if not foods:
            return {
                "total_calories": 0,
                "avg_protein": 0,
                "avg_carbs": 0,
                "balance_score": 0
            }

        total_calories = sum(f.get("nutrition", {}).get("calories", 0) for f in foods)
        total_protein = sum(f.get("nutrition", {}).get("protein", 0) for f in foods)
        total_carbs = sum(f.get("nutrition", {}).get("carbs", 0) for f in foods)

        avg_protein = total_protein / len(foods)
        avg_carbs = total_carbs / len(foods)

        # 简单的营养平衡评分（蛋白质和碳水比例）
        balance_score = min(10, (avg_protein / max(avg_carbs, 1)) * 10)

        return {
            "total_calories": total_calories,
            "avg_protein": round(avg_protein, 1),
            "avg_carbs": round(avg_carbs, 1),
            "balance_score": round(balance_score, 1),
            "protein_rich": avg_protein > 15,
            "carb_rich": avg_carbs > 30
        }

    def _generate_health_tips(
        self,
        destination: str,
        travel_days: int,
        nutrition_analysis: Dict[str, Any]
    ) -> List[str]:
        """生成饮食健康建议"""
        tips = []

        # 基于营养分析的建议
        if nutrition_analysis.get("protein_rich"):
            tips.append("🥗 营养均衡：美食以蛋白质为主，建议搭配新鲜蔬菜水果")

        if nutrition_analysis.get("carb_rich"):
            tips.append("🏃 碳水较高：建议增加户外活动，帮助消耗能量")

        # 基于旅行天数的建议
        if travel_days >= 5:
            tips.append("🍽️ 规律饮食：长途旅行建议保持三餐规律，避免暴饮暴食")
            tips.append("💧 充足饮水：每天至少8杯水，保持身体水分充足")

        # 通用饮食健康建议
        tips.extend([
            "🍜 品尝当地特色：尝试新美食，但注意食品卫生",
            "🥤 少吃甜食：旅行中容易摄入过多糖分，适量控制",
            "🌶️ 注意辣度：如果不习惯辛辣，点餐时提前说明",
            "🍺 适量饮酒：如需饮酒，注意适量，避免影响第二天行程"
        ])

        return tips

    def _generate_recommendations(
        self,
        destination: str,
        foods: List[Dict],
        nutrition: Dict[str, Any],
        health_tips: List[str]
    ) -> List[Dict[str, Any]]:
        """使用 LLM 生成完整的美食推荐"""
        if not foods:
            return []

        # 构造 Prompt
        prompt = f"""你是一位专业的美食与健康顾问。请为去{destination}旅行的游客提供详细的美食推荐。

可选美食：
{self._format_foods_for_llm(foods)}

营养分析：
- 平均蛋白质：{nutrition['avg_protein']}g
- 平均碳水：{nutrition['avg_carbs']}g
- 营养均衡度：{nutrition['balance_score']}/10

请按照以下格式输出推荐（返回 JSON 数组）：
[
  {{
    "name": "美食名称",
    "description": "详细描述",
    "health_rating": 9,
    "recommendation_reason": "推荐理由",
    "best_time": "最佳品尝时间"
  }}
]

注意：
1. 从给定的美食中选择3-5个最推荐的
2. health_rating 是健康评分（1-10分）
3. 考虑营养均衡和口味多样性
4. 只返回 JSON，不要其他文字
"""

        try:
            if self.llm:
                response = self.llm.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7
                )

                # 提取 JSON
                import json
                import re
                content = response.choices[0].message.content

                # 提取 JSON 数组
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    recommendations = json.loads(json_match.group(0))
                    return recommendations
        except Exception as e:
            print(f"LLM 生成推荐失败: {e}")

        # 降级方案：返回基础推荐
        return [
            {
                "name": food["name"],
                "description": food["description"],
                "health_rating": 8 if food.get("nutrition", {}).get("protein", 0) > 15 else 7,
                "recommendation_reason": f"当地特色美食，营养丰富",
                "best_time": "午餐或晚餐"
            }
            for food in foods[:5]
        ]

    def _format_foods_for_llm(self, foods: List[Dict]) -> str:
        """格式化美食列表供 LLM 使用"""
        formatted = []
        for i, food in enumerate(foods, 1):
            nutrition = food.get("nutrition", {})
            formatted.append(
                f"{i}. {food['name']}\n"
                f"   - 描述：{food['description']}\n"
                f"   - 类别：{food['category']}\n"
                f"   - 热量：{nutrition.get('calories', 0)} kcal\n"
                f"   - 蛋白质：{nutrition.get('protein', 0)}g\n"
            )
        return "\n".join(formatted)


# 示例用法
if __name__ == "__main__":
    agent = FoodAgent()

    state = {
        "destination": "大理",
        "travel_days": 5,
        "dietary_restrictions": []  # 可以添加如 ["乳制品", "辣椒"]
    }

    result = agent.execute(state)

    print("=" * 50)
    print("美食推荐：")
    for food in result["food_recommendations"]:
        print(f"\n📍 {food['name']}")
        print(f"   {food['description']}")
        print(f"   健康评分：{food['health_rating']}/10")
        print(f"   推荐理由：{food['recommendation_reason']}")
        print(f"   最佳时间：{food['best_time']}")

    print("\n" + "=" * 50)
    print("饮食健康建议：")
    for tip in result["health_tips"]:
        print(f"  {tip}")

    print("\n" + "=" * 50)
    print("营养摘要：")
    nutrition = result["nutrition_summary"]
    print(f"  平均蛋白质：{nutrition['avg_protein']}g")
    print(f"  平均碳水：{nutrition['avg_carbs']}g")
    print(f"  营养均衡度：{nutrition['balance_score']}/10")
