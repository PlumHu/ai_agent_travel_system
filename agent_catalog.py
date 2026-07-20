"""面向 UI 的 Agent 展示元数据（轻量，避免导入重依赖）。"""

AGENT_DESCRIPTIONS = {
    "parse": "需求解析：提取目的地/日期/预算/偏好与意图",
    "recommend": "智能推荐：正向推荐目的地 / 反向推荐出行时间",
    "plan": "行程规划：按目的地生成逐日行程与预算分配",
    "travel": "旅行规划：结合知识库生成完整旅行计划",
    "food": "美食营养：当地美食推荐与饮食健康建议",
    "psychology": "心理节奏：旅行压力评估与放松建议",
    "destination": "目的地推荐：按偏好/预算推荐目的地列表",
    "merge": "内容融合：合并多 Agent 输出并检查一致性",
    "output": "旅行报告：生成可下载的 Markdown 行程报告",
    "react": "ReAct 循环：Think→Act→Observe 动态调工具",
    "browser": "浏览器自动化：真实网页操作兜底（可选）",
}

USER_FACING_AGENTS = (
    "recommend",
    "destination",
    "plan",
    "travel",
    "food",
    "psychology",
    "output",
)

AGENT_DISPLAY_NAMES = {
    "recommend": "智能推荐",
    "destination": "目的地推荐",
    "plan": "行程规划",
    "travel": "旅行规划",
    "food": "美食营养",
    "psychology": "心理节奏",
    "output": "旅行报告",
}
