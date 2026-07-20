"""
需求解析 Agent
解析用户输入，提取结构化信息并进行意图路由
"""
import json
import logging
import re
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from state import AgentState
from config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL, TEMPERATURE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_agent(state: AgentState) -> AgentState:
    """
    需求解析 Agent 节点

    职责：
    1. 解析用户输入
    2. 提取结构化信息（目的地、日期、预算等）
    3. 识别意图并决定下一步路由

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    logger.info("=" * 50)
    logger.info("[Parse Agent] 开始解析用户需求")

    user_input = state["user_input"]
    logger.info(f"用户输入: {user_input}")

    # 初始化 LLM
    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=TEMPERATURE,
        openai_api_key=OPENAI_API_KEY,
        openai_api_base=OPENAI_API_BASE
    )

    # 构造提示词
    system_prompt = """你是一个专业的旅行需求分析师。
请分析用户的旅行需求，提取以下结构化信息：

1. **目的地** (destination): 用户想去的地方（如果没有明确提及，返回 null）
2. **出发日期** (start_date): 格式 YYYY-MM-DD（如果没有，返回 null）
3. **返回日期** (end_date): 格式 YYYY-MM-DD（如果没有，返回 null）
4. **预算** (budget): 数字（元），如果没有返回 null
5. **偏好** (preferences): 用户的旅行偏好列表（如["美食", "文化", "自然风光"]）
6. **健康信息** (health_info): 过敏、疾病等健康相关信息
7. **意图** (intent):
   - "plan_trip": 已有目的地，需要规划行程
   - "recommend_destination": 没有目的地，需要推荐
   - "food_advice": 主要咨询美食相关
   - "general_inquiry": 一般性咨询

**请以 JSON 格式输出，不要包含任何额外的文字解释。**

示例输出：
```json
{
  "destination": "大理",
  "start_date": "2026-06-15",
  "end_date": "2026-06-20",
  "budget": 5000,
  "preferences": ["美食", "文化"],
  "health_info": null,
  "intent": "plan_trip"
}
```
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ]

    try:
        # 调用 LLM
        response = llm.invoke(messages)
        response_text = response.content

        logger.info(f"LLM 原始响应:\n{response_text}")

        # 提取 JSON（处理可能的 markdown 代码块）
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析
            json_str = response_text.strip()

        # 解析 JSON
        parsed_data = json.loads(json_str)

        # 更新状态
        state["destination"] = parsed_data.get("destination")
        state["start_date"] = parsed_data.get("start_date")
        state["end_date"] = parsed_data.get("end_date")
        state["budget"] = parsed_data.get("budget")
        state["preferences"] = parsed_data.get("preferences", [])
        state["health_info"] = parsed_data.get("health_info")
        state["intent"] = parsed_data.get("intent", "general_inquiry")

        # 决定下一步路由
        if state["intent"] == "recommend_destination":
            state["next_action"] = "recommend"
        elif state["intent"] == "plan_trip":
            state["next_action"] = "plan"
        else:
            state["next_action"] = "plan"  # 默认进入规划流程

        logger.info(f"解析结果:")
        logger.info(f"  - 目的地: {state['destination']}")
        logger.info(f"  - 日期: {state['start_date']} ~ {state['end_date']}")
        logger.info(f"  - 预算: {state['budget']}")
        logger.info(f"  - 偏好: {state['preferences']}")
        logger.info(f"  - 意图: {state['intent']}")
        logger.info(f"  - 下一步: {state['next_action']}")

        state["current_step"] = "parse_completed"
        state["error"] = None

    except Exception as e:
        logger.error(f"解析失败: {e}")
        state["error"] = f"需求解析失败: {str(e)}"
        state["next_action"] = "end"

    return state


# 测试代码
if __name__ == "__main__":
    from state import create_initial_state

    test_input = "我想6月中旬去大理玩5天，预算5000元，喜欢吃美食和看风景"
    state = create_initial_state(test_input)
    result = parse_agent(state)

    print("\n解析结果:")
    print(json.dumps({
        "destination": result["destination"],
        "start_date": result["start_date"],
        "end_date": result["end_date"],
        "budget": result["budget"],
        "preferences": result["preferences"],
        "intent": result["intent"],
        "next_action": result["next_action"]
    }, ensure_ascii=False, indent=2))
