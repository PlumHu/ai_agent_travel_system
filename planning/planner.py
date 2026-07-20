"""
动态规划模块（Plan-and-Execute）
================================
让 Agent 先把复杂目标分解成有序子任务（Plan），再逐步执行（Execute），
执行中可根据结果动态重规划（Replan）。

这是 Agent 与固定 Pipeline 的另一核心区别：
  - 固定 Pipeline：步骤写死
  - 动态规划：LLM 根据目标自主生成执行计划，可中途调整

与 ReAct 的区别：
  - ReAct：每步走一小步，走一步看一步（细粒度、灵活但可能绕路）
  - Plan-and-Execute：先出全局计划再执行（粗粒度、目标清晰、适合多步骤任务）
  两者互补：本模块生成计划，可交给 ReActAgent 或固定 Agent 执行每一步。

使用方式：
    planner = Planner(llm=my_llm)
    plan = planner.create_plan("规划从上海到大理5天游，含机票酒店和每日行程")
    # plan.steps = [Step(1, "查询上海到大理机票"), Step(2, "推荐大理酒店"), ...]

    # 执行中重规划
    plan = planner.replan(plan, completed_step=1, observation="机票已查到均价800")
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """计划中的单个子任务"""
    step_id: int
    description: str
    tool_hint: str = ""              # 建议使用的工具/Agent
    depends_on: List[int] = field(default_factory=list)  # 依赖的前置步骤
    status: str = "pending"          # pending / in_progress / completed / skipped
    result: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "tool_hint": self.tool_hint,
            "depends_on": self.depends_on,
            "status": self.status,
            "result": (self.result or "")[:300],
        }


@dataclass
class Plan:
    """完整执行计划"""
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    revision: int = 0                # 重规划次数

    def next_step(self) -> Optional[PlanStep]:
        """返回下一个可执行步骤（依赖已完成且自身 pending）"""
        completed_ids = {s.step_id for s in self.steps if s.status == "completed"}
        for s in self.steps:
            if s.status == "pending" and all(d in completed_ids for d in s.depends_on):
                return s
        return None

    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps)

    def progress(self) -> str:
        done = sum(1 for s in self.steps if s.status == "completed")
        return f"{done}/{len(self.steps)}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "revision": self.revision,
            "progress": self.progress(),
            "steps": [s.to_dict() for s in self.steps],
        }


class Planner:
    """
    动态规划器。

    用 LLM 把复杂目标分解为有序子任务，支持执行中重规划。
    LLM 不可用时降级为基于规则的简单分解。
    """

    PLAN_PROMPT = """你是一个旅行规划任务分解专家。请把用户的复杂目标分解为有序的、可执行的子任务。

用户目标：{goal}

可用能力：查询天气、搜索机票、搜索酒店、检索攻略、生成行程、推荐目的地/时间

请输出 JSON 格式的执行计划（3-6 个步骤，粒度适中）：
```json
{{
  "steps": [
    {{"step_id": 1, "description": "查询目的地天气判断适宜度", "tool_hint": "get_weather", "depends_on": []}},
    {{"step_id": 2, "description": "搜索往返机票", "tool_hint": "search_flights", "depends_on": []}},
    {{"step_id": 3, "description": "综合信息生成每日行程", "tool_hint": "plan_agent", "depends_on": [1, 2]}}
  ]
}}
```

规则：
- step_id 从 1 连续编号
- depends_on 列出必须先完成的步骤 id（无依赖则空数组）
- 只输出 JSON"""

    REPLAN_PROMPT = """你正在执行一个旅行规划计划，需要根据最新执行结果判断是否调整剩余计划。

原目标：{goal}

已完成步骤及结果：
{completed}

剩余待执行步骤：
{remaining}

最新观察：{observation}

请判断是否需要调整剩余计划。输出 JSON：
```json
{{
  "need_replan": true,
  "reason": "简述原因",
  "new_steps": [
    {{"step_id": 3, "description": "...", "tool_hint": "...", "depends_on": []}}
  ]
}}
```
若无需调整，need_replan=false 且 new_steps 为空数组。只输出 JSON。"""

    def __init__(self, llm=None, max_steps: int = 6):
        self.llm = llm
        self.max_steps = max_steps

    def create_plan(self, goal: str) -> Plan:
        """把目标分解为执行计划"""
        if self.llm is None:
            return self._rule_based_plan(goal)

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            prompt = self.PLAN_PROMPT.format(goal=goal)
            response = self.llm.invoke([
                SystemMessage(content="你是任务分解专家，输出严格的 JSON。"),
                HumanMessage(content=prompt),
            ])
            parsed = self._parse_json(response.content)
            steps = [
                PlanStep(
                    step_id=s["step_id"],
                    description=s["description"],
                    tool_hint=s.get("tool_hint", ""),
                    depends_on=s.get("depends_on", []),
                )
                for s in parsed.get("steps", [])[: self.max_steps]
            ]
            if steps:
                logger.info(f"[Planner] 生成计划，共 {len(steps)} 步")
                return Plan(goal=goal, steps=steps)
        except Exception as e:
            logger.warning(f"[Planner] LLM 规划失败，降级为规则分解: {e}")

        return self._rule_based_plan(goal)

    def replan(
        self,
        plan: Plan,
        observation: str = "",
    ) -> Plan:
        """
        根据执行结果重规划剩余步骤。
        LLM 不可用或判断无需调整时返回原 plan。
        """
        if self.llm is None:
            return plan

        completed = [s for s in plan.steps if s.status == "completed"]
        remaining = [s for s in plan.steps if s.status == "pending"]
        if not remaining:
            return plan

        try:
            from langchain_core.messages import HumanMessage

            prompt = self.REPLAN_PROMPT.format(
                goal=plan.goal,
                completed="\n".join(f"  [{s.step_id}] {s.description} → {(s.result or '')[:100]}" for s in completed) or "（无）",
                remaining="\n".join(f"  [{s.step_id}] {s.description}" for s in remaining),
                observation=observation or "（无）",
            )
            response = self.llm.invoke([HumanMessage(content=prompt)])
            parsed = self._parse_json(response.content)

            if parsed.get("need_replan") and parsed.get("new_steps"):
                logger.info(f"[Planner] 重规划: {parsed.get('reason', '')}")
                new_steps = [
                    PlanStep(
                        step_id=s["step_id"],
                        description=s["description"],
                        tool_hint=s.get("tool_hint", ""),
                        depends_on=s.get("depends_on", []),
                    )
                    for s in parsed["new_steps"][: self.max_steps]
                ]
                # 保留已完成步骤 + 新的剩余步骤
                plan.steps = completed + new_steps
                plan.revision += 1
        except Exception as e:
            logger.warning(f"[Planner] 重规划失败，保持原计划: {e}")

        return plan

    def _rule_based_plan(self, goal: str) -> Plan:
        """规则降级：基于关键词生成一个通用计划"""
        steps = []
        sid = 1

        # 有目的地关键词 → 天气 + 攻略
        steps.append(PlanStep(sid, "解析用户需求，提取目的地/时间/预算", "parse_agent"))
        sid += 1

        if any(k in goal for k in ["机票", "航班", "飞"]):
            steps.append(PlanStep(sid, "搜索机票信息", "search_flights"))
            sid += 1
        if any(k in goal for k in ["酒店", "住宿", "住"]):
            steps.append(PlanStep(sid, "搜索酒店信息", "search_hotels"))
            sid += 1

        steps.append(PlanStep(sid, "检索目的地攻略与天气", "rag_retrieve"))
        deps_id = sid
        sid += 1
        steps.append(PlanStep(sid, "综合信息生成完整行程", "plan_agent",
                              depends_on=list(range(1, deps_id + 1))))

        logger.info(f"[Planner] 规则分解生成 {len(steps)} 步")
        return Plan(goal=goal, steps=steps)

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        json_str = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
        return json.loads(json_str)
