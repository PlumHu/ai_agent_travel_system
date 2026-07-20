"""
需求解析 Agent（支持独立调用 + 流式输出 + 多 provider 兜底 + 反思自纠错）
解析用户输入，提取结构化信息并进行意图路由
"""
import json
import logging
import re
from typing import Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base_agent import BaseAgent
from agents.reflection import ParseOutputValidator, ValidationResult
from state import AgentState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParseAgent(BaseAgent):
    """需求解析 Agent（带反思验证）"""

    def __init__(self, long_term_memory=None, streaming_callback=None):
        super().__init__("ParseAgent", streaming_callback=streaming_callback)
        self.long_term_memory = long_term_memory
        self._validator = ParseOutputValidator()

    def execute(self, state: AgentState) -> AgentState:
        """执行解析逻辑（带反思循环）"""
        logger.info("=" * 50)
        logger.info("[Parse Agent] 开始解析用户需求（带反思）")

        return self.execute_with_reflection(
            state,
            execute_fn=self._do_parse,
            validate_fn=self._validate_output,
        )

    def _do_parse(self, state: AgentState) -> AgentState:
        """实际解析逻辑"""
        user_input = state["user_input"]
        logger.info(f"用户输入: {user_input}")

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
   - "recommend_time": 推荐出行时间
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
        ]

        # 注入长期记忆
        if self.long_term_memory is not None:
            try:
                mem_context = self.long_term_memory.get_memory_context(query=user_input)
                if mem_context:
                    messages.append(SystemMessage(content=mem_context))
                    logger.info("[ParseAgent] 已注入长期记忆")
            except Exception as e:
                logger.warning(f"[ParseAgent] 长期记忆注入失败: {e}")

        # 注入反思 critique（如果是重试）
        critique = state.get("_reflection_critique")
        if critique:
            messages.append(SystemMessage(
                content=f"[反思修正] 上次解析存在以下问题，请修正：\n{critique}\n"
                        f"请确保输出完整且格式正确。"
            ))
            logger.info(f"[ParseAgent] 已注入反思 critique")

        messages.append(HumanMessage(content=user_input))

        try:
            response_text = self._invoke_with_fallback(messages, streaming=False)
            logger.info(f"LLM 原始响应:\n{response_text}")

            # 提取 JSON
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text.strip()

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
            elif state["intent"] == "recommend_time":
                state["next_action"] = "recommend_time"
            else:
                state["next_action"] = "plan"

            logger.info(f"解析结果: dest={state['destination']}, intent={state['intent']}")
            state["current_step"] = "parse_completed"
            state["error"] = None

        except Exception as e:
            logger.error(f"解析失败: {e}")
            state["error"] = f"需求解析失败: {str(e)}"
            state["next_action"] = "end"

        return state

    def _validate_output(self, state: AgentState) -> ValidationResult:
        """验证解析输出的质量"""
        return self._validator.validate(state)

    def _extract_output(self, state: AgentState) -> Dict[str, Any]:
        """提取输出"""
        return {
            "destination": state.get("destination"),
            "start_date": state.get("start_date"),
            "end_date": state.get("end_date"),
            "budget": state.get("budget"),
            "preferences": state.get("preferences", []),
            "health_info": state.get("health_info"),
            "intent": state.get("intent"),
            "next_action": state.get("next_action"),
            "reflection_attempts": state.get("reflection_attempts", 0),
            "error": state.get("error")
        }


# 独立调用函数（兼容原有代码）
def parse_agent(state: AgentState) -> AgentState:
    """LangGraph 节点函数（保持兼容）"""
    agent = ParseAgent()
    return agent.execute(state)


# ============ 独立调用示例 ============

if __name__ == "__main__":
    # 示例 1：独立调用模式
    print("\n" + "=" * 60)
    print("示例 1：独立调用 Parse Agent")
    print("=" * 60)

    agent = ParseAgent()

    # 输入数据
    input_data = {
        "user_input": "我想6月中旬去大理玩5天，预算5000元，喜欢吃美食和看风景"
    }

    # 执行
    result = agent.run_standalone(input_data)

    if result["success"]:
        print("\n✅ 解析成功!")
        print(json.dumps(result["data"], ensure_ascii=False, indent=2))
    else:
        print(f"\n❌ 解析失败: {result['error']}")

    # 示例 2：推荐时间意图
    print("\n" + "=" * 60)
    print("示例 2：推荐最佳出行时间")
    print("=" * 60)

    input_data2 = {
        "user_input": "三亚什么时候去最合适？人少、天气好"
    }

    result2 = agent.run_standalone(input_data2)

    if result2["success"]:
        print("\n✅ 解析成功!")
        print(json.dumps(result2["data"], ensure_ascii=False, indent=2))
