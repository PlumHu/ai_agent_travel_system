"""
目的地推荐 Agent

当用户没有明确目的地时，根据用户偏好推荐旅行目的地
"""

from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from llm_config import create_llm_from_env


class DestinationAgent(BaseAgent):
    """目的地推荐 Agent"""

    def __init__(self, llm_provider: str = None):
        """
        初始化 DestinationAgent

        Args:
            llm_provider: LLM 提供商
        """
        super().__init__("DestinationAgent")
        self._llm = None
        self._llm_provider = llm_provider

    @property
    def llm(self):
        if self._llm is None and not self._llm_provider:
            self._llm = create_llm_from_env()
        return self._llm

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行入口：补全状态 → 推荐目的地"""
        state = self._enrich_state(state)
        return self._execute_task(state)

    def _enrich_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """准备状态（勿覆盖 BaseAgent._prepare_state）"""
        prefs = state.get("preferences")
        if prefs is None:
            state["preferences"] = {}
        elif isinstance(prefs, list):
            # AgentState 里 preferences 是 List[str]，这里转成字典供内部逻辑使用
            state["preferences"] = {"tags": prefs} if prefs else {}

        if not state.get("budget"):
            state["budget"] = 5000  # 默认预算

        return state

    def _execute_task(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行目的地推荐"""
        preferences = state.get("preferences", {})
        if isinstance(preferences, list):
            preferences = {"tags": preferences}
        budget = state.get("budget", 5000)
        month = state.get("month", None)

        # 1. 获取候选目的地
        candidates = self._get_candidate_destinations(preferences, budget, month)

        # 2. 使用 LLM 生成推荐
        recommendations = self._generate_recommendations(candidates, preferences, budget)

        state["destination_recommendations"] = recommendations

        # 如果有推荐，设置第一个为默认目的地
        if recommendations:
            state["destination"] = recommendations[0]["name"]

        return state

    def _extract_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """提取输出"""
        return {
            "recommendations": state.get("destination_recommendations", []),
            "selected_destination": state.get("destination"),
            "error": state.get("error")
        }

    def _get_candidate_destinations(
        self,
        preferences: Dict[str, Any],
        budget: int,
        month: int = None
    ) -> List[Dict[str, Any]]:
        """获取候选目的地"""
        # 简化版本：预定义的目的地数据
        destinations = [
            {
                "name": "大理",
                "tags": ["自然风光", "文化", "慢生活"],
                "avg_cost": 4000,
                "best_months": [3, 4, 5, 9, 10, 11],
                "description": "苍山洱海，风花雪月，白族文化",
                "highlights": ["洱海", "苍山", "大理古城", "双廊"]
            },
            {
                "name": "三亚",
                "tags": ["海滨", "度假", "热带"],
                "avg_cost": 6000,
                "best_months": [10, 11, 12, 1, 2, 3],
                "description": "阳光海滩，热带风情，度假天堂",
                "highlights": ["亚龙湾", "天涯海角", "蜈支洲岛", "南山寺"]
            },
            {
                "name": "丽江",
                "tags": ["古镇", "文化", "自然风光"],
                "avg_cost": 4500,
                "best_months": [3, 4, 5, 9, 10],
                "description": "古城古韵，纳西文化，玉龙雪山",
                "highlights": ["丽江古城", "玉龙雪山", "泸沽湖", "束河古镇"]
            },
            {
                "name": "成都",
                "tags": ["美食", "文化", "熊猫"],
                "avg_cost": 3500,
                "best_months": [3, 4, 5, 9, 10],
                "description": "天府之国，美食之都，熊猫故乡",
                "highlights": ["宽窄巷子", "大熊猫基地", "武侯祠", "锦里"]
            },
            {
                "name": "杭州",
                "tags": ["江南水乡", "文化", "美食"],
                "avg_cost": 4000,
                "best_months": [3, 4, 5, 9, 10],
                "description": "上有天堂，下有苏杭，西湖美景",
                "highlights": ["西湖", "灵隐寺", "宋城", "西溪湿地"]
            },
            {
                "name": "厦门",
                "tags": ["海滨", "文艺", "美食"],
                "avg_cost": 3800,
                "best_months": [3, 4, 5, 9, 10, 11],
                "description": "海上花园，文艺小清新，鼓浪屿",
                "highlights": ["鼓浪屿", "曾厝垵", "厦门大学", "南普陀寺"]
            }
        ]

        # 过滤候选
        candidates = []
        for dest in destinations:
            # 预算过滤
            if dest["avg_cost"] > budget * 1.2:
                continue

            # 月份过滤
            if month and month not in dest["best_months"]:
                continue

            # 偏好匹配（简单版本）
            if preferences:
                pref_tags = []
                if isinstance(preferences.get("tags"), list):
                    pref_tags.extend(str(t) for t in preferences["tags"])
                pref_tags.extend(
                    str(v) for v in preferences.values() if isinstance(v, str)
                )
                if pref_tags:
                    match_count = sum(
                        1 for tag in pref_tags if any(t in tag or tag in t for t in dest["tags"])
                    )
                    if match_count > 0:
                        dest["match_score"] = match_count
                        candidates.append(dest)
                    else:
                        candidates.append(dest)
                else:
                    candidates.append(dest)
            else:
                candidates.append(dest)

        # 排序（按匹配度和性价比）
        candidates.sort(key=lambda x: (x.get("match_score", 0), -x["avg_cost"]), reverse=True)

        return candidates[:5]  # 返回前5个

    def _generate_recommendations(
        self,
        candidates: List[Dict[str, Any]],
        preferences: Dict[str, Any],
        budget: int
    ) -> List[Dict[str, Any]]:
        """使用 LLM 生成推荐"""
        if not candidates:
            return []

        prompt = f"""你是一位专业的旅行顾问。请根据用户需求推荐旅行目的地。

用户偏好：{preferences if preferences else "无特殊偏好"}
用户预算：{budget}元

候选目的地：
{self._format_candidates_for_llm(candidates)}

请按照以下格式输出推荐（返回 JSON 数组）：
[
  {{
    "name": "目的地名称",
    "recommendation_score": 9,
    "reason": "推荐理由（50字以内）",
    "suitable_for": "适合人群",
    "travel_days": 5
  }}
]

注意：
1. 推荐3个最合适的目的地
2. recommendation_score 是推荐指数（1-10分）
3. 只返回 JSON，不要其他文字
"""

        try:
            if self.llm:
                response = self.llm.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7
                )

                import json
                import re
                content = response.choices[0].message.content

                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    recommendations = json.loads(json_match.group(0))
                    return recommendations
        except Exception as e:
            print(f"LLM 生成推荐失败: {e}")

        # 降级方案
        return [
            {
                "name": dest["name"],
                "recommendation_score": 8,
                "reason": dest["description"],
                "suitable_for": "所有人群",
                "travel_days": 5
            }
            for dest in candidates[:3]
        ]

    def _format_candidates_for_llm(self, candidates: List[Dict]) -> str:
        """格式化候选目的地"""
        formatted = []
        for i, dest in enumerate(candidates, 1):
            formatted.append(
                f"{i}. {dest['name']}\n"
                f"   - 标签：{', '.join(dest['tags'])}\n"
                f"   - 平均花费：{dest['avg_cost']}元\n"
                f"   - 描述：{dest['description']}\n"
                f"   - 亮点：{', '.join(dest['highlights'])}\n"
            )
        return "\n".join(formatted)


# 示例用法
if __name__ == "__main__":
    agent = DestinationAgent()

    state = {
        "preferences": {
            "style": "自然风光",
            "pace": "慢生活"
        },
        "budget": 5000,
        "month": 5
    }

    result = agent.execute(state)

    print("=" * 50)
    print("目的地推荐：")
    for rec in result["recommendations"]:
        print(f"\n📍 {rec['name']}")
        print(f"   推荐指数：{rec['recommendation_score']}/10")
        print(f"   推荐理由：{rec['reason']}")
        print(f"   适合人群：{rec['suitable_for']}")
        print(f"   建议天数：{rec['travel_days']}天")

    print(f"\n默认选择：{result['selected_destination']}")
