"""
LLM-as-Judge 评分器
====================
使用 LLM 对 Agent 输出进行综合质量评估。
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class JudgeScore:
    """LLM 评分结果"""
    completeness: float = 0.0        # 信息完整性（0-10）
    consistency: float = 0.0         # 逻辑一致性（0-10）
    practicality: float = 0.0        # 建议实用性（0-10）
    personalization: float = 0.0     # 个性化程度（0-10）
    overall: float = 0.0             # 综合评分（0-10）
    critique: str = ""               # 改进建议
    passed: bool = False             # 是否达标（overall >= threshold）


class LLMJudge:
    """
    LLM-as-Judge 评分器。

    使用一个 LLM 对 Agent 的输出进行多维度质量评估。
    这是业界通用的 Agent 评估方式，弥补规则式指标的不足。

    使用方式：
        judge = LLMJudge(llm=your_llm)
        score = judge.evaluate(
            user_input="我想去大理玩5天",
            agent_output=travel_plan_json,
            context={"destination": "大理", "budget": 5000}
        )
        print(score.overall, score.critique)
    """

    JUDGE_PROMPT = """你是一位旅行规划质量评审专家。请对以下旅行规划输出进行严格评估。

## 用户需求
{user_input}

## Agent 输出
{agent_output}

## 额外上下文
- 目的地：{destination}
- 预算：{budget} 元
- 偏好：{preferences}

## 评分维度（每项 0-10 分）

1. **信息完整性 (completeness)**：行程安排、住宿、餐饮、交通、预算是否齐全？
   - 10分：所有维度都有详细具体的信息
   - 5分：覆盖大部分维度但有遗漏
   - 0分：严重不完整

2. **逻辑一致性 (consistency)**：日程安排是否地理合理？时间分配是否可行？
   - 10分：所有安排都符合现实逻辑
   - 5分：大部分合理，少量不太可行
   - 0分：存在明显不合理（如一天安排跨省）

3. **建议实用性 (practicality)**：是否给出具体可操作的建议？
   - 10分：有具体名称、地址/方位、价格区间、营业时间等
   - 5分：有方向性建议但不够具体
   - 0分：全是空泛的套话

4. **个性化程度 (personalization)**：是否根据用户偏好和预算做了定制？
   - 10分：高度贴合用户需求（预算匹配、偏好融入）
   - 5分：有考虑但不够深入
   - 0分：像通用模板，无针对性

## 输出格式
请严格以 JSON 格式输出，不要有其他文字：
```json
{{
  "completeness": 8,
  "consistency": 7,
  "practicality": 9,
  "personalization": 6,
  "overall": 7.5,
  "critique": "简短的改进建议（100字以内）",
  "passed": true
}}
```

注意：overall 是四项的加权平均（completeness×0.3 + consistency×0.25 + practicality×0.25 + personalization×0.2），overall >= 6 时 passed=true。
"""

    def __init__(self, llm=None, pass_threshold: float = 6.0):
        """
        Args:
            llm: LangChain ChatLLM 实例（用于评分）
            pass_threshold: 通过阈值（overall >= 此值为通过）
        """
        self.llm = llm
        self.pass_threshold = pass_threshold

    def evaluate(
        self,
        user_input: str,
        agent_output: Any,
        context: Dict[str, Any] = None,
    ) -> JudgeScore:
        """
        对 Agent 输出进行 LLM 评分。

        Args:
            user_input: 用户原始输入
            agent_output: Agent 生成的输出（dict 或 str）
            context: 额外上下文（destination, budget, preferences 等）

        Returns:
            JudgeScore 评分结果
        """
        if self.llm is None:
            logger.warning("[LLMJudge] 未配置 LLM，返回默认分数")
            return JudgeScore(
                completeness=5, consistency=5, practicality=5,
                personalization=5, overall=5, critique="未配置评估 LLM", passed=False
            )

        context = context or {}

        # 格式化 agent_output
        if isinstance(agent_output, dict):
            output_str = json.dumps(agent_output, ensure_ascii=False, indent=2)[:3000]
        else:
            output_str = str(agent_output)[:3000]

        # 构造评估 Prompt
        prompt = self.JUDGE_PROMPT.format(
            user_input=user_input,
            agent_output=output_str,
            destination=context.get("destination", "未知"),
            budget=context.get("budget", "未指定"),
            preferences=", ".join(context.get("preferences", [])) or "无特殊偏好",
        )

        try:
            from langchain_core.messages import HumanMessage

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

            score = JudgeScore(
                completeness=float(result.get("completeness", 0)),
                consistency=float(result.get("consistency", 0)),
                practicality=float(result.get("practicality", 0)),
                personalization=float(result.get("personalization", 0)),
                overall=float(result.get("overall", 0)),
                critique=result.get("critique", ""),
                passed=result.get("passed", False),
            )

            # 重新计算 overall（确保公式一致）
            calculated_overall = (
                score.completeness * 0.3
                + score.consistency * 0.25
                + score.practicality * 0.25
                + score.personalization * 0.2
            )
            score.overall = round(calculated_overall, 1)
            score.passed = score.overall >= self.pass_threshold

            return score

        except Exception as e:
            logger.error(f"[LLMJudge] 评估失败: {e}")
            return JudgeScore(
                overall=0, critique=f"评估异常: {str(e)}", passed=False
            )

    def evaluate_batch(
        self,
        cases: list,
        results: list,
    ) -> Dict[str, Any]:
        """
        批量评估并生成汇总统计。

        Args:
            cases: 测试用例列表
            results: 对应的 Agent 输出列表

        Returns:
            汇总统计（均分、通过率等）
        """
        scores = []
        for case, result in zip(cases, results):
            score = self.evaluate(
                user_input=case.get("input", ""),
                agent_output=result,
                context=case.get("expected", {}),
            )
            scores.append(score)

        if not scores:
            return {"count": 0, "pass_rate": 0}

        return {
            "count": len(scores),
            "pass_rate": sum(1 for s in scores if s.passed) / len(scores),
            "avg_overall": sum(s.overall for s in scores) / len(scores),
            "avg_completeness": sum(s.completeness for s in scores) / len(scores),
            "avg_consistency": sum(s.consistency for s in scores) / len(scores),
            "avg_practicality": sum(s.practicality for s in scores) / len(scores),
            "avg_personalization": sum(s.personalization for s in scores) / len(scores),
            "scores": scores,
        }
