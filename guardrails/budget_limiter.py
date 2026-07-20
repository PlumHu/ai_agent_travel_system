"""
调用限流器（Budget Limiter）
============================
防止 token 和 API 调用失控，保护系统和用户。

限制维度：
  1. 单次会话最大 token 用量
  2. 单用户每小时最大调用次数
  3. 单次请求最大工具调用次数

超限时返回友好提示而非报错。
"""
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from guardrails.config import GuardrailsConfig

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    """限流状态"""
    allowed: bool = True
    reason: str = ""
    tokens_used: int = 0
    tokens_remaining: int = 0
    requests_used: int = 0
    requests_remaining: int = 0
    tool_calls_used: int = 0
    tool_calls_remaining: int = 0


class BudgetLimiter:
    """
    调用限流器

    使用方式：
        limiter = BudgetLimiter()

        # 每次请求前检查
        status = limiter.check_request()
        if not status.allowed:
            return rate_limit_response(status.reason)

        # 请求完成后记录 token 用量
        limiter.record_tokens(input_tokens=500, output_tokens=1000)

        # 工具调用前检查
        if not limiter.check_tool_call().allowed:
            return tool_limit_response()
        limiter.record_tool_call()
    """

    def __init__(self, config: Optional[GuardrailsConfig] = None, user_id: str = "default"):
        self.config = config or GuardrailsConfig()
        self.user_id = user_id

        # Token 计数
        self._session_tokens: int = 0

        # 请求计数（滑动窗口，保存时间戳）
        self._request_timestamps: deque = deque()

        # 当前请求的工具调用计数
        self._current_tool_calls: int = 0

    def check_request(self) -> BudgetStatus:
        """
        检查是否允许新的请求。

        检查项：
        - 会话 token 总量是否超限
        - 每小时请求数是否超限
        """
        status = BudgetStatus(
            tokens_used=self._session_tokens,
            tokens_remaining=max(0, self.config.max_tokens_per_session - self._session_tokens),
        )

        # 1. Token 上限
        if self._session_tokens >= self.config.max_tokens_per_session:
            status.allowed = False
            status.reason = (
                f"本次会话已使用 {self._session_tokens} tokens，"
                f"达到上限 {self.config.max_tokens_per_session}。"
                f"请开始新会话继续对话。"
            )
            logger.warning(f"[BudgetLimiter] Token 超限: {self._session_tokens}")
            return status

        # 2. 每小时请求数限制
        now = time.time()
        one_hour_ago = now - 3600

        # 清理超过 1 小时的旧记录
        while self._request_timestamps and self._request_timestamps[0] < one_hour_ago:
            self._request_timestamps.popleft()

        requests_in_hour = len(self._request_timestamps)
        status.requests_used = requests_in_hour
        status.requests_remaining = max(
            0, self.config.max_requests_per_hour - requests_in_hour
        )

        if requests_in_hour >= self.config.max_requests_per_hour:
            status.allowed = False
            status.reason = (
                f"过去一小时已请求 {requests_in_hour} 次，"
                f"达到上限 {self.config.max_requests_per_hour} 次/小时。"
                f"请稍后再试。"
            )
            logger.warning(f"[BudgetLimiter] 请求频率超限: {requests_in_hour}/hour")
            return status

        # 记录本次请求时间戳
        self._request_timestamps.append(now)

        # 重置当前请求的工具调用计数
        self._current_tool_calls = 0

        return status

    def check_tool_call(self) -> BudgetStatus:
        """
        检查当前请求是否还能继续调用工具。
        """
        status = BudgetStatus(
            tool_calls_used=self._current_tool_calls,
            tool_calls_remaining=max(
                0, self.config.max_tool_calls_per_request - self._current_tool_calls
            ),
        )

        if self._current_tool_calls >= self.config.max_tool_calls_per_request:
            status.allowed = False
            status.reason = (
                f"本次请求已调用 {self._current_tool_calls} 次工具，"
                f"达到上限 {self.config.max_tool_calls_per_request}。"
            )
            logger.warning(f"[BudgetLimiter] 工具调用超限: {self._current_tool_calls}")

        return status

    def record_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """记录 token 使用量"""
        total = input_tokens + output_tokens
        self._session_tokens += total
        logger.debug(
            f"[BudgetLimiter] +{total} tokens "
            f"(total: {self._session_tokens}/{self.config.max_tokens_per_session})"
        )

    def record_tool_call(self) -> None:
        """记录一次工具调用"""
        self._current_tool_calls += 1

    def get_usage_summary(self) -> dict:
        """获取当前用量摘要"""
        now = time.time()
        one_hour_ago = now - 3600
        while self._request_timestamps and self._request_timestamps[0] < one_hour_ago:
            self._request_timestamps.popleft()

        return {
            "user_id": self.user_id,
            "session_tokens_used": self._session_tokens,
            "session_tokens_limit": self.config.max_tokens_per_session,
            "session_tokens_pct": round(
                self._session_tokens / self.config.max_tokens_per_session * 100, 1
            ),
            "requests_last_hour": len(self._request_timestamps),
            "requests_limit_per_hour": self.config.max_requests_per_hour,
            "current_tool_calls": self._current_tool_calls,
            "tool_calls_limit": self.config.max_tool_calls_per_request,
        }

    def reset_session(self) -> None:
        """重置会话计数（新会话开始时调用）"""
        self._session_tokens = 0
        self._current_tool_calls = 0
        logger.info(f"[BudgetLimiter] 会话计数已重置 (user={self.user_id})")
