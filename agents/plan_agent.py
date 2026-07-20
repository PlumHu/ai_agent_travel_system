"""
行程规划 Agent
根据目的地、时间、预算等信息生成详细的旅行行程规划
"""
import json
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from agents.base_agent import BaseAgent
from state import AgentState
from config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PlanAgent(BaseAgent):
    """行程规划 Agent"""

    def __init__(self):
        super().__init__("PlanAgent")

    def execute(self, state: AgentState) -> AgentState:
        """执行行程规划逻辑"""
        logger.info("=" * 50)
        logger.info("[Plan Agent] 开始行程规划")

        destination = state.get("destination") or self.infer_destination(state.get("user_input", ""))
        if destination and not state.get("destination"):
            state["destination"] = destination
        start_date = state.get("start_date")
        end_date = state.get("end_date")
        budget = state.get("budget")
        preferences = state.get("preferences", [])

        if not destination:
            state["error"] = "缺少目的地信息，无法进行行程规划"
            state["next_action"] = "end"
            return state

        # 计算行程天数
        days = self._calculate_days(start_date, end_date)

        # 调用 LLM 生成行程
        llm = ChatOpenAI(
            model=OPENAI_MODEL,
            temperature=0.7,
            openai_api_key=OPENAI_API_KEY,
            openai_api_base=OPENAI_API_BASE
        )

        system_prompt = f"""你是一个专业的旅行规划师。
请根据以下信息，生成详细的旅行行程规划。

**目的地：** {destination}
**出行日期：** {start_date or "未指定"} 至 {end_date or "未指定"}
**行程天数：** {days} 天
**预算：** {budget or "未指定"} 元
**用户偏好：** {", ".join(preferences) if preferences else "无特殊偏好"}

**输出要求：**
以 JSON 格式输出，包含每日详细行程：
- day_plan: 每日行程安排
- accommodation: 住宿建议
- transportation: 交通建议
- budget_breakdown: 预算分配
- tips: 实用贴士

示例格式：
```json
{{
  "destination": "{destination}",
  "total_days": {days},
  "day_plan": [
    {{
      "day": 1,
      "date": "{start_date or "待定"}",
      "theme": "抵达与休整",
      "activities": [
        {{
          "time": "上午",
          "activity": "抵达{destination}",
          "location": "机场/火车站",
          "duration": "2小时",
          "cost": "交通费用",
          "tips": "提前预订接机服务"
        }}
      ],
      "meals": [
        {{ "time": "午餐", "recommendation": "当地特色餐厅", "budget": "100元" }}
      ]
    }}
  ],
  "accommodation": {{
    "recommended_area": "市中心/景区附近",
    "budget_option": "经济型酒店，200-300元/晚",
    "comfort_option": "舒适型酒店，400-600元/晚",
    "luxury_option": "高端酒店，800+元/晚"
  }},
  "transportation": {{
    "arrival": "飞机/高铁",
    "local_transport": "地铁/公交/打车",
    "tips": "建议购买交通卡"
  }},
  "budget_breakdown": {{
    "transportation": "占比20%",
    "accommodation": "占比30%",
    "food": "占比25%",
    "tickets": "占比15%",
    "shopping": "占比10%"
  }},
  "tips": [
    "建议提前预订热门景点门票",
    "注意当地天气变化",
    "保存紧急联系方式"
  ]
}}
```
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请为{destination}生成{days}天的详细行程规划")
        ]

        try:
            response = llm.invoke(messages)
            response_text = response.content

            # 提取 JSON
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text.strip()

            travel_plan = json.loads(json_str)
            state["travel_plan"] = travel_plan

            logger.info(f"行程规划完成: {destination}, {days}天")

            state["current_step"] = "plan_completed"
            state["next_action"] = "output"
            state["error"] = None

        except Exception as e:
            logger.error(f"行程规划失败: {e}")
            state["error"] = f"行程规划失败: {str(e)}"
            state["next_action"] = "end"

        return state

    def _calculate_days(self, start_date: str, end_date: str) -> int:
        """计算行程天数"""
        if not start_date or not end_date:
            return 3  # 默认3天

        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            return max(1, (end - start).days + 1)
        except:
            return 3

    def _extract_output(self, state: AgentState) -> Dict[str, Any]:
        """提取输出"""
        return {
            "type": "travel_plan",
            "destination": state.get("destination"),
            "plan": state.get("travel_plan"),
            "error": state.get("error")
        }


# 独立调用函数（兼容 LangGraph）
def plan_agent(state: AgentState) -> AgentState:
    """LangGraph 节点函数"""
    agent = PlanAgent()
    return agent.execute(state)


# ============ 测试示例 ============

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("行程规划 Agent 测试")
    print("=" * 60)

    agent = PlanAgent()

    input_data = {
        "user_input": "我想去大理旅游5天",
        "destination": "大理",
        "start_date": "2026-07-01",
        "end_date": "2026-07-05",
        "budget": 5000,
        "preferences": ["自然风光", "美食"]
    }

    result = agent.run_standalone(input_data)

    if result["success"]:
        print("\n✅ 行程规划成功!")
        print(json.dumps(result["data"], ensure_ascii=False, indent=2))
    else:
        print(f"\n❌ 规划失败: {result['error']}")
