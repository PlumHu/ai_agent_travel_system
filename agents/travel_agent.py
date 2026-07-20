"""
旅行规划 Agent
基于用户需求和 RAG 检索结果，生成完整的旅行计划
"""
import json
import logging
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from agents.base_agent import BaseAgent
from state import AgentState
from config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL, TEMPERATURE
from knowledge.rag_manager import RAGManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TravelAgent(BaseAgent):
    """旅行规划 Agent（独立调用 + LangGraph 节点共用逻辑）"""

    def __init__(self):
        super().__init__("TravelAgent")

    def execute(self, state: AgentState) -> AgentState:
        if not state.get("destination"):
            inferred = self.infer_destination(state.get("user_input", ""))
            if inferred:
                state["destination"] = inferred
        return travel_agent(state)

    def _extract_output(self, state: AgentState) -> Dict[str, Any]:
        return {
            "type": "travel_plan",
            "destination": state.get("destination"),
            "travel_plan": state.get("travel_plan"),
            "retrieved_docs": state.get("retrieved_docs"),
            "error": state.get("error"),
        }


def travel_agent(state: AgentState) -> AgentState:
    """
    旅行规划 Agent 节点

    职责：
    1. 从 RAG 检索相关知识
    2. 调用工具获取实时信息（天气、路线等）
    3. 生成完整的旅行计划

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    logger.info("=" * 50)
    logger.info("[Travel Agent] 开始规划旅行")

    destination = state.get("destination")
    start_date = state.get("start_date")
    end_date = state.get("end_date")
    budget = state.get("budget")
    preferences = state.get("preferences", [])

    if not destination:
        logger.warning("未提供目的地，无法规划")
        state["error"] = "缺少目的地信息"
        state["next_action"] = "end"
        return state

    # Step 1: RAG 检索相关知识
    logger.info(f"检索目的地知识: {destination}")
    try:
        rag = RAGManager()
        query = f"{destination} 旅行攻略 景点 美食"
        retrieved_docs = rag.retrieve(query, top_k=3)
        state["retrieved_docs"] = retrieved_docs

        # 提取检索到的文本
        context_text = "\n\n".join([
            f"文档 {i+1}:\n{doc['text']}"
            for i, doc in enumerate(retrieved_docs)
        ])

        logger.info(f"检索到 {len(retrieved_docs)} 条相关文档")

    except Exception as e:
        logger.error(f"RAG 检索失败: {e}")
        context_text = "（未能检索到相关知识库内容）"

    # Step 2: 构造提示词并调用 LLM
    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=TEMPERATURE,
        openai_api_key=OPENAI_API_KEY,
        openai_api_base=OPENAI_API_BASE
    )

    system_prompt = f"""你是一个专业的旅行规划师。
请根据以下信息，为用户生成一份详细的旅行计划：

**用户需求：**
- 目的地：{destination}
- 出发日期：{start_date or "未指定"}
- 返回日期：{end_date or "未指定"}
- 预算：{budget or "未指定"} 元
- 偏好：{", ".join(preferences) if preferences else "无特殊偏好"}

**知识库参考：**
{context_text}

**输出要求：**
请以 JSON 格式输出旅行计划，包含以下字段：
- day_by_day: 每日行程安排（数组）
- accommodation: 住宿建议
- food: 美食推荐
- budget_breakdown: 预算分解
- tips: 旅行贴士

示例格式：
```json
{{
  "day_by_day": [
    {{"day": 1, "date": "2026-06-15", "activities": ["抵达大理", "入住酒店", "古城夜游"], "meals": ["晚餐：喜洲粑粑"]}},
    {{"day": 2, "date": "2026-06-16", "activities": ["洱海骑行", "喜洲古镇"], "meals": ["早餐：饵丝", "午餐：砂锅鱼"]}}
  ],
  "accommodation": ["推荐：洱海边民宿，预算 300-500 元/晚"],
  "food": ["喜洲粑粑", "大理砂锅鱼", "白族三道茶"],
  "budget_breakdown": {{"交通": 1500, "住宿": 1500, "餐饮": 1000, "门票": 500, "其他": 500}},
  "tips": ["紫外线强，注意防晒", "早晚温差大"]
}}
```
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"请为我规划{destination}的旅行")
    ]

    try:
        response = llm.invoke(messages)
        response_text = response.content

        logger.info(f"LLM 响应长度: {len(response_text)} 字符")

        # 提取 JSON
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response_text.strip()

        travel_plan = json.loads(json_str)
        state["travel_plan"] = travel_plan

        logger.info("旅行计划生成成功")
        logger.info(f"  - 行程天数: {len(travel_plan.get('day_by_day', []))}")
        logger.info(f"  - 美食推荐: {len(travel_plan.get('food', []))}")

        state["current_step"] = "travel_plan_completed"
        state["next_action"] = "output"
        state["error"] = None

    except Exception as e:
        logger.error(f"旅行规划失败: {e}")
        state["error"] = f"旅行规划失败: {str(e)}"
        state["next_action"] = "end"

    return state
