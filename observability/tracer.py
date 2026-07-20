"""
可观测性模块
============
为 Agent 系统提供结构化的追踪、指标和调用链记录。

弥补原系统只有 logging、缺少结构化 tracing 的问题。

核心能力：
  - Trace / Span : 调用链追踪（一次请求 = 一个 Trace，每个 Agent/工具 = 一个 Span）
  - Metrics      : token 用量、延迟、成功率、工具降级次数
  - 导出         : JSON 落盘 + 控制台摘要，可对接 LangSmith/OpenTelemetry

设计为轻量、零外部依赖，与 StreamingCallback 互补：
  - StreamingCallback 面向"实时展示"
  - Tracer 面向"事后分析和监控"

使用方式：
    tracer = Tracer()
    with tracer.trace("pipeline", user_input="去大理") as t:
        with tracer.span("ParseAgent", trace=t) as s:
            s.set_metric("tokens", 500)
            ...
    tracer.export("logs/traces/")
    print(tracer.summary())
"""
import json
import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Span:
    """单个操作的追踪单元（Agent 执行 / 工具调用）"""
    name: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    parent_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "running"          # running / success / error
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def set_metric(self, key: str, value: Any) -> None:
        self.metrics[key] = value

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "duration_ms": round(self.duration_ms, 1),
            "status": self.status,
            "error": self.error,
            "metrics": self.metrics,
            "attributes": self.attributes,
        }


@dataclass
class Trace:
    """一次完整请求的追踪（包含多个 Span）"""
    name: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    spans: List[Span] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "duration_ms": round(self.duration_ms, 1),
            "attributes": self.attributes,
            "spans": [s.to_dict() for s in self.spans],
        }


class Tracer:
    """
    追踪器：管理 Trace 和 Span 的生命周期，收集指标。

    线程安全性：单会话单线程使用，若需并发请为每会话创建独立 Tracer。
    """

    def __init__(self):
        self._traces: List[Trace] = []
        self._current_trace: Optional[Trace] = None

    @contextmanager
    def trace(self, name: str, **attributes):
        """开启一个 Trace 上下文"""
        t = Trace(name=name, attributes=attributes)
        self._traces.append(t)
        self._current_trace = t
        try:
            yield t
        except Exception as e:
            t.attributes["error"] = str(e)
            raise
        finally:
            t.end_time = time.time()
            logger.info(f"[Tracer] Trace '{name}' 完成 ({t.duration_ms:.0f}ms, {len(t.spans)} spans)")

    @contextmanager
    def span(self, name: str, trace: Optional[Trace] = None, parent: Optional[Span] = None):
        """开启一个 Span 上下文"""
        target_trace = trace or self._current_trace
        s = Span(name=name, parent_id=parent.span_id if parent else None)
        if target_trace is not None:
            target_trace.spans.append(s)
        try:
            yield s
            s.status = "success"
        except Exception as e:
            s.status = "error"
            s.error = str(e)
            raise
        finally:
            s.end_time = time.time()

    def record_span(
        self,
        name: str,
        duration_ms: float,
        status: str = "success",
        metrics: Dict[str, Any] = None,
        trace: Optional[Trace] = None,
    ) -> Span:
        """直接记录一个已完成的 Span（用于事后补录）"""
        target_trace = trace or self._current_trace
        s = Span(name=name, status=status, metrics=metrics or {})
        s.start_time = time.time() - duration_ms / 1000
        s.end_time = time.time()
        if target_trace is not None:
            target_trace.spans.append(s)
        return s

    def summary(self) -> Dict[str, Any]:
        """生成所有 Trace 的汇总指标"""
        if not self._traces:
            return {"traces": 0}

        total_spans = sum(len(t.spans) for t in self._traces)
        all_spans = [s for t in self._traces for s in t.spans]
        error_spans = [s for s in all_spans if s.status == "error"]

        # token 汇总
        total_tokens = sum(
            s.metrics.get("tokens", 0) for s in all_spans
        )

        # 按 Agent/工具聚合延迟
        by_name: Dict[str, List[float]] = {}
        for s in all_spans:
            by_name.setdefault(s.name, []).append(s.duration_ms)

        name_stats = {
            name: {
                "count": len(durs),
                "avg_ms": round(sum(durs) / len(durs), 1),
                "max_ms": round(max(durs), 1),
            }
            for name, durs in by_name.items()
        }

        return {
            "traces": len(self._traces),
            "total_spans": total_spans,
            "error_spans": len(error_spans),
            "success_rate": round(1 - len(error_spans) / total_spans, 3) if total_spans else 1.0,
            "total_tokens": total_tokens,
            "avg_trace_ms": round(sum(t.duration_ms for t in self._traces) / len(self._traces), 1),
            "span_stats": name_stats,
        }

    def export(self, output_dir: str) -> str:
        """导出所有 Trace 为 JSON 文件"""
        from datetime import datetime

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out / f"traces_{ts}.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "summary": self.summary(),
                    "traces": [t.to_dict() for t in self._traces],
                },
                f, ensure_ascii=False, indent=2,
            )
        logger.info(f"[Tracer] Trace 已导出: {path}")
        return str(path)

    def get_traces(self) -> List[Trace]:
        return self._traces

    def clear(self) -> None:
        self._traces.clear()
        self._current_trace = None
