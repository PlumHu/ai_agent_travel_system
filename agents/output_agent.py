"""
输出 Agent
生成最终交付物：客户报告（Markdown）
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from agents.base_agent import BaseAgent
from state import AgentState
from config import REPORTS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OutputAgent(BaseAgent):
    """输出 Agent：把 travel_plan 写成 Markdown 报告"""

    def __init__(self):
        super().__init__("OutputAgent")

    def execute(self, state: AgentState) -> AgentState:
        # 独立模式下若只有自然语言，先走 TravelAgent 生成行程再出报告
        if not state.get("travel_plan"):
            destination = state.get("destination") or self.infer_destination(
                state.get("user_input", "")
            )
            if destination:
                state["destination"] = destination
                from agents.travel_agent import travel_agent as travel_fn
                state = travel_fn(state)
        return output_agent(state)

    def _extract_output(self, state: AgentState) -> Dict[str, Any]:
        return {
            "type": "client_report",
            "destination": state.get("destination"),
            "client_report": state.get("client_report"),
            "travel_plan": state.get("travel_plan"),
            "error": state.get("error"),
        }


def output_agent(state: AgentState) -> AgentState:
    """
    输出 Agent 节点

    职责：
    1. 将旅行计划转换为 Markdown 格式的客户报告
    2. 保存到文件

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    logger.info("=" * 50)
    logger.info("[Output Agent] 生成最终报告")

    travel_plan = state.get("travel_plan")
    if not travel_plan:
        logger.warning("未找到旅行计划，无法生成报告")
        state["error"] = "缺少旅行计划"
        state["next_action"] = "end"
        return state

    destination = state.get("destination", "未知目的地")
    budget = state.get("budget", "未指定")

    # 生成 Markdown 报告
    markdown_content = f"""# {destination} 旅行计划

**生成时间:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**预算:** {budget} 元

---

## 📅 每日行程

"""

    # 添加每日行程
    for day_plan in travel_plan.get("day_by_day", []):
        day = day_plan.get("day", 0)
        date = day_plan.get("date", "未知日期")
        activities = day_plan.get("activities", [])
        meals = day_plan.get("meals", [])

        markdown_content += f"### Day {day} - {date}\n\n"
        markdown_content += "**活动安排:**\n"
        for activity in activities:
            markdown_content += f"- {activity}\n"

        if meals:
            markdown_content += "\n**餐饮推荐:**\n"
            for meal in meals:
                markdown_content += f"- {meal}\n"

        markdown_content += "\n"

    # 添加住宿建议
    markdown_content += "## 🏨 住宿建议\n\n"
    for acc in travel_plan.get("accommodation", []):
        markdown_content += f"- {acc}\n"

    # 添加美食推荐
    markdown_content += "\n## 🍜 美食推荐\n\n"
    for food in travel_plan.get("food", []):
        markdown_content += f"- {food}\n"

    # 添加预算分解
    markdown_content += "\n## 💰 预算分解\n\n"
    budget_breakdown = travel_plan.get("budget_breakdown", {})
    markdown_content += "| 项目 | 金额 (元) |\n|------|----------|\n"
    for item, amount in budget_breakdown.items():
        markdown_content += f"| {item} | {amount} |\n"

    total = sum(budget_breakdown.values())
    markdown_content += f"| **合计** | **{total}** |\n"

    # 添加旅行贴士
    markdown_content += "\n## 💡 旅行贴士\n\n"
    for tip in travel_plan.get("tips", []):
        markdown_content += f"- {tip}\n"

    markdown_content += "\n---\n\n*本报告由 AI Travel Agent 自动生成*\n"

    # 保存到文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{destination}_旅行计划_{timestamp}.md"
    filepath = REPORTS_DIR / filename

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"报告已保存: {filepath}")

        state["client_report"] = markdown_content
        state["current_step"] = "output_completed"
        state["next_action"] = "end"
        state["error"] = None

    except Exception as e:
        logger.error(f"保存报告失败: {e}")
        state["error"] = f"保存报告失败: {str(e)}"
        state["next_action"] = "end"

    return state
