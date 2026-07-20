"""
主入口 + LangGraph 图编排
使用 LangGraph 编排多 Agent 工作流，支持 Reflection 回环。
"""
import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from state import AgentState, create_initial_state
from agents.parse_agent import parse_agent
from agents.travel_agent import travel_agent
from agents.output_agent import output_agent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 最大反思重试次数（防止无限循环）
MAX_REFLECTION_RETRIES = 2


def route_after_parse(state: AgentState) -> Literal["travel_agent", "parse_agent", "end"]:
    """
    解析后的路由逻辑（含 Reflection 回环）

    根据意图决定下一步：
    - plan_trip -> travel_agent（开始规划）
    - recommend_destination -> travel_agent（推荐后规划）
    - error -> end（结束）
    - _reflection_critique 存在 且 重试次数未超限 -> parse_agent（反思重试）
    """
    if state.get("error"):
        return "end"

    # Reflection 回环：验证失败时重新解析
    critique = state.get("_reflection_critique")
    attempts = state.get("reflection_attempts", 0) or 0
    if critique and attempts < MAX_REFLECTION_RETRIES:
        logger.info(f"[Router] Reflection 触发重试 (attempt={attempts})")
        return "parse_agent"

    next_action = state.get("next_action", "end")

    if next_action in ["plan", "recommend"]:
        return "travel_agent"

    return "end"


def route_after_travel(state: AgentState) -> Literal["output_agent", "travel_agent", "end"]:
    """
    旅行规划后的路由逻辑（含 Reflection 回环）
    """
    if state.get("error"):
        return "end"

    # Travel plan 的 Reflection 回环
    critique = state.get("_reflection_critique")
    attempts = state.get("reflection_attempts", 0) or 0
    if critique and attempts < MAX_REFLECTION_RETRIES:
        logger.info(f"[Router] Travel Reflection 触发重试 (attempt={attempts})")
        return "travel_agent"

    return "output_agent"


def build_graph() -> StateGraph:
    """
    构建 LangGraph 工作流（含 Reflection 回环边）

    工作流程：
    1. parse_agent: 解析用户需求 ←─┐
    2. travel_agent: 规划旅行 ←──┐  │ (reflection retry)
    3. output_agent: 生成报告      │  │
                                    │  │
    reflection loop ────────────────┘  │
    reflection loop ───────────────────┘
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("parse_agent", parse_agent)
    workflow.add_node("travel_agent", travel_agent)
    workflow.add_node("output_agent", output_agent)

    # 设置入口点
    workflow.set_entry_point("parse_agent")

    # 条件边（含 Reflection 回环）
    workflow.add_conditional_edges(
        "parse_agent",
        route_after_parse,
        {
            "travel_agent": "travel_agent",
            "parse_agent": "parse_agent",  # Reflection 重试
            "end": END
        }
    )

    workflow.add_conditional_edges(
        "travel_agent",
        route_after_travel,
        {
            "output_agent": "output_agent",
            "travel_agent": "travel_agent",  # Reflection 重试
            "end": END
        }
    )

    # output_agent 执行完毕后结束
    workflow.add_edge("output_agent", END)

    # 编译图
    app = workflow.compile()

    return app


def run_agent(user_input: str) -> dict:
    """
    运行 Agent 系统

    Args:
        user_input: 用户输入

    Returns:
        最终状态字典
    """
    logger.info("=" * 80)
    logger.info("AI Travel Agent 启动")
    logger.info("=" * 80)

    # 创建初始状态
    initial_state = create_initial_state(user_input)

    # 构建图
    app = build_graph()

    # 执行图
    try:
        final_state = app.invoke(initial_state)

        logger.info("=" * 80)
        logger.info("Agent 执行完成")
        logger.info("=" * 80)

        return final_state

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        return {"error": str(e)}


def main():
    """
    主函数：命令行交互模式
    """
    print("\n" + "=" * 60)
    print("🧳 欢迎使用 AI Travel Agent (旅行规划助手)")
    print("=" * 60 + "\n")

    while True:
        print("\n请输入您的旅行需求（输入 'quit' 退出）:")
        user_input = input("> ").strip()

        if user_input.lower() in ["quit", "exit", "q"]:
            print("\n感谢使用，祝您旅途愉快！👋\n")
            break

        if not user_input:
            print("❌ 输入不能为空，请重新输入")
            continue

        # 执行 Agent
        result = run_agent(user_input)

        # 显示结果
        if result.get("error"):
            print(f"\n❌ 执行出错: {result['error']}")
        else:
            print("\n✅ 旅行计划已生成！")

            # 显示报告摘要
            travel_plan = result.get("travel_plan")
            if travel_plan:
                print(f"\n📅 行程天数: {len(travel_plan.get('day_by_day', []))} 天")
                print(f"💰 预算总计: {sum(travel_plan.get('budget_breakdown', {}).values())} 元")
                print(f"🍜 美食推荐: {len(travel_plan.get('food', []))} 项")

            # 提示报告位置
            if result.get("client_report"):
                print(f"\n📄 详细报告已保存到: output/reports/")


if __name__ == "__main__":
    # 测试用例
    test_input = "我想6月中旬去大理玩5天，预算5000元，喜欢吃美食和看风景"

    print("\n🔧 测试模式")
    print(f"输入: {test_input}\n")

    result = run_agent(test_input)

    if result.get("client_report"):
        print("\n" + "=" * 60)
        print("📄 生成的报告:")
        print("=" * 60)
        print(result["client_report"])
