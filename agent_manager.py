"""
Agent Manager
统一管理和调度所有 Agent，集成：
  - 多轮对话上下文压缩 + 长期记忆
  - Guardrails 安全护栏（输入/输出/限流）
  - 异步并行执行
  - 流式输出回调
  - Human-in-the-Loop 确认钩子
"""
import logging
import time
from typing import Callable, Dict, Any, Type, Optional, TYPE_CHECKING

from context_manager import ContextManager
from guardrails import InputGuard, OutputGuard, BudgetLimiter, GuardrailsConfig
from streaming import StreamingCallback

if TYPE_CHECKING:
    from agents.base_agent import BaseAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from agent_catalog import (
    AGENT_DESCRIPTIONS,
    AGENT_DISPLAY_NAMES,
    USER_FACING_AGENTS,
)


class AgentManager:
    """Agent 管理器（含上下文压缩 + 长期记忆 + 安全护栏 + 流式 + HITL）"""

    def __init__(
        self,
        llm=None,
        keep_recent_turns: int = 5,
        token_soft_limit: int = 6000,
        user_id: str = "default",
        enable_long_term_memory: bool = True,
        embedding_model=None,
        enable_guardrails: bool = True,
        guardrails_config: Optional[GuardrailsConfig] = None,
        streaming_callback: Optional[StreamingCallback] = None,
        confirm_callback: Optional[Callable] = None,
        enable_tracing: bool = True,
    ):
        """
        Args:
            llm: LangChain ChatLLM 实例，用于 LLM 摘要压缩；为 None 时使用规则降级
            keep_recent_turns: 滑动窗口保留最近几轮完整对话
            token_soft_limit: 触发压缩的 token 软上限（估算值）
            user_id: 用户唯一标识，长期记忆按此隔离
            enable_long_term_memory: 是否启用长期记忆（默认 True）
            embedding_model: SentenceTransformer 实例，用于长期记忆向量检索
            enable_guardrails: 是否启用安全护栏（默认 True）
            guardrails_config: 护栏配置（为 None 时用默认）
            streaming_callback: 流式输出回调（为 None 时无流式事件）
            confirm_callback: Human-in-the-Loop 确认回调
                签名: (question: str, options: List[str]) -> str
                返回用户选择的选项文本
            enable_tracing: 是否启用可观测性追踪（默认 True）
        """
        self.agents: Dict[str, "BaseAgent"] = {}
        self._agent_factories: Dict[str, Callable[[], "BaseAgent"]] = {}
        self._agent_class_names: Dict[str, str] = {}
        self._travel_rag = None
        self._psych_rag = None
        self._ltm_enabled = enable_long_term_memory
        self._ltm_embedding_model = embedding_model
        self._ltm_llm = llm
        self.user_id = user_id
        self.streaming_callback = streaming_callback
        self.confirm_callback = confirm_callback
        self.long_term_memory = None

        # ── 可观测性 ──
        self.tracer = None
        if enable_tracing:
            try:
                from observability import Tracer
                self.tracer = Tracer()
                logger.info("[AgentManager] 可观测性追踪已启用")
            except Exception as e:
                logger.warning(f"[AgentManager] Tracer 初始化失败: {e}")

        # ── Guardrails 安全护栏 ──
        self.enable_guardrails = enable_guardrails
        if enable_guardrails:
            gc = guardrails_config or GuardrailsConfig()
            self.input_guard = InputGuard(config=gc)
            self.output_guard = OutputGuard(config=gc)
            self.budget_limiter = BudgetLimiter(config=gc, user_id=user_id)
            logger.info("[AgentManager] 安全护栏已启用")
        else:
            self.input_guard = None
            self.output_guard = None
            self.budget_limiter = None

        # ── 上下文管理（长期记忆惰性挂载，避免启动抢 SQLite 锁）──
        self.ctx = ContextManager(
            llm=llm,
            keep_recent_turns=keep_recent_turns,
            token_soft_limit=token_soft_limit,
            system_prompt="你是一位专业的旅行规划助手，帮助用户规划旅行行程。",
            long_term_memory=None,
        )
        self._register_agents()

    def _ensure_long_term_memory(self):
        """首次需要时再打开长期记忆，避免启动阶段卡在 SQLite 锁。"""
        if self.long_term_memory is not None or not self._ltm_enabled:
            return self.long_term_memory
        try:
            from memory.long_term_memory import LongTermMemory
            self.long_term_memory = LongTermMemory(
                user_id=self.user_id,
                embedding_model=self._ltm_embedding_model,
                llm=self._ltm_llm,
            )
            self.ctx.long_term_memory = self.long_term_memory
            logger.info(f"[AgentManager] 长期记忆已启用 (user_id={self.user_id})")
        except Exception as e:
            self._ltm_enabled = False
            logger.warning(f"[AgentManager] 长期记忆初始化失败，已禁用: {e}")
        return self.long_term_memory

    def _get_travel_rag(self):
        if self._travel_rag is None:
            from knowledge.rag_manager import RAGManager
            self._travel_rag = RAGManager(collection_name="travel_knowledge")
        return self._travel_rag

    def _get_psych_rag(self):
        if self._psych_rag is None:
            from knowledge.rag_manager import RAGManager
            self._psych_rag = RAGManager(collection_name="psychology_knowledge")
        return self._psych_rag

    def _register_agents(self):
        """注册 Agent 工厂（惰性 import + 惰性实例化）。"""

        def make_parse():
            from agents.parse_agent_v2 import ParseAgent
            self._ensure_long_term_memory()
            return ParseAgent(
                long_term_memory=self.long_term_memory,
                streaming_callback=self.streaming_callback,
            )

        def make_recommend():
            from agents.recommend_agent import RecommendAgent
            self._ensure_long_term_memory()
            return RecommendAgent(
                long_term_memory=self.long_term_memory,
                rag=self._get_travel_rag(),
            )

        def make_plan():
            from agents.plan_agent import PlanAgent
            return PlanAgent()

        def make_travel():
            from agents.travel_agent import TravelAgent
            return TravelAgent()

        def make_food():
            from agents.food_agent import FoodAgent
            return FoodAgent()

        def make_psychology():
            from agents.psychology_agent import PsychologyAgent
            return PsychologyAgent(rag=self._get_psych_rag())

        def make_destination():
            from agents.destination_agent import DestinationAgent
            return DestinationAgent()

        def make_merge():
            from agents.merge_agent import MergeAgent
            return MergeAgent()

        def make_output():
            from agents.output_agent import OutputAgent
            return OutputAgent()

        def make_react():
            from agents.react_agent import ReActAgent
            return ReActAgent(
                tools=self._build_react_tools(),
                budget_limiter=self.budget_limiter,
                streaming_callback=self.streaming_callback,
            )

        def make_browser():
            from agents.browser_adapter import BrowserAgentAdapter
            return BrowserAgentAdapter(headless=True)

        registrations = [
            ("parse", "ParseAgent", make_parse),
            ("recommend", "RecommendAgent", make_recommend),
            ("plan", "PlanAgent", make_plan),
            ("travel", "TravelAgent", make_travel),
            ("food", "FoodAgent", make_food),
            ("psychology", "PsychologyAgent", make_psychology),
            ("destination", "DestinationAgent", make_destination),
            ("merge", "MergeAgent", make_merge),
            ("output", "OutputAgent", make_output),
            ("react", "ReActAgent", make_react),
            ("browser", "BrowserAgentAdapter", make_browser),
        ]

        for name, class_name, factory in registrations:
            self._agent_factories[name] = factory
            self._agent_class_names[name] = class_name

        logger.info(
            f"已注册 {len(self._agent_factories)} 个 Agent 工厂（惰性加载）: "
            f"{list(self._agent_factories.keys())}"
        )

    def _get_agent(self, agent_name: str) -> Optional["BaseAgent"]:
        """按需实例化 Agent。"""
        if agent_name in self.agents:
            return self.agents[agent_name]
        factory = self._agent_factories.get(agent_name)
        if factory is None:
            return None
        try:
            agent = factory()
            self.agents[agent_name] = agent
            return agent
        except Exception as e:
            logger.warning(f"[AgentManager] 实例化 Agent '{agent_name}' 失败: {e}")
            return None

    def run_agent(
        self,
        agent_name: str,
        input_data: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """
        运行指定的 Agent

        Args:
            agent_name: Agent 名称
            input_data: 输入数据
            **kwargs: 额外参数

        Returns:
            执行结果
        """
        agent = self._get_agent(agent_name)
        if agent is None:
            available = list(self._agent_factories.keys())
            return {
                "success": False,
                "data": None,
                "error": f"Agent '{agent_name}' 不存在。可用: {available}"
            }

        logger.info(f"运行 Agent: {agent_name}")

        # 可观测性：记录 Agent 执行 span
        if self.tracer is not None:
            with self.tracer.span(f"Agent:{agent_name}") as span:
                span.set_attribute("input_keys", list(input_data.keys()))
                result = agent.run_standalone(input_data)
                span.set_metric(
                    "output_size",
                    len(str(result.get("data", ""))),
                )
                if not result.get("success"):
                    span.status = "error"
                    span.error = result.get("error", "")
                return result

        return agent.run_standalone(input_data)

    def list_agents(self, user_facing_only: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        列出可用的 Agent（不触发实例化，保持启动轻量）

        Args:
            user_facing_only: True 时只返回面向用户的 Agent（独立 Agent UI 用）
        """
        names = list(self._agent_factories.keys())
        if user_facing_only:
            names = [n for n in USER_FACING_AGENTS if n in self._agent_factories]

        return {
            name: {
                "name": name,
                "class": self._agent_class_names.get(name, name),
                "description": AGENT_DESCRIPTIONS.get(name, ""),
                "display_name": AGENT_DISPLAY_NAMES.get(name, name),
            }
            for name in names
        }

    def run_pipeline(
        self,
        user_input: str,
        auto_route: bool = True
    ) -> Dict[str, Any]:
        """
        运行完整的 Agent 流水线（集成安全护栏 + HITL + 流式回调）

        Args:
            user_input: 用户输入
            auto_route: 是否自动路由

        Returns:
            完整的执行结果（含上下文统计 + 安全警告）
        """
        self._ensure_long_term_memory()
        start_time = time.time()

        logger.info("=" * 60)
        logger.info("开始运行 Agent Pipeline")
        logger.info(f"上下文状态: {self.ctx.get_stats()}")
        logger.info("=" * 60)

        # 可观测性：开启 Trace（贯穿整个 pipeline）
        self._active_trace = None
        if self.tracer is not None:
            self._active_trace_cm = self.tracer.trace("pipeline", user_input=user_input[:100])
            self._active_trace = self._active_trace_cm.__enter__()

        # 流式通知
        if self.streaming_callback:
            self.streaming_callback.on_pipeline_start(user_input)

        # ── 1. 安全护栏：输入检查 ──
        if self.enable_guardrails:
            # 限流检查
            budget_status = self.budget_limiter.check_request()
            if not budget_status.allowed:
                return {
                    "success": False,
                    "error": budget_status.reason,
                    "guardrail_blocked": True,
                }

            # 输入安全检查
            guard_result = self.input_guard.check(user_input)
            if guard_result.blocked:
                logger.warning(f"[Guardrails] 输入被拦截: {guard_result.reason}")
                return {
                    "success": False,
                    "error": guard_result.reason,
                    "guardrail_blocked": True,
                    "detected_issues": guard_result.detected_issues,
                }

            # 使用脱敏后的输入
            if guard_result.sanitized_input != user_input:
                logger.info("[Guardrails] 输入已脱敏")
                user_input = guard_result.sanitized_input

        # ── 2. 加入上下文窗口 ──
        self.ctx.add_user_message(user_input)

        results = {
            "steps": [],
            "final_output": None,
            "success": True,
            "context_stats": self.ctx.get_stats(),
            "warnings": [],
        }

        # 安全警告传递
        if self.enable_guardrails and guard_result.warnings:
            results["warnings"].extend(guard_result.warnings)

        # ── 3. Step 1: Parse Agent ──
        parse_result = self.run_agent("parse", {"user_input": user_input})
        results["steps"].append({
            "agent": "parse",
            "result": parse_result
        })

        if not parse_result["success"]:
            results["success"] = False
            assistant_msg = f"解析失败: {parse_result.get('error', '未知错误')}"
            self.ctx.add_assistant_message(assistant_msg)
            results["context_stats"] = self.ctx.get_stats()
            self._finish_pipeline(results, start_time)
            return results

        parse_data = parse_result["data"]

        # ── 4. Human-in-the-Loop 确认（可选）──
        if self.confirm_callback and parse_data.get("intent") == "plan_trip":
            destination = parse_data.get("destination", "未知")
            budget = parse_data.get("budget", "未指定")
            confirmed = self.confirm_callback(
                f"确认规划 {destination} 的行程吗？（预算: {budget}元）",
                ["确认，开始规划", "修改需求", "取消"]
            )
            if confirmed == "取消":
                results["success"] = False
                results["final_output"] = {"message": "用户取消了规划"}
                self._finish_pipeline(results, start_time)
                return results
            elif confirmed == "修改需求":
                results["success"] = False
                results["final_output"] = {"message": "请重新描述您的需求", "need_retry": True}
                self._finish_pipeline(results, start_time)
                return results

        if not auto_route:
            results["final_output"] = parse_data
            self.ctx.add_assistant_message(str(parse_data))
            results["context_stats"] = self.ctx.get_stats()
            self._finish_pipeline(results, start_time)
            return results

        # ── 5. 根据意图路由 ──
        intent = parse_data.get("intent")
        next_action = parse_data.get("next_action")

        if intent == "recommend_time" or next_action == "recommend_time":
            recommend_result = self.run_agent("recommend", {
                "user_input": user_input,
                "destination": parse_data.get("destination"),
                "preferences": parse_data.get("preferences", []),
                "intent": "recommend_time"
            })
            results["steps"].append({
                "agent": "recommend (time)",
                "result": recommend_result
            })
            results["final_output"] = recommend_result["data"]
            self.ctx.add_assistant_message(str(recommend_result["data"]))

        elif intent == "recommend_destination" or next_action == "recommend":
            recommend_result = self.run_agent("recommend", {
                "user_input": user_input,
                "start_date": parse_data.get("start_date"),
                "budget": parse_data.get("budget"),
                "preferences": parse_data.get("preferences", []),
                "intent": "recommend_destination"
            })
            results["steps"].append({
                "agent": "recommend (destination)",
                "result": recommend_result
            })
            results["final_output"] = recommend_result["data"]
            self.ctx.add_assistant_message(str(recommend_result["data"]))

        else:
            results["final_output"] = parse_data
            results["steps"].append({
                "agent": "travel (placeholder)",
                "result": {"success": True, "data": "待实现"}
            })
            self.ctx.add_assistant_message(str(parse_data))

        # ── 6. 安全护栏：输出检查 ──
        if self.enable_guardrails and results["final_output"]:
            output_text = str(results["final_output"])
            output_result = self.output_guard.check(output_text)
            if output_result.has_warnings:
                results["warnings"].extend(output_result.warnings)
            results["confidence_level"] = output_result.confidence_level

        results["context_stats"] = self.ctx.get_stats()
        self._finish_pipeline(results, start_time)
        return results

    def _finish_pipeline(self, results: Dict[str, Any], start_time: float) -> None:
        """Pipeline 结束收尾（流式通知 + 计时）"""
        duration_ms = (time.time() - start_time) * 1000
        results["duration_ms"] = round(duration_ms, 1)

        if self.streaming_callback:
            self.streaming_callback.on_pipeline_end(
                success=results.get("success", False),
                duration_ms=duration_ms,
            )

        # 记录 token 用量（粗估）
        if self.budget_limiter:
            estimated_tokens = sum(
                len(str(step.get("result", {}).get("data", ""))) // 2
                for step in results.get("steps", [])
            )
            self.budget_limiter.record_tokens(output_tokens=estimated_tokens)

        # 可观测性：关闭 Trace 并附上摘要
        if self.tracer is not None and getattr(self, "_active_trace", None) is not None:
            try:
                self._active_trace_cm.__exit__(None, None, None)
                results["trace_id"] = self._active_trace.trace_id
                results["trace_summary"] = self.tracer.summary()
            except Exception as e:
                logger.warning(f"[AgentManager] Trace 关闭失败: {e}")
            finally:
                self._active_trace = None

    def get_trace_summary(self) -> Dict[str, Any]:
        """获取可观测性追踪摘要（token/延迟/成功率/各 Agent 统计）"""
        if self.tracer is not None:
            return self.tracer.summary()
        return {}

    def export_traces(self, output_dir: str = "logs/traces/") -> str:
        """导出全部调用链到 JSON 文件"""
        if self.tracer is not None:
            return self.tracer.export(output_dir)
        return ""

    def get_context_messages(self, query: str = ""):
        """获取当前压缩后的上下文消息列表，含长期记忆注入（可直接传给 LLM）"""
        self._ensure_long_term_memory()
        return self.ctx.get_messages(query=query)

    def reset_context(self):
        """重置对话上下文（开始新会话时调用；长期记忆不清除）"""
        self.ctx.reset()
        logger.info("[AgentManager] 短期上下文已重置（长期记忆保留）")

    def save_context(self) -> Dict[str, Any]:
        """导出短期上下文状态用于持久化"""
        return self.ctx.dump_state()

    def load_context(self, state: Dict[str, Any]) -> None:
        """从持久化状态恢复短期上下文"""
        self.ctx.load_state(state)

    def save_trip(self, destination: str, **kwargs) -> None:
        """记录完成的行程到长期记忆（wrapper 方法）"""
        if self.long_term_memory is not None:
            self.long_term_memory.save_trip(destination, **kwargs)
        else:
            logger.warning("[AgentManager] 长期记忆未启用，无法保存行程")

    def get_user_profile(self) -> Dict[str, Any]:
        """获取当前用户画像（来自长期记忆）"""
        if self.long_term_memory is not None:
            return self.long_term_memory.get_user_profile()
        return {}

    def get_trip_history(self, limit: int = 10):
        """获取历史行程（来自长期记忆）"""
        if self.long_term_memory is not None:
            return self.long_term_memory.get_trip_history(limit=limit)
        return []

    def get_memory_conflicts(self):
        """获取待确认的偏好冲突（来自长期记忆）"""
        if self.long_term_memory is not None:
            return self.long_term_memory.get_pending_conflicts()
        return []

    def decay_memories(self):
        """触发长期记忆衰减清理"""
        if self.long_term_memory is not None:
            return self.long_term_memory.decay_memories()
        return {}

    # ── Agent Loop（ReAct）─────────────────────────────────────

    def _build_react_tools(self):
        """
        构建 ReAct 工具字典。

        走统一工具注册中心（tools/registry.py），不再在此手工重复包装。
        这是"消除三套并存"后的唯一工具来源。
        """
        try:
            from tools.registry import get_default_registry
            return get_default_registry().as_dict()
        except Exception as e:
            logger.warning(f"[AgentManager] ToolRegistry 加载失败，返回空工具集: {e}")
            return {}

    def run_react(self, user_input: str) -> Dict[str, Any]:
        """
        使用 ReAct 循环 Agent 处理复杂开放式查询。

        适用于需要多次、动态调用工具的场景（多目的地对比、多约束查询）。
        受安全护栏（输入检查 + 工具调用限流）约束。

        Args:
            user_input: 用户输入

        Returns:
            {"success": bool, "answer": str, "iterations": int, "scratchpad": [...]}
        """
        start_time = time.time()
        logger.info("=" * 60)
        logger.info("开始运行 ReAct Agent Loop")
        logger.info("=" * 60)

        if self.streaming_callback:
            self.streaming_callback.on_pipeline_start(user_input)

        # 输入护栏
        if self.enable_guardrails:
            budget_status = self.budget_limiter.check_request()
            if not budget_status.allowed:
                return {"success": False, "error": budget_status.reason, "guardrail_blocked": True}

            guard_result = self.input_guard.check(user_input)
            if guard_result.blocked:
                return {
                    "success": False,
                    "error": guard_result.reason,
                    "guardrail_blocked": True,
                }
            user_input = guard_result.sanitized_input

        # 构造并运行 ReActAgent
        from agents.react_agent import ReActAgent

        tools = self._build_react_tools()
        react_agent = ReActAgent(
            tools=tools,
            budget_limiter=self.budget_limiter,
            streaming_callback=self.streaming_callback,
        )

        result = react_agent.run_standalone({"user_input": user_input})

        # 输出护栏
        if self.enable_guardrails and result.get("success") and result.get("data"):
            answer = result["data"].get("answer", "")
            if answer:
                out_result = self.output_guard.check(str(answer))
                if out_result.has_warnings:
                    result["warnings"] = out_result.warnings

        duration_ms = (time.time() - start_time) * 1000
        if self.streaming_callback:
            self.streaming_callback.on_pipeline_end(result.get("success", False), duration_ms)

        # 写入上下文和长期记忆
        answer = (result.get("data") or {}).get("answer", "")
        if answer:
            self.ctx.add_user_message(user_input)
            self.ctx.add_assistant_message(str(answer))

        result["duration_ms"] = round(duration_ms, 1)
        return result


# ============ 使用示例 ============

if __name__ == "__main__":
    import json

    manager = AgentManager()

    # 示例 1：列出所有 Agent
    print("\n" + "=" * 60)
    print("示例 1：列出所有可用的 Agent")
    print("=" * 60)
    agents = manager.list_agents()
    print(json.dumps(agents, ensure_ascii=False, indent=2))

    # 示例 2：独立运行 Parse Agent
    print("\n" + "=" * 60)
    print("示例 2：独立运行 Parse Agent")
    print("=" * 60)
    result = manager.run_agent("parse", {
        "user_input": "我想6月去大理玩，预算5000元"
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 示例 3：独立运行 Recommend Agent（反向推荐时间）
    print("\n" + "=" * 60)
    print("示例 3：独立运行 Recommend Agent - 推荐时间")
    print("=" * 60)
    result = manager.run_agent("recommend", {
        "user_input": "三亚什么时候去最合适？",
        "destination": "三亚",
        "preferences": ["人少", "天气好"],
        "intent": "recommend_time"
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 示例 4：运行完整 Pipeline
    print("\n" + "=" * 60)
    print("示例 4：运行完整 Agent Pipeline")
    print("=" * 60)
    result = manager.run_pipeline("我想春天去旅游，喜欢自然风光，预算5000元")
    print(json.dumps(result, ensure_ascii=False, indent=2))
