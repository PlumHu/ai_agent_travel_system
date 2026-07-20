"""
评估框架入口脚本
================
运行完整的 Agent 系统评估并生成报告。

用法：
    python evaluation/run_eval.py
    python evaluation/run_eval.py --cases evaluation/test_cases/travel_cases.json
    python evaluation/run_eval.py --category basic_planning --max 5
    python evaluation/run_eval.py --llm-judge  # 启用 LLM 评分（有成本）
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from evaluation.dataset import EvalDataset
from evaluation.evaluator import Evaluator
from evaluation.judges import LLMJudge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Agent 系统评估工具")
    parser.add_argument(
        "--cases", type=str, default=None,
        help="测试用例文件路径（默认: evaluation/test_cases/travel_cases.json）"
    )
    parser.add_argument(
        "--output", type=str, default="evaluation/reports/",
        help="报告输出目录"
    )
    parser.add_argument(
        "--category", type=str, default=None,
        help="只评估指定分类（如 basic_planning）"
    )
    parser.add_argument(
        "--max", type=int, default=None,
        help="最多评估几个用例（快速验证用）"
    )
    parser.add_argument(
        "--llm-judge", action="store_true",
        help="启用 LLM-as-Judge 评分（有 API 成本）"
    )
    parser.add_argument(
        "--list-categories", action="store_true",
        help="列出所有可用分类"
    )

    args = parser.parse_args()

    # 加载数据集
    dataset = EvalDataset(args.cases)
    logger.info(f"加载了 {len(dataset)} 个测试用例")

    if args.list_categories:
        categories = dataset.get_categories()
        print("\n可用分类:")
        for cat in sorted(categories):
            count = len(dataset.get_by_category(cat))
            print(f"  - {cat} ({count} 用例)")
        return

    # 初始化 AgentManager
    try:
        from agent_manager import AgentManager
        manager = AgentManager(enable_long_term_memory=False)
        logger.info("AgentManager 初始化成功")
    except Exception as e:
        logger.error(f"AgentManager 初始化失败: {e}")
        logger.info("将以 dry-run 模式运行（只验证数据集格式）")
        manager = None

    # LLM Judge（可选）
    llm_judge = None
    if args.llm_judge:
        try:
            from config import get_llm
            llm = get_llm()
            llm_judge = LLMJudge(llm=llm)
            logger.info("LLM Judge 已启用")
        except Exception as e:
            logger.warning(f"LLM Judge 初始化失败，跳过: {e}")

    # 运行评估
    evaluator = Evaluator(
        agent_manager=manager,
        dataset=dataset,
        llm_judge=llm_judge,
        enable_llm_judge=args.llm_judge,
    )

    categories = [args.category] if args.category else None
    report = evaluator.run(categories=categories, max_cases=args.max)

    # 输出结果
    if "error" in report:
        print(f"\n❌ 评估失败: {report['error']}")
        return

    summary = report["summary"]
    print("\n" + "=" * 60)
    print("📊 评估结果摘要")
    print("=" * 60)
    print(f"  总用例数: {summary['total_cases']}")
    print(f"  通过: {summary['passed']} ✅")
    print(f"  失败: {summary['failed']} ❌")
    print(f"  通过率: {summary['pass_rate']:.1%}")
    print(f"  平均延迟: {summary['avg_latency_ms']:.0f}ms")

    # 指标详情
    print("\n📈 指标详情:")
    for name, stats in report.get("metric_stats", {}).items():
        status = "✅" if stats["pass_rate"] >= 0.8 else "⚠️" if stats["pass_rate"] >= 0.5 else "❌"
        print(f"  {status} {name}: avg={stats['avg_score']:.3f}, pass={stats['pass_rate']:.0%}")

    # 保存报告
    report_path = evaluator.save_report(report, args.output)
    print(f"\n📄 报告已保存: {report_path}")


if __name__ == "__main__":
    main()
