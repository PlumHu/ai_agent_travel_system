"""
Agent 基类
支持每个 Agent 独立运行，内置多 provider 兜底 LLM 获取
集成 ReflectionMixin 反思能力和 StreamingCallback 流式回调
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import logging
import re

from state import AgentState
from agents.reflection import ReflectionMixin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseAgent(ABC, ReflectionMixin):
    """Agent 基类，所有 Agent 继承此类。内置反思与流式能力。"""

    def __init__(self, name: str, streaming_callback=None):
        self.name = name
        self.logger = logging.getLogger(f"Agent.{name}")
        self.streaming_callback = streaming_callback

    @staticmethod
    def infer_destination(user_input: str) -> Optional[str]:
        """从自然语言里粗提取目的地，供独立 Agent 模式兜底。"""
        if not user_input:
            return None
        patterns = [
            r"(?:去|到|前往|游玩|旅游|旅行)\s*([^\s,，。！？的玩旅吃看住]{2,12})",
            r"([^\s,，。！？]{2,12})\s*(?:怎么玩|行程|美食|攻略|几天|几日)",
        ]
        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                return match.group(1).strip("的了吗呢啊")
        return None

    # ── LLM 获取（含兜底） ────────────────────────────────────

    def _get_llm(self, streaming: bool = False):
        """
        获取主 provider LLM 实例。
        由各 Agent 的 execute() 调用，取代硬编码的 ChatOpenAI(...)。
        """
        from config import get_llm
        return get_llm(streaming=streaming)

    def _invoke_with_fallback(
        self,
        messages: list,
        streaming: bool = False,
        max_retries_per_provider: int = 2,
    ) -> str:
        """
        调用 LLM，失败时自动重试 + 降级到下一个 provider。
        支持流式回调：streaming=True 且 streaming_callback 存在时逐 token 回调。

        错误恢复策略（两层）：
          1. 同一 provider 内：瞬时错误（超时/限流/5xx）指数退避重试 max_retries_per_provider 次
          2. provider 间：重试仍失败则降级到下一个 provider

        Args:
            messages: LangChain message 列表
            streaming: 是否流式（streaming=True 时返回 generator 或触发回调）
            max_retries_per_provider: 单 provider 瞬时错误的最大重试次数

        Returns:
            LLM 响应文本（非流式）或 generator（流式且无回调）
        """
        import time as _time
        from config import get_llm_fallback, AVAILABLE_PROVIDERS
        failed = []

        for p in AVAILABLE_PROVIDERS:
            if p["name"] in failed:
                continue

            # 同一 provider 内的重试循环
            for attempt in range(max_retries_per_provider + 1):
                try:
                    from langchain_openai import ChatOpenAI
                    llm = ChatOpenAI(
                        model=p["model"],
                        temperature=0.7,
                        openai_api_key=p["api_key"],
                        openai_api_base=p["base_url"],
                        streaming=streaming,
                    )

                    # 通知流式回调 Agent 开始执行
                    if self.streaming_callback:
                        self.streaming_callback.on_agent_start(self.name)

                    if streaming:
                        if self.streaming_callback:
                            # 有回调：逐 token 发送，最后返回完整文本
                            full_text = ""
                            for chunk in llm.stream(messages):
                                token = chunk.content
                                full_text += token
                                self.streaming_callback.on_agent_token(self.name, token)
                            self.streaming_callback.on_agent_end(self.name, {"text": full_text})
                            return full_text
                        else:
                            return llm.stream(messages)
                    else:
                        response = llm.invoke(messages)
                        if self.streaming_callback:
                            self.streaming_callback.on_agent_end(
                                self.name, {"text": response.content}
                            )
                        return response.content

                except Exception as e:
                    is_transient = self._is_transient_error(e)
                    # 瞬时错误且还有重试次数 → 退避重试
                    if is_transient and attempt < max_retries_per_provider:
                        backoff = 2 ** attempt  # 1s, 2s, 4s...
                        self.logger.warning(
                            f"[{self.name}] provider={p['name']} 瞬时错误(第{attempt+1}次): {e}，"
                            f"{backoff}s 后重试"
                        )
                        _time.sleep(backoff)
                        continue
                    # 非瞬时错误 或 重试耗尽 → 降级下一个 provider
                    self.logger.warning(
                        f"[{self.name}] provider={p['name']} 调用失败: {e}，尝试下一个 provider"
                    )
                    failed.append(p["name"])
                    break

        raise RuntimeError(f"[{self.name}] 所有 LLM provider 均不可用: {failed}")

    @staticmethod
    def _is_transient_error(error: Exception) -> bool:
        """
        判断是否为可重试的瞬时错误（超时/限流/网络/5xx），
        而非永久性错误（认证失败/参数错误/4xx）。
        """
        msg = str(error).lower()
        transient_markers = [
            "timeout", "timed out", "rate limit", "429", "too many requests",
            "500", "502", "503", "504", "connection", "network",
            "temporarily", "overloaded", "unavailable", "无可用渠道",
        ]
        permanent_markers = [
            "invalid api key", "authentication", "401", "403",
            "invalid request", "not found", "404",
        ]
        # 永久错误优先判断
        if any(m in msg for m in permanent_markers):
            return False
        return any(m in msg for m in transient_markers)

    # ── 独立运行模式 ──────────────────────────────────────────

    @abstractmethod
    def execute(self, state: AgentState) -> AgentState:
        pass

    def run_standalone(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info(f"[{self.name}] 独立模式启动")
        state = self._prepare_state(input_data)
        try:
            result_state = self.execute(state)
            output = self._extract_output(result_state)
            self.logger.info(f"[{self.name}] 独立模式完成")
            return {"success": True, "data": output, "error": None}
        except Exception as e:
            self.logger.error(f"[{self.name}] 执行失败: {e}", exc_info=True)
            return {"success": False, "data": None, "error": str(e)}

    def _prepare_state(self, input_data: Dict[str, Any]) -> AgentState:
        from state import create_initial_state
        user_input = input_data.get("user_input", "")
        state = create_initial_state(user_input)
        for key, value in input_data.items():
            if key != "user_input" and key in state:
                state[key] = value
        return state

    @abstractmethod
    def _extract_output(self, state: AgentState) -> Dict[str, Any]:
        pass

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        return True

