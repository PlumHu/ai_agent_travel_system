"""
ReAct 循环 Agent（Agent Loop）
==============================
实现 Think → Act → Observe 的迭代循环，让 LLM 自主决定调用哪个工具、
何时停止，而非固定 Pipeline 的硬编码流程。

这是 Agent 与 Chain 的本质区别：
  - Chain / 固定 Pipeline：工具调用次数和顺序写死
  - Agent Loop：每轮由 LLM 推理动态决定下一步动作

循环结构：
    for i in range(max_iterations):
        thought, action = Think(user_input, scratchpad)   # LLM 推理
        if action == final_answer: break                   # 终止判断
        observation = Act(action)                          # 执行工具
        scratchpad.append(thought, action, observation)    # 观察记录

适用场景：复杂开放式查询（多目的地对比、多约束、需多次动态取数）。
简单意图仍建议走固定 Pipeline（更快、更省 token）。

安全：复用 BudgetLimiter 限制工具调用次数，工具异常隔离不中断循环。
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from agents.base_agent import BaseAgent
from state import AgentState

logger = logging.getLogger(__name__)


# ToolSpec 已上移至统一工具注册中心 tools/registry.py。
# 此处 re-export 保持向后兼容（旧代码 from agents.react_agent import ToolSpec 仍可用）。
from tools.registry import ToolSpec  # noqa: E402


@dataclass
class ReActStep:
    """单轮循环记录"""
    iteration: int
    thought: str
    action: str = ""
    action_input: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    is_final: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation[:500] if self.observation else "",
            "is_final": self.is_final,
        }


class ReActAgent(BaseAgent):
    """
    ReAct 风格循环 Agent。

    使用方式：
        tools = {
            "get_weather": ToolSpec("get_weather", get_weather, "查询城市天气", {"city": "城市名"}),
            ...
        }
        agent = ReActAgent(tools=tools, budget_limiter=limiter)
        result = agent.run_standalone({"user_input": "对比大理和丽江的天气"})
    """

    def __init__(
        self,
        tools: Optional[Dict[str, ToolSpec]] = None,
        max_iterations: int = None,
        budget_limiter=None,
        streaming_callback=None,
    ):
        super().__init__("ReActAgent", streaming_callback=streaming_callback)
        self.tools = tools or {}
        self.budget_limiter = budget_limiter

        # 默认从 config 读取 MAX_ITERATIONS
        if max_iterations is None:
            try:
                from config import MAX_ITERATIONS
                max_iterations = MAX_ITERATIONS
            except Exception:
                max_iterations = 10
        self.max_iterations = max_iterations

    def register_tool(self, spec: ToolSpec) -> None:
        """注册一个工具"""
        self.tools[spec.name] = spec

    def execute(self, state: AgentState) -> AgentState:
        """执行 ReAct 循环"""
        user_input = state["user_input"]
        logger.info("=" * 50)
        logger.info(f"[ReActAgent] 开始 Agent Loop: {user_input[:50]}")

        scratchpad: List[ReActStep] = []

        for i in range(self.max_iterations):
            # ── 1. Think: LLM 决定下一步 ──
            try:
                decision = self._think(user_input, scratchpad)
            except Exception as e:
                logger.error(f"[ReActAgent] Think 阶段失败: {e}")
                state["error"] = f"ReAct 推理失败: {str(e)}"
                break

            thought = decision.get("thought", "")

            # ── 2. 终止判断 ──
            if decision.get("final_answer"):
                step = ReActStep(
                    iteration=i + 1,
                    thought=thought,
                    is_final=True,
                    observation=decision["final_answer"],
                )
                scratchpad.append(step)
                state["react_answer"] = decision["final_answer"]
                logger.info(f"[ReActAgent] 第 {i+1} 轮产出最终答案，循环结束")
                break

            action = decision.get("action", "")
            action_input = decision.get("action_input", {})

            # ── 3. 工具调用限流检查 ──
            if self.budget_limiter is not None:
                tool_status = self.budget_limiter.check_tool_call()
                if not tool_status.allowed:
                    logger.warning(f"[ReActAgent] 工具调用受限，强制结束: {tool_status.reason}")
                    state["react_answer"] = self._force_final_answer(user_input, scratchpad)
                    break

            # ── 4. Act: 执行工具 ──
            observation = self._act(action, action_input)

            if self.budget_limiter is not None:
                self.budget_limiter.record_tool_call()

            # ── 5. Observe: 记录 ──
            step = ReActStep(
                iteration=i + 1,
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
            )
            scratchpad.append(step)
            logger.info(f"[ReActAgent] 第 {i+1} 轮: action={action}")

        else:
            # for 循环正常结束（未 break）= 达到 max_iterations
            logger.warning(f"[ReActAgent] 达到最大轮数 {self.max_iterations}，强制生成答案")
            if not state.get("react_answer"):
                state["react_answer"] = self._force_final_answer(user_input, scratchpad)

        # 写入 state
        state["react_scratchpad"] = [s.to_dict() for s in scratchpad]
        state["react_iterations"] = len(scratchpad)
        state["current_step"] = "react_completed"
        if not state.get("error"):
            state["error"] = None
        return state

    def _think(self, user_input: str, scratchpad: List[ReActStep]) -> Dict[str, Any]:
        """
        Think 阶段：LLM 基于历史 scratchpad 决定下一步动作。

        Returns:
            {"thought": ..., "action": ..., "action_input": {...}}
            或 {"thought": ..., "final_answer": "..."}
        """
        system_prompt = self._build_system_prompt()
        scratchpad_text = self._render_scratchpad(scratchpad)

        human_content = f"""用户请求：{user_input}

{scratchpad_text}

请决定下一步。若信息已足够，直接给出 final_answer；否则选择一个工具调用。
严格按 JSON 格式输出。"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_content),
        ]

        response_text = self._invoke_with_fallback(messages, streaming=False)
        return self._parse_decision(response_text)

    def _build_system_prompt(self) -> str:
        """构造含工具清单的 ReAct system prompt"""
        tools_desc = "\n".join(spec.render() for spec in self.tools.values())

        return f"""你是一个旅行规划 ReAct 智能体，通过"思考-行动-观察"循环解决问题。

可用工具：
{tools_desc}

工作方式：
1. 分析用户请求和已有观察结果（Observation）
2. 若还需更多信息，选择一个工具调用
3. 若信息已足够，直接给出最终答案

输出格式（严格 JSON，二选一）：

调用工具时：
```json
{{
  "thought": "我需要先查询大理的天气来判断是否适合出行",
  "action": "get_weather",
  "action_input": {{"city": "大理"}}
}}
```

给出最终答案时：
```json
{{
  "thought": "已收集到天气和攻略信息，可以回答了",
  "final_answer": "根据查询结果，大理当前..."
}}
```

规则：
- action 必须是上述工具名之一
- 不要重复调用相同参数的工具
- 最多可调用 {self.max_iterations} 次工具，请高效决策
- 只输出 JSON，不要额外文字"""

    def _render_scratchpad(self, scratchpad: List[ReActStep]) -> str:
        """把历史循环渲染成文本供 LLM 参考"""
        if not scratchpad:
            return "（暂无历史记录，这是第一轮）"

        lines = ["已执行的步骤："]
        for step in scratchpad:
            lines.append(f"[第{step.iteration}轮] 思考: {step.thought}")
            if step.action:
                lines.append(f"  行动: {step.action}({json.dumps(step.action_input, ensure_ascii=False)})")
                lines.append(f"  观察: {step.observation[:300]}")
        return "\n".join(lines)

    def _parse_decision(self, response_text: str) -> Dict[str, Any]:
        """从 LLM 响应中解析决策 JSON"""
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试找第一个 { 到最后一个 }
            start = response_text.find("{")
            end = response_text.rfind("}")
            json_str = response_text[start:end + 1] if start >= 0 and end > start else response_text.strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"[ReActAgent] 决策 JSON 解析失败: {e}，降级为最终答案")
            return {"thought": "解析失败", "final_answer": response_text[:500]}

    def _act(self, action: str, action_input: Dict[str, Any]) -> str:
        """
        Act 阶段：执行工具调用。
        工具异常被隔离为错误 observation，循环继续（让 LLM 换策略）。
        """
        if action not in self.tools:
            return f"错误：工具 '{action}' 不存在。可用工具: {list(self.tools.keys())}"

        spec = self.tools[action]

        if self.streaming_callback:
            self.streaming_callback.on_tool_start(action, self.name)

        try:
            result = spec.func(**action_input) if action_input else spec.func()
            observation = str(result)
            success = True
        except TypeError as e:
            observation = f"工具参数错误: {e}。请检查 action_input 是否符合 {spec.args_schema}"
            success = False
        except Exception as e:
            observation = f"工具执行失败: {e}"
            success = False
            logger.warning(f"[ReActAgent] 工具 {action} 执行失败: {e}")

        if self.streaming_callback:
            self.streaming_callback.on_tool_end(action, success, self.name)

        return observation

    def _force_final_answer(self, user_input: str, scratchpad: List[ReActStep]) -> str:
        """达到上限或受限时，用已有信息强制生成答案"""
        scratchpad_text = self._render_scratchpad(scratchpad)
        messages = [
            SystemMessage(content="你是旅行规划助手。请基于已收集的信息，尽力给出一个有用的最终回答。"),
            HumanMessage(content=f"用户请求：{user_input}\n\n{scratchpad_text}\n\n请直接给出最终回答（不要再调用工具）。"),
        ]
        try:
            return self._invoke_with_fallback(messages, streaming=False)
        except Exception as e:
            logger.error(f"[ReActAgent] 强制答案生成失败: {e}")
            return "抱歉，收集信息时遇到问题，无法给出完整回答。请稍后重试或简化您的请求。"

    def _extract_output(self, state: AgentState) -> Dict[str, Any]:
        """提取输出"""
        return {
            "type": "react_result",
            "answer": state.get("react_answer"),
            "iterations": state.get("react_iterations", 0),
            "scratchpad": state.get("react_scratchpad", []),
            "error": state.get("error"),
        }
