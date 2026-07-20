"""
评估器核心
==========
编排评估数据集、指标计算和评分，生成评估报告。
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

from evaluation.dataset import EvalDataset
from evaluation.metrics import EvalResult, MetricResult, Metrics
from evaluation.judges import LLMJudge

logger = logging.getLogger(__name__)


class Evaluator:
    """
    Agent 系统评估器。

    编排完整的评估流程：
    1. 加载测试数据集
    2. 逐个运行 Agent Pipeline
    3. 计算各项指标
    4. （可选）LLM-as-Judge 综合评分
    5. 生成评估报告

    使用方式：
        evaluator = Evaluator(agent_manager=manager)
        report = evaluator.run()
        evaluator.save_report(report, "evaluation/reports/")
    """

    def __init__(
        self,
        agent_manager=None,
        dataset: Optional[EvalDataset] = None,
        llm_judge: Optional[LLMJudge] = None,
        enable_llm_judge: bool = False,
    ):
        """
        Args:
            agent_manager: AgentManager 实例
            dataset: 评估数据集（为 None 时加载默认）
            llm_judge: LLM 评分器（为 None 且 enable_llm_judge=True 时自动创建）
            enable_llm_judge: 是否启用 LLM 评分（有 API 成本）
        """
        self.agent_manager = agent_manager
        self.dataset = dataset or EvalDataset()
        self.llm_judge = llm_judge
        self.enable_llm_judge = enable_llm_judge

    def run(
        self,
        categories: List[str] = None,
        max_cases: int = None,
    ) -> Dict[str, Any]:
        """
        运行评估。

        Args:
            categories: 只评估指定分类（为 None 时评估全部）
            max_cases: 最多评估几个用例（用于快速验证）

        Returns:
            评估报告字典
        """
        # 筛选测试用例
        cases = self.dataset.get_all()
        if categories:
            cases = [c for c in cases if c.get("category") in categories]
        if max_cases:
            cases = cases[:max_cases]

        if not cases:
            logger.warning("[Evaluator] 无测试用例可执行")
            return {"error": "no test cases", "results": []}

        logger.info(f"[Evaluator] 开始评估 {len(cases)} 个测试用例")

        results: List[EvalResult] = []

        for i, case in enumerate(cases, 1):
            logger.info(f"[Evaluator] [{i}/{len(cases)}] 执行: {case['id']}")
            eval_result = self._evaluate_single(case)
            results.append(eval_result)

        # 汇总统计
        report = self._generate_report(results)
        logger.info(f"[Evaluator] 评估完成。通过率: {report['summary']['pass_rate']:.1%}")

        return report

    def _evaluate_single(self, case: Dict[str, Any]) -> EvalResult:
        """评估单个测试用例"""
        case_id = case.get("id", "unknown")
        input_text = case.get("input", "")
        expected = case.get("expected", {})
        category = case.get("category", "unknown")

        eval_result = EvalResult(
            case_id=case_id,
            input_text=input_text,
            category=category,
        )

        if not self.agent_manager:
            eval_result.error = "未配置 agent_manager"
            eval_result.overall_pass = False
            return eval_result

        # 执行 Agent Pipeline 并计时
        start_time = time.time()
        try:
            pipeline_result = self.agent_manager.run_pipeline(input_text, auto_route=True)
            eval_result.latency_ms = (time.time() - start_time) * 1000
            eval_result.raw_output = pipeline_result
        except Exception as e:
            eval_result.error = str(e)
            eval_result.latency_ms = (time.time() - start_time) * 1000
            eval_result.overall_pass = False
            return eval_result

        if not pipeline_result.get("success"):
            eval_result.error = pipeline_result.get("error", "pipeline failed")
            eval_result.overall_pass = False
            return eval_result

        # 计算各项指标
        self._compute_metrics(eval_result, pipeline_result, expected)

        # LLM-as-Judge（如果启用）
        if self.enable_llm_judge and self.llm_judge:
            try:
                judge_score = self.llm_judge.evaluate(
                    user_input=input_text,
                    agent_output=pipeline_result.get("final_output"),
                    context=expected,
                )
                eval_result.metrics.append(MetricResult(
                    name="llm_judge_overall",
                    score=judge_score.overall / 10.0,  # 归一化到 0-1
                    passed=judge_score.passed,
                    details=judge_score.critique,
                ))
            except Exception as e:
                logger.warning(f"[Evaluator] LLM Judge 评估失败: {e}")

        # 判断整体是否通过
        eval_result.overall_pass = all(m.passed for m in eval_result.metrics)

        return eval_result

    def _compute_metrics(
        self,
        eval_result: EvalResult,
        pipeline_result: Dict[str, Any],
        expected: Dict[str, Any],
    ) -> None:
        """计算规则式指标"""
        steps = pipeline_result.get("steps", [])

        # 从 steps 中提取 parse 结果
        parse_data = None
        for step in steps:
            if step.get("agent") == "parse" and step.get("result", {}).get("success"):
                parse_data = step["result"]["data"]
                break

        # 1. 意图准确率
        if expected.get("intent") and parse_data:
            metric = Metrics.intent_accuracy(
                actual_intent=parse_data.get("intent", ""),
                expected_intent=expected["intent"],
            )
            eval_result.metrics.append(metric)

        # 2. 实体提取 F1
        if parse_data and any(
            k in expected for k in ["destination", "budget", "start_date", "end_date"]
        ):
            metric = Metrics.entity_extraction_f1(
                actual=parse_data,
                expected=expected,
            )
            eval_result.metrics.append(metric)

        # 3. 行程完整度
        final_output = pipeline_result.get("final_output")
        if expected.get("has_day_plan") and isinstance(final_output, dict):
            metric = Metrics.plan_completeness(final_output)
            eval_result.metrics.append(metric)

        # 4. 预算合理性
        if (
            expected.get("budget_within_range")
            and isinstance(final_output, dict)
            and final_output.get("budget_breakdown")
            and expected.get("budget")
        ):
            metric = Metrics.budget_rationality(
                budget_breakdown=final_output["budget_breakdown"],
                declared_budget=float(expected["budget"]),
            )
            eval_result.metrics.append(metric)

        # 5. 响应时间
        metric = Metrics.latency_check(eval_result.latency_ms)
        eval_result.metrics.append(metric)

    def _generate_report(self, results: List[EvalResult]) -> Dict[str, Any]:
        """生成评估汇总报告"""
        total = len(results)
        passed = sum(1 for r in results if r.overall_pass)
        failed = total - passed

        # 按分类统计
        category_stats = {}
        for r in results:
            cat = r.category
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "passed": 0}
            category_stats[cat]["total"] += 1
            if r.overall_pass:
                category_stats[cat]["passed"] += 1

        # 按指标统计
        metric_stats = {}
        for r in results:
            for m in r.metrics:
                if m.name not in metric_stats:
                    metric_stats[m.name] = {"scores": [], "pass_count": 0, "total": 0}
                metric_stats[m.name]["scores"].append(m.score)
                metric_stats[m.name]["total"] += 1
                if m.passed:
                    metric_stats[m.name]["pass_count"] += 1

        for name, stats in metric_stats.items():
            scores = stats["scores"]
            stats["avg_score"] = sum(scores) / len(scores) if scores else 0
            stats["pass_rate"] = stats["pass_count"] / stats["total"] if stats["total"] > 0 else 0

        # 平均延迟
        latencies = [r.latency_ms for r in results if r.latency_ms > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        return {
            "summary": {
                "total_cases": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": passed / total if total > 0 else 0,
                "avg_latency_ms": round(avg_latency, 1),
            },
            "category_stats": category_stats,
            "metric_stats": metric_stats,
            "results": [
                {
                    "case_id": r.case_id,
                    "input": r.input_text[:80],
                    "category": r.category,
                    "passed": r.overall_pass,
                    "latency_ms": round(r.latency_ms, 1),
                    "metrics": [
                        {"name": m.name, "score": round(m.score, 3), "passed": m.passed}
                        for m in r.metrics
                    ],
                    "error": r.error,
                }
                for r in results
            ],
        }

    def save_report(self, report: Dict[str, Any], output_path: str) -> str:
        """保存评估报告为 JSON + Markdown"""
        from pathlib import Path
        from datetime import datetime

        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON 报告
        json_path = out_dir / f"eval_report_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Markdown 报告
        md_path = out_dir / f"eval_report_{timestamp}.md"
        md_content = self._report_to_markdown(report)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"[Evaluator] 报告已保存: {json_path}")
        return str(md_path)

    def _report_to_markdown(self, report: Dict[str, Any]) -> str:
        """将报告转为 Markdown 格式"""
        summary = report["summary"]

        lines = [
            "# Agent 系统评估报告",
            "",
            f"**评估时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 总体结果",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 总用例数 | {summary['total_cases']} |",
            f"| 通过数 | {summary['passed']} |",
            f"| 失败数 | {summary['failed']} |",
            f"| **通过率** | **{summary['pass_rate']:.1%}** |",
            f"| 平均延迟 | {summary['avg_latency_ms']:.0f}ms |",
            "",
            "## 分类统计",
            "",
            "| 分类 | 通过/总数 | 通过率 |",
            "|------|-----------|--------|",
        ]

        for cat, stats in report.get("category_stats", {}).items():
            rate = stats["passed"] / stats["total"] if stats["total"] > 0 else 0
            lines.append(f"| {cat} | {stats['passed']}/{stats['total']} | {rate:.0%} |")

        lines.extend([
            "",
            "## 指标详情",
            "",
            "| 指标 | 平均分 | 通过率 |",
            "|------|--------|--------|",
        ])

        for name, stats in report.get("metric_stats", {}).items():
            lines.append(
                f"| {name} | {stats['avg_score']:.3f} | {stats['pass_rate']:.0%} |"
            )

        # 失败用例
        failed_cases = [r for r in report.get("results", []) if not r["passed"]]
        if failed_cases:
            lines.extend([
                "",
                "## 失败用例",
                "",
            ])
            for case in failed_cases[:10]:
                lines.append(f"- **{case['case_id']}**: {case['input']}")
                if case.get("error"):
                    lines.append(f"  - 错误: {case['error']}")
                for m in case.get("metrics", []):
                    if not m["passed"]:
                        lines.append(f"  - ❌ {m['name']}: {m['score']:.3f}")

        lines.append("\n---\n*报告由 Evaluation 框架自动生成*\n")

        return "\n".join(lines)
