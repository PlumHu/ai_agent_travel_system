"""
AgentState 类型定义
LangGraph 状态管理的核心数据结构
"""
from typing import TypedDict, Annotated, Sequence, Optional, Dict, Any, List
from langchain_core.messages import BaseMessage

# LangGraph reducer 签名必须是 (existing, new) -> merged，不能带额外参数
_MAX_MESSAGES = 20


def _keep_latest_messages(
    existing: Sequence[BaseMessage],
    new: Sequence[BaseMessage],
) -> Sequence[BaseMessage]:
    """
    自定义消息合并函数：追加新消息，并在超出上限时截断最旧的消息。
    替代原来的 operator.add，防止 messages 无限增长。
    """
    merged = list(existing or []) + list(new or [])
    if len(merged) > _MAX_MESSAGES:
        merged = merged[-_MAX_MESSAGES:]
    return merged


class AgentState(TypedDict):
    """
    Agent 状态类型定义
    所有 Agent 节点共享这个状态对象
    """
    # 消息历史（自定义合并函数，超出上限自动截断最旧消息）
    messages: Annotated[Sequence[BaseMessage], _keep_latest_messages]

    # 用户原始输入
    user_input: str

    # 意图识别结果
    intent: Optional[str]  # "plan_trip", "recommend_destination", "food_advice" 等

    # 提取的结构化信息
    destination: Optional[str]       # 目的地
    start_date: Optional[str]        # 出发日期
    end_date: Optional[str]          # 返回日期
    budget: Optional[float]          # 预算
    preferences: Optional[List[str]] # 用户偏好（美食、文化、自然等）
    health_info: Optional[Dict[str, Any]]  # 健康信息（过敏、疾病等）

    # 各 Agent 的输出结果
    destination_recommendation: Optional[str]       # 目的地推荐结果
    travel_plan: Optional[Dict[str, Any]]           # 旅行计划
    food_advice: Optional[Dict[str, Any]]           # 美食建议
    psych_advice: Optional[Dict[str, Any]]          # 心理节奏建议

    # RAG 检索结果
    retrieved_docs: Optional[List[Dict[str, Any]]]  # 检索到的知识库文档

    # 融合后的最终内容
    merged_content: Optional[Dict[str, Any]]

    # 最终交付物
    client_report: Optional[str]               # 客户报告（Markdown）
    social_content: Optional[Dict[str, Any]]   # 自媒体素材（JSON）

    # 元信息
    current_step: str        # 当前执行步骤
    error: Optional[str]     # 错误信息
    next_action: str         # 下一步动作（用于路由）

    # Reflection 反思机制
    reflection_attempts: Optional[int]       # 当前 Agent 反思重试次数
    _reflection_critique: Optional[str]      # 验证失败时的 critique（下次调用注入 Prompt）

    # Guardrails 安全护栏
    guardrail_warnings: Optional[List[str]]  # 安全检查警告信息

    # ReAct Agent Loop（Think-Act-Observe 循环）
    react_scratchpad: Optional[List[Dict[str, Any]]]  # 每轮 thought/action/observation 记录
    react_iterations: Optional[int]                   # 实际循环轮数
    react_answer: Optional[str]                       # ReAct 循环最终答案


# 初始状态工厂函数
def create_initial_state(user_input: str) -> AgentState:
    """创建初始状态"""
    return AgentState(
        messages=[],
        user_input=user_input,
        intent=None,
        destination=None,
        start_date=None,
        end_date=None,
        budget=None,
        preferences=None,
        health_info=None,
        destination_recommendation=None,
        travel_plan=None,
        food_advice=None,
        psych_advice=None,
        retrieved_docs=None,
        merged_content=None,
        client_report=None,
        social_content=None,
        current_step="parse",
        error=None,
        next_action="parse",
        reflection_attempts=None,
        _reflection_critique=None,
        guardrail_warnings=None,
        react_scratchpad=None,
        react_iterations=None,
        react_answer=None,
    )
