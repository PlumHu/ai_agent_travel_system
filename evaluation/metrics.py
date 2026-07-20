"""
评估指标体系
=============
定义和计算 Agent 系统的各项质量指标。
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricResult:
    """单项指标结果"""
    name: str
    score: float           # 0.0 ~ 1.0（或 0~10 for LLM judge）
    passed: bool
    details: str = ""


@dataclass
class EvalResult:
    """单个测试用例的评估结果"""
    case_id: str
    input_text: str
    category: str
    metrics: List[MetricResult] = field(default_factory=list)
    latency_ms: float = 0.0
    overall_pass: bool = True
    raw_output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class Metrics:
    """
    评估指标计算器

    支持的维度：
    1. intent_accuracy      — 意图识别准确率
    2. entity_extraction_f1 — 实体提取 F1 分数
    3. plan_completeness    — 行程完整度
    4. budget_rationality   — 预算合理性
    5. tool_success_rate    — 工具调用成功率
    6. latency              — 响应时间
    """

    @staticmethod
    def intent_accuracy(actual_intent: str, expected_intent: str) -> MetricResult:
        """意图识别准确率"""
        is_correct = actual_intent == expected_intent
        return MetricResult(
            name="intent_accuracy",
            score=1.0 if is_correct else 0.0,
            passed=is_correct,
            details=f"actual={actual_intent}, expected={expected_intent}",
        )

    @staticmethod
    def entity_extraction_f1(
        actual: Dict[str, Any],
        expected: Dict[str, Any],
        fields: List[str] = None,
    ) -> MetricResult:
        """
        实体提取 F1 分数。

        比较 actual 和 expected 中各字段的值是否一致。
        """
        if fields is None:
            fields = ["destination", "budget", "start_date", "end_date"]

        true_positive = 0
        false_positive = 0
        false_negative = 0

        for field_name in fields:
            actual_val = actual.get(field_name)
            expected_val = expected.get(field_name)

            if expected_val is None:
                # 该字段不在预期中，跳过
                if actual_val is not None:
                    false_positive += 1
                continue

            if actual_val is None:
                false_negative += 1
            elif str(actual_val) == str(expected_val):
                true_positive += 1
            else:
                # 对于数值字段，允许一定误差
                try:
                    if abs(float(actual_val) - float(expected_val)) / max(float(expected_val), 1) < 0.1:
                        true_positive += 1
                    else:
                        false_positive += 1
                        false_negative += 1
                except (TypeError, ValueError):
                    false_positive += 1
                    false_negative += 1

        precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) > 0 else 0
        recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        return MetricResult(
            name="entity_extraction_f1",
            score=f1,
            passed=f1 >= 0.7,
            details=f"P={precision:.2f}, R={recall:.2f}, F1={f1:.2f}",
        )

    @staticmethod
    def plan_completeness(travel_plan: Dict[str, Any]) -> MetricResult:
        """
        行程完整度评分。

        检查 travel_plan 是否包含所有必要字段：
        - day_by_day（必须）
        - accommodation（必须）
        - food（可选加分）
        - budget_breakdown（必须）
        - tips（可选加分）
        """
        if not travel_plan:
            return MetricResult("plan_completeness", 0.0, False, "travel_plan 为空")

        required = ["day_by_day", "budget_breakdown"]
        important = ["accommodation", "food", "tips"]

        score = 0.0
        total_weight = 0.0

        for field_name in required:
            total_weight += 2.0
            if travel_plan.get(field_name):
                score += 2.0

        for field_name in important:
            total_weight += 1.0
            if travel_plan.get(field_name):
                score += 1.0

        # 检查 day_by_day 内容
        day_plans = travel_plan.get("day_by_day", [])
        if day_plans:
            total_weight += 2.0
            has_activities = all(
                d.get("activities") for d in day_plans if isinstance(d, dict)
            )
            if has_activities:
                score += 2.0

        final_score = score / total_weight if total_weight > 0 else 0

        return MetricResult(
            name="plan_completeness",
            score=final_score,
            passed=final_score >= 0.7,
            details=f"得分 {score}/{total_weight}，含 {len(day_plans)} 天行程",
        )

    @staticmethod
    def budget_rationality(
        budget_breakdown: Dict[str, Any],
        declared_budget: float,
    ) -> MetricResult:
        """
        预算合理性。

        检查预算分解总和与声明预算的偏差。
        """
        if not budget_breakdown or not declared_budget:
            return MetricResult(
                "budget_rationality", 0.5, True,
                "预算数据不完整，跳过检查"
            )

        try:
            total = sum(float(v) for v in budget_breakdown.values())
            deviation = abs(total - declared_budget) / declared_budget

            if deviation <= 0.1:
                score = 1.0
            elif deviation <= 0.2:
                score = 0.8
            elif deviation <= 0.3:
                score = 0.6
            else:
                score = max(0.0, 1.0 - deviation)

            return MetricResult(
                name="budget_rationality",
                score=score,
                passed=deviation <= 0.3,
                details=f"分解总和={total}, 声明={declared_budget}, 偏差={deviation:.1%}",
            )
        except (TypeError, ValueError) as e:
            return MetricResult(
                "budget_rationality", 0.0, False, f"计算失败: {e}"
            )

    @staticmethod
    def latency_check(latency_ms: float, threshold_ms: float = 30000) -> MetricResult:
        """
        响应时间检查。

        默认阈值：30 秒。
        """
        passed = latency_ms <= threshold_ms
        score = min(1.0, threshold_ms / max(latency_ms, 1))

        return MetricResult(
            name="latency",
            score=score,
            passed=passed,
            details=f"{latency_ms:.0f}ms (阈值: {threshold_ms:.0f}ms)",
        )
