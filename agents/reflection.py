"""
Reflection 反思与自纠错模块
===========================
提供 Agent 执行后的质量验证和自动修正能力。

核心机制：
  1. execute_with_reflection() — 带反思的执行循环
  2. 验证器（Validator）— 检查输出质量
  3. Critique 注入 — 将验证失败原因注入下一次 LLM 调用

设计模式：
  采用 Mixin 方式混入 BaseAgent，任何 Agent 可复用。
  验证器可以是规则式（快，无成本）或 LLM-as-Judge（准，有成本）。

使用方式：
    class MyAgent(BaseAgent, ReflectionMixin):
        def execute(self, state):
            return self.execute_with_reflection(
                state,
                execute_fn=self._do_execute,
                validate_fn=self._validate_output,
            )
"""
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from state import AgentState

logger = logging.getLogger(__name__)


# ── 验证结果 ─────────────────────────────────────────────────────
class ValidationResult:
    """验证结果"""

    def __init__(self, is_valid: bool, critique: str = "", details: Dict[str, Any] = None):
        self.is_valid = is_valid
        self.critique = critique
        self.details = details or {}

    def __bool__(self):
        return self.is_valid

    def __repr__(self):
        status = "✅ PASS" if self.is_valid else "❌ FAIL"
        return f"ValidationResult({status}, critique='{self.critique[:50]}')"


# ── Reflection Mixin ─────────────────────────────────────────────
class ReflectionMixin:
    """
    反思能力混入类。

    任何继承 BaseAgent 的 Agent 都可以同时混入此类，
    获得 execute_with_reflection() 方法。
    """

    MAX_REFLECTION_RETRIES: int = 2  # 最大反思重试次数

    def execute_with_reflection(
        self,
        state: AgentState,
        execute_fn: Callable[[AgentState], AgentState],
        validate_fn: Callable[[AgentState], ValidationResult],
        max_retries: int = None,
    ) -> AgentState:
        """
        带反思的执行循环。

        流程：
          1. 调用 execute_fn(state) 执行 Agent 逻辑
          2. 调用 validate_fn(state) 验证输出质量
          3. 若验证通过 → 返回 state
          4. 若验证失败 → 将 critique 注入 state，重试
          5. 超过 max_retries 次后，仍返回最后一次的 state（附带警告）

        Args:
            state: 当前 Agent 状态
            execute_fn: 执行函数（接收 state，返回更新后的 state）
            validate_fn: 验证函数（接收 state，返回 ValidationResult）
            max_retries: 最大重试次数（默认用类属性）

        Returns:
            执行并验证后的 state
        """
        retries = max_retries if max_retries is not None else self.MAX_REFLECTION_RETRIES
        agent_name = getattr(self, "name", "UnknownAgent")

        for attempt in range(retries + 1):
            # 执行
            state = execute_fn(state)

            # 执行报错，直接返回（不做反思）
            if state.get("error"):
                logger.warning(
                    f"[Reflection:{agent_name}] 执行出错，跳过反思: {state['error']}"
                )
                return state

            # 验证
            result = validate_fn(state)

            if result.is_valid:
                # 验证通过
                state["reflection_attempts"] = attempt
                state["_reflection_critique"] = None
                if attempt > 0:
                    logger.info(
                        f"[Reflection:{agent_name}] 第 {attempt + 1} 次尝试验证通过"
                    )
                return state

            # 验证失败
            logger.warning(
                f"[Reflection:{agent_name}] 第 {attempt + 1}/{retries + 1} 次验证未通过"
                f" | Critique: {result.critique}"
            )

            # 最后一次也失败了
            if attempt == retries:
                state["reflection_attempts"] = attempt + 1
                state["_reflection_critique"] = result.critique
                logger.error(
                    f"[Reflection:{agent_name}] 已达最大重试次数 ({retries})，"
                    f"返回最后结果，附带 critique"
                )
                return state

            # 注入 critique 准备重试
            state["_reflection_critique"] = result.critique

        return state


# ── 内置验证器 ────────────────────────────────────────────────────

class ParseOutputValidator:
    """
    ParseAgent 输出验证器。

    规则式验证（零成本，毫秒级）：
    - intent 必须在合法范围内
    - destination 格式合法（非空、长度 2~10）
    - budget 若存在必须为正数
    - 日期格式合法（YYYY-MM-DD）
    - start_date 不晚于 end_date
    """

    VALID_INTENTS = {
        "plan_trip",
        "recommend_destination",
        "recommend_time",
        "food_advice",
        "general_inquiry",
    }

    def validate(self, state: AgentState) -> ValidationResult:
        """验证 ParseAgent 的输出"""
        issues = []

        # 1. intent 检查
        intent = state.get("intent")
        if not intent:
            issues.append("缺少 intent 字段")
        elif intent not in self.VALID_INTENTS:
            issues.append(f"intent='{intent}' 不在合法范围: {self.VALID_INTENTS}")

        # 2. destination 检查（plan_trip/recommend_time 时必须有）
        destination = state.get("destination")
        if intent in ("plan_trip", "recommend_time"):
            if not destination:
                issues.append(f"intent={intent} 但未提取到 destination")
            elif len(destination) < 2 or len(destination) > 10:
                issues.append(f"destination='{destination}' 长度异常（应 2~10 字符）")

        # 3. budget 检查
        budget = state.get("budget")
        if budget is not None:
            try:
                budget_val = float(budget)
                if budget_val <= 0:
                    issues.append(f"budget={budget} 不是正数")
                elif budget_val > 1000000:
                    issues.append(f"budget={budget} 超出合理范围（>100万）")
            except (TypeError, ValueError):
                issues.append(f"budget='{budget}' 无法转为数字")

        # 4. 日期格式检查
        for date_field in ("start_date", "end_date"):
            date_val = state.get(date_field)
            if date_val:
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date_val)):
                    issues.append(f"{date_field}='{date_val}' 格式不是 YYYY-MM-DD")
                else:
                    try:
                        datetime.strptime(str(date_val), "%Y-%m-%d")
                    except ValueError:
                        issues.append(f"{date_field}='{date_val}' 不是合法日期")

        # 5. 日期逻辑检查
        start = state.get("start_date")
        end = state.get("end_date")
        if start and end:
            try:
                s = datetime.strptime(str(start), "%Y-%m-%d")
                e = datetime.strptime(str(end), "%Y-%m-%d")
                if s > e:
                    issues.append(f"start_date({start}) 晚于 end_date({end})")
            except ValueError:
                pass  # 格式已在上面检查过

        if issues:
            critique = "解析输出验证失败：\n" + "\n".join(f"  - {i}" for i in issues)
            return ValidationResult(False, critique, {"issues": issues})

        return ValidationResult(True)


class TravelPlanValidator:
    """
    TravelAgent 行程规划输出验证器。

    规则式验证：
    - travel_plan 存在且非空
    - 包含必要字段：day_by_day, budget_breakdown
    - 行程天数 > 0
    - 预算分解总和与声明预算偏差不超过 30%
    - 每日行程至少有 1 个活动
    """

    def validate(self, state: AgentState) -> ValidationResult:
        """验证 TravelAgent 的输出"""
        issues = []

        travel_plan = state.get("travel_plan")
        if not travel_plan:
            return ValidationResult(False, "travel_plan 为空")

        if not isinstance(travel_plan, dict):
            return ValidationResult(False, f"travel_plan 类型异常: {type(travel_plan)}")

        # 1. 必要字段检查
        required_fields = ["day_by_day", "budget_breakdown"]
        for field in required_fields:
            if field not in travel_plan:
                issues.append(f"缺少必要字段: {field}")

        # 2. 行程天数
        day_by_day = travel_plan.get("day_by_day", [])
        if not day_by_day:
            issues.append("day_by_day 为空（无行程安排）")
        elif len(day_by_day) > 30:
            issues.append(f"行程天数异常: {len(day_by_day)} 天（>30）")

        # 3. 每日行程内容
        for i, day in enumerate(day_by_day):
            if not isinstance(day, dict):
                issues.append(f"第 {i+1} 天数据格式错误")
                continue
            activities = day.get("activities", [])
            if not activities:
                issues.append(f"第 {i+1} 天没有活动安排")

        # 4. 预算合理性
        budget_breakdown = travel_plan.get("budget_breakdown", {})
        declared_budget = state.get("budget")
        if budget_breakdown and declared_budget:
            try:
                total = sum(float(v) for v in budget_breakdown.values())
                declared = float(declared_budget)
                if declared > 0:
                    deviation = abs(total - declared) / declared
                    if deviation > 0.3:
                        issues.append(
                            f"预算分解总和({total})与声明预算({declared})"
                            f"偏差 {deviation:.0%}，超过 30%"
                        )
            except (TypeError, ValueError):
                pass  # 数据格式有误，跳过

        if issues:
            critique = "行程规划验证失败：\n" + "\n".join(f"  - {i}" for i in issues)
            return ValidationResult(False, critique, {"issues": issues})

        return ValidationResult(True)


class RecommendationValidator:
    """
    RecommendAgent 推荐输出验证器。

    验证推荐结果的完整性和合理性。
    """

    def validate(self, state: AgentState) -> ValidationResult:
        """验证推荐输出"""
        issues = []
        intent = state.get("intent")

        if intent == "recommend_time":
            time_rec = state.get("time_recommendation")
            if not time_rec:
                return ValidationResult(False, "time_recommendation 为空")

            best_periods = time_rec.get("best_periods", [])
            if not best_periods:
                issues.append("未提供任何推荐时间段（best_periods 为空）")
            elif len(best_periods) > 5:
                issues.append(f"推荐时间段过多: {len(best_periods)} 个")

        else:
            dest_rec = state.get("destination_recommendation")
            if not dest_rec:
                return ValidationResult(False, "destination_recommendation 为空")

            recommendations = dest_rec.get("recommendations", [])
            if not recommendations:
                issues.append("未提供任何推荐目的地（recommendations 为空）")
            else:
                for i, rec in enumerate(recommendations):
                    if not rec.get("destination"):
                        issues.append(f"第 {i+1} 个推荐缺少 destination 字段")

        if issues:
            critique = "推荐输出验证失败：\n" + "\n".join(f"  - {i}" for i in issues)
            return ValidationResult(False, critique, {"issues": issues})

        return ValidationResult(True)


# ── LLM-as-Judge 验证器（高级，有 API 成本）─────────────────────────

class LLMJudgeValidator:
    """
    使用 LLM 对 Agent 输出进行综合质量评估。

    适用场景：
    - 规则无法覆盖的语义质量（如行程是否地理合理）
    - 最终输出的整体可用性评估

    注意：每次调用消耗 token，仅在规则验证通过后的最终检查使用。
    """

    JUDGE_PROMPT = """你是一个旅行规划质量评审专家。
请评估以下旅行规划的质量，从以下维度打分（每项 0-10 分）：

1. **信息完整性**：行程、住宿、餐饮、预算是否齐全
2. **逻辑一致性**：日程安排是否合理（地理距离、时间分配）
3. **实用性**：建议是否具体可操作（而非泛泛而谈）
4. **个性化**：是否针对用户偏好做了定制

用户需求：{user_input}
目的地：{destination}
预算：{budget}

行程规划：
{travel_plan}

请以 JSON 格式输出评估结果：
```json
{{
  "completeness": 8,
  "consistency": 7,
  "practicality": 9,
  "personalization": 6,
  "overall": 7.5,
  "critique": "简短的改进建议（50字以内）",
  "pass": true
}}
```

注意：overall >= 6 时 pass=true，否则 pass=false。
"""

    def __init__(self, llm=None, pass_threshold: float = 6.0):
        self.llm = llm
        self.pass_threshold = pass_threshold

    def validate(self, state: AgentState) -> ValidationResult:
        """使用 LLM 评估行程质量"""
        if self.llm is None:
            # 无 LLM 时默认通过（降级为规则验证）
            return ValidationResult(True)

        travel_plan = state.get("travel_plan", {})
        if not travel_plan:
            return ValidationResult(False, "无行程规划可评估")

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            prompt = self.JUDGE_PROMPT.format(
                user_input=state.get("user_input", ""),
                destination=state.get("destination", "未知"),
                budget=state.get("budget", "未指定"),
                travel_plan=json.dumps(travel_plan, ensure_ascii=False, indent=2)[:2000],
            )

            response = self.llm.invoke([HumanMessage(content=prompt)])
            response_text = response.content

            # 提取 JSON
            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
            )
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                result = json.loads(response_text.strip())

            overall = float(result.get("overall", 0))
            is_pass = result.get("pass", overall >= self.pass_threshold)
            critique = result.get("critique", "")

            return ValidationResult(
                is_valid=is_pass,
                critique=critique if not is_pass else "",
                details=result,
            )

        except Exception as e:
            logger.warning(f"[LLMJudge] 评估失败，降级为通过: {e}")
            return ValidationResult(True)
