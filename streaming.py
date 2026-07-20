"""
流式输出管理器
==============
提供全链路的流式事件回调机制，让用户实时看到 Agent 执行进度。

事件类型：
  - agent_start    : Agent 开始执行
  - agent_token    : LLM 生成单个 token
  - agent_end      : Agent 执行完成
  - tool_start     : 工具调用开始
  - tool_end       : 工具调用结束
  - pipeline_start : 整个 Pipeline 开始
  - pipeline_end   : 整个 Pipeline 结束
  - error          : 错误事件

使用方式：
    callback = StreamingCallback()
    callback.add_listener(my_handler)  # 注册监听器

    # 传入 Agent
    agent = ParseAgent(streaming_callback=callback)

    # 或在 Web UI 中
    callback.add_listener(lambda e: st_placeholder.write(e))
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """流式事件"""
    type: str                        # 事件类型
    agent: str = ""                  # Agent 名称
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __repr__(self):
        return f"StreamEvent({self.type}, agent={self.agent})"


class StreamingCallback:
    """
    流式回调管理器。

    观察者模式：注册多个监听器，每次事件触发时通知所有监听器。
    支持同步和异步监听器。
    """

    def __init__(self):
        self._listeners: List[Callable[[StreamEvent], None]] = []
        self._token_buffer: Dict[str, str] = {}  # agent_name -> accumulated text

    def add_listener(self, listener: Callable[[StreamEvent], None]) -> None:
        """注册事件监听器"""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable) -> None:
        """移除监听器"""
        self._listeners = [l for l in self._listeners if l is not listener]

    def clear_listeners(self) -> None:
        """清空所有监听器"""
        self._listeners.clear()

    # ── 事件发射方法 ─────────────────────────────────────────

    def on_pipeline_start(self, user_input: str) -> None:
        """Pipeline 开始"""
        self._emit(StreamEvent(
            type="pipeline_start",
            data={"user_input": user_input[:200]},
        ))

    def on_pipeline_end(self, success: bool, duration_ms: float = 0) -> None:
        """Pipeline 结束"""
        self._emit(StreamEvent(
            type="pipeline_end",
            data={"success": success, "duration_ms": duration_ms},
        ))

    def on_agent_start(self, agent_name: str) -> None:
        """Agent 开始执行"""
        self._token_buffer[agent_name] = ""
        self._emit(StreamEvent(
            type="agent_start",
            agent=agent_name,
        ))

    def on_agent_token(self, agent_name: str, token: str) -> None:
        """Agent LLM 输出单个 token"""
        self._token_buffer[agent_name] = self._token_buffer.get(agent_name, "") + token
        self._emit(StreamEvent(
            type="agent_token",
            agent=agent_name,
            data={"token": token, "accumulated": self._token_buffer[agent_name]},
        ))

    def on_agent_end(self, agent_name: str, result: Dict[str, Any] = None) -> None:
        """Agent 执行完成"""
        self._emit(StreamEvent(
            type="agent_end",
            agent=agent_name,
            data={"result": result or {}, "total_text": self._token_buffer.get(agent_name, "")},
        ))
        # 清理 buffer
        self._token_buffer.pop(agent_name, None)

    def on_tool_start(self, tool_name: str, agent_name: str = "") -> None:
        """工具调用开始"""
        self._emit(StreamEvent(
            type="tool_start",
            agent=agent_name,
            data={"tool": tool_name},
        ))

    def on_tool_end(self, tool_name: str, success: bool, agent_name: str = "") -> None:
        """工具调用结束"""
        self._emit(StreamEvent(
            type="tool_end",
            agent=agent_name,
            data={"tool": tool_name, "success": success},
        ))

    def on_reflection(self, agent_name: str, attempt: int, critique: str) -> None:
        """反思重试事件"""
        self._emit(StreamEvent(
            type="reflection",
            agent=agent_name,
            data={"attempt": attempt, "critique": critique[:200]},
        ))

    def on_error(self, error: str, agent_name: str = "") -> None:
        """错误事件"""
        self._emit(StreamEvent(
            type="error",
            agent=agent_name,
            data={"error": error},
        ))

    # ── 内部方法 ─────────────────────────────────────────────

    def _emit(self, event: StreamEvent) -> None:
        """触发事件通知所有监听器"""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.warning(f"[StreamingCallback] 监听器异常: {e}")

    def get_accumulated_text(self, agent_name: str) -> str:
        """获取指定 Agent 的累计文本"""
        return self._token_buffer.get(agent_name, "")


# ── 内置监听器 ─────────────────────────────────────────────────

class ConsoleStreamListener:
    """控制台流式输出监听器（调试用）"""

    def __call__(self, event: StreamEvent) -> None:
        if event.type == "pipeline_start":
            print(f"\n{'='*60}")
            print(f"🚀 Pipeline 开始: {event.data.get('user_input', '')[:50]}...")
            print(f"{'='*60}")

        elif event.type == "agent_start":
            print(f"\n▶️  {event.agent} 开始执行...")

        elif event.type == "agent_token":
            print(event.data.get("token", ""), end="", flush=True)

        elif event.type == "agent_end":
            print(f"\n✅ {event.agent} 完成")

        elif event.type == "tool_start":
            print(f"  🔧 调用工具: {event.data.get('tool', '')}")

        elif event.type == "tool_end":
            status = "✅" if event.data.get("success") else "❌"
            print(f"  {status} 工具完成: {event.data.get('tool', '')}")

        elif event.type == "reflection":
            print(f"  🔄 反思重试 #{event.data.get('attempt', 0)}: {event.data.get('critique', '')[:80]}")

        elif event.type == "pipeline_end":
            status = "✅ 成功" if event.data.get("success") else "❌ 失败"
            duration = event.data.get("duration_ms", 0)
            print(f"\n{'='*60}")
            print(f"🏁 Pipeline 结束: {status} ({duration:.0f}ms)")
            print(f"{'='*60}\n")

        elif event.type == "error":
            print(f"\n⚠️  错误 [{event.agent}]: {event.data.get('error', '')}")


class CollectorListener:
    """事件收集监听器（用于后续分析或测试断言）"""

    def __init__(self):
        self.events: List[StreamEvent] = []

    def __call__(self, event: StreamEvent) -> None:
        self.events.append(event)

    def get_events_by_type(self, event_type: str) -> List[StreamEvent]:
        return [e for e in self.events if e.type == event_type]

    def get_events_by_agent(self, agent_name: str) -> List[StreamEvent]:
        return [e for e in self.events if e.agent == agent_name]

    def clear(self):
        self.events.clear()
