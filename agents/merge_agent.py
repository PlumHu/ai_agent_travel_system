"""
内容融合 Agent

功能：
1. 融合多个 Agent 的输出
2. 检查一致性
3. 消除冲突
4. 生成统一的最终输出
"""

from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from llm_config import create_llm_from_env


class MergeAgent(BaseAgent):
    """内容融合 Agent"""

    def __init__(self, llm_provider: str = None):
        """
        初始化 MergeAgent

        Args:
            llm_provider: LLM 提供商
        """
        super().__init__("MergeAgent")
        self._llm = None
        self._llm_provider = llm_provider

    @property
    def llm(self):
        if self._llm is None and not self._llm_provider:
            self._llm = create_llm_from_env()
        return self._llm

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行入口：收集内容 → 融合"""
        state = self._enrich_state(state)
        return self._execute_task(state)

    def _enrich_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """准备状态（勿覆盖 BaseAgent._prepare_state）"""
        if "contents_to_merge" not in state or not state.get("contents_to_merge"):
            state["contents_to_merge"] = self._collect_contents(state)

        return state

    def _execute_task(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行内容融合"""
        contents = state.get("contents_to_merge", {})

        if not contents:
            state["error"] = "没有内容需要融合"
            return state

        # 1. 一致性检查
        consistency_check = self._check_consistency(contents)

        # 2. 冲突解决
        resolved_contents = self._resolve_conflicts(contents, consistency_check)

        # 3. 内容融合
        merged_content = self._merge_contents(resolved_contents)

        state["merged_content"] = merged_content
        state["consistency_report"] = consistency_check

        return state

    def _extract_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """提取输出"""
        return {
            "merged_content": state.get("merged_content", {}),
            "consistency_report": state.get("consistency_report", {}),
            "error": state.get("error")
        }

    def _collect_contents(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """收集需要融合的内容"""
        contents = {}

        # 从 state 中收集各个 Agent 的输出
        if "destination_recommendations" in state:
            contents["destination"] = state["destination_recommendations"]

        if "travel_plan" in state:
            contents["travel_plan"] = state["travel_plan"]

        if "food_recommendations" in state:
            contents["food"] = state["food_recommendations"]

        if "mental_health_tips" in state:
            contents["mental_health"] = state["mental_health_tips"]

        return contents

    def _check_consistency(self, contents: Dict[str, Any]) -> Dict[str, Any]:
        """一致性检查"""
        report = {
            "is_consistent": True,
            "conflicts": [],
            "warnings": []
        }

        # 检查目的地一致性
        destinations = set()
        if "destination" in contents:
            for rec in contents["destination"]:
                destinations.add(rec.get("name"))

        if "travel_plan" in contents:
            plan_dest = contents["travel_plan"].get("destination")
            if plan_dest and plan_dest not in destinations:
                report["conflicts"].append(
                    f"旅行计划中的目的地 {plan_dest} 与推荐目的地不一致"
                )
                report["is_consistent"] = False

        # 检查预算一致性
        budgets = []
        if "travel_plan" in contents:
            plan_budget = contents["travel_plan"].get("total_budget")
            if plan_budget:
                budgets.append(plan_budget)

        if len(set(budgets)) > 1:
            report["warnings"].append(f"发现不同的预算金额：{budgets}")

        # 检查天数一致性
        days = []
        if "travel_plan" in contents:
            plan_days = len(contents["travel_plan"].get("daily_plan", []))
            if plan_days:
                days.append(plan_days)

        if "destination" in contents:
            for rec in contents["destination"]:
                rec_days = rec.get("travel_days")
                if rec_days:
                    days.append(rec_days)

        if days and len(set(days)) > 1:
            report["warnings"].append(f"发现不同的旅行天数：{days}")

        return report

    def _resolve_conflicts(
        self,
        contents: Dict[str, Any],
        consistency_check: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解决冲突"""
        if consistency_check["is_consistent"]:
            return contents

        # 简化版本：优先使用 travel_plan 中的信息
        resolved = contents.copy()

        if "travel_plan" in resolved:
            # 以 travel_plan 为准
            plan = resolved["travel_plan"]

            # 更新目的地推荐
            if "destination" in resolved:
                for rec in resolved["destination"]:
                    if rec.get("name") == plan.get("destination"):
                        # 保留匹配的推荐
                        resolved["destination"] = [rec]
                        break

        return resolved

    def _merge_contents(self, contents: Dict[str, Any]) -> Dict[str, Any]:
        """融合内容"""
        merged = {
            "destination": None,
            "travel_plan": None,
            "food_recommendations": [],
            "mental_health_tips": [],
            "summary": ""
        }

        # 融合目的地
        if "destination" in contents:
            if isinstance(contents["destination"], list) and contents["destination"]:
                merged["destination"] = contents["destination"][0].get("name")

        # 融合旅行计划
        if "travel_plan" in contents:
            merged["travel_plan"] = contents["travel_plan"]
            if not merged["destination"]:
                merged["destination"] = contents["travel_plan"].get("destination")

        # 融合美食推荐
        if "food" in contents:
            merged["food_recommendations"] = contents["food"]

        # 融合心理健康建议
        if "mental_health" in contents:
            merged["mental_health_tips"] = contents["mental_health"]

        # 生成摘要
        merged["summary"] = self._generate_summary(merged)

        return merged

    def _generate_summary(self, merged: Dict[str, Any]) -> str:
        """生成摘要"""
        parts = []

        if merged.get("destination"):
            parts.append(f"目的地：{merged['destination']}")

        if merged.get("travel_plan"):
            plan = merged["travel_plan"]
            days = len(plan.get("daily_plan", []))
            budget = plan.get("total_budget", 0)
            parts.append(f"行程：{days}天")
            if budget:
                parts.append(f"预算：{budget}元")

        if merged.get("food_recommendations"):
            food_count = len(merged["food_recommendations"])
            parts.append(f"美食推荐：{food_count}项")

        if merged.get("mental_health_tips"):
            tips_count = len(merged["mental_health_tips"])
            parts.append(f"健康建议：{tips_count}条")

        return " | ".join(parts)


# 示例用法
if __name__ == "__main__":
    agent = MergeAgent()

    # 模拟多个 Agent 的输出
    state = {
        "destination_recommendations": [
            {
                "name": "大理",
                "recommendation_score": 9,
                "travel_days": 5
            }
        ],
        "travel_plan": {
            "destination": "大理",
            "total_budget": 4500,
            "daily_plan": [
                {"day": 1, "activities": ["洱海"]},
                {"day": 2, "activities": ["苍山"]},
                {"day": 3, "activities": ["大理古城"]},
                {"day": 4, "activities": ["双廊"]},
                {"day": 5, "activities": ["返程"]}
            ]
        },
        "food_recommendations": [
            {"name": "喜洲粑粑", "health_rating": 8},
            {"name": "洱海鱼", "health_rating": 9}
        ],
        "mental_health_tips": [
            "保持愉悦心情",
            "适度安排行程"
        ]
    }

    result = agent.execute(state)

    print("=" * 50)
    print("融合后的内容：")
    print(f"\n摘要：{result['merged_content']['summary']}")

    print("\n一致性检查：")
    print(f"  是否一致：{result['consistency_report']['is_consistent']}")
    if result['consistency_report']['conflicts']:
        print(f"  冲突：{result['consistency_report']['conflicts']}")
    if result['consistency_report']['warnings']:
        print(f"  警告：{result['consistency_report']['warnings']}")
