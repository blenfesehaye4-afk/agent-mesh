"""Distributed Tracing & Execution Telemetry for Multi-Agent Workflows.

Provides OpenTelemetry-aligned span lifecycle management, context propagation,
hierarchical trace trees, and waterfall visualization export for agent execution graphs.
"""

from __future__ import annotations

import contextvars
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SpanStatus(str, Enum):
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


class SpanKind(str, Enum):
    GATEWAY = "gateway"
    AGENT = "agent"
    TOOL = "tool"
    LLM = "llm"
    CACHE = "cache"


class TraceSpan(BaseModel):
    """An individual operation within a distributed multi-agent trace."""

    trace_id: str
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: Optional[str] = None
    name: str
    kind: SpanKind = SpanKind.GATEWAY
    agent_id: Optional[str] = None
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: SpanStatus = SpanStatus.UNSET
    status_message: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    events: List[Dict[str, Any]] = Field(default_factory=list)

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Record an in-span milestone event."""
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def finish(self, status: SpanStatus = SpanStatus.OK, status_message: Optional[str] = None) -> None:
        """Mark span as finished and compute duration."""
        if self.end_time is None:
            self.end_time = time.time()
            self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
            self.status = status
            if status_message:
                self.status_message = status_message


# Contextvars for automatic context propagation across async tasks
_active_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("_active_trace_id", default=None)
_active_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("_active_span_id", default=None)


class Tracer:
    """Manages span lifecycles, context propagation, and trace tree querying."""

    def __init__(self, max_traces: int = 5000):
        self.max_traces = max_traces
        # trace_id -> list of TraceSpan
        self._traces: Dict[str, List[TraceSpan]] = {}

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.GATEWAY,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> TraceSpan:
        """Create and register a new span, linking to active context if not explicitly given."""
        current_trace = trace_id or _active_trace_id.get() or f"tr-{uuid.uuid4().hex[:12]}"
        current_parent = parent_span_id or _active_span_id.get()

        span = TraceSpan(
            trace_id=current_trace,
            parent_span_id=current_parent,
            name=name,
            kind=kind,
            agent_id=agent_id,
            attributes=attributes or {},
        )

        if current_trace not in self._traces:
            if len(self._traces) >= self.max_traces:
                # Evict oldest trace
                oldest = next(iter(self._traces))
                del self._traces[oldest]
            self._traces[current_trace] = []

        self._traces[current_trace].append(span)
        return span

    class _SpanContextManager:
        def __init__(self, tracer: Tracer, span: TraceSpan):
            self.tracer = tracer
            self.span = span
            self.trace_token = None
            self.span_token = None

        def __enter__(self) -> TraceSpan:
            self.trace_token = _active_trace_id.set(self.span.trace_id)
            self.span_token = _active_span_id.set(self.span.span_id)
            return self.span

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is not None:
                self.span.finish(status=SpanStatus.ERROR, status_message=str(exc_val))
            else:
                if self.span.status == SpanStatus.UNSET:
                    self.span.finish(status=SpanStatus.OK)

            if self.trace_token:
                _active_trace_id.reset(self.trace_token)
            if self.span_token:
                _active_span_id.reset(self.span_token)

        async def __aenter__(self) -> TraceSpan:
            return self.__enter__()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.__exit__(exc_type, exc_val, exc_tb)

    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.GATEWAY,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> _SpanContextManager:
        """Context manager for tracing synchronous or asynchronous code blocks."""
        s = self.start_span(
            name=name,
            kind=kind,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            agent_id=agent_id,
            attributes=attributes,
        )
        return self._SpanContextManager(self, s)

    def get_trace(self, trace_id: str) -> List[TraceSpan]:
        """Fetch all spans for a trace, sorted by start time."""
        return sorted(self._traces.get(trace_id, []), key=lambda s: s.start_time)

    def export_waterfall(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Export a hierarchical waterfall representation of a trace."""
        spans = self.get_trace(trace_id)
        if not spans:
            return None

        root_start = min(s.start_time for s in spans)
        root_end = max((s.end_time or s.start_time) for s in spans)
        total_duration_ms = round((root_end - root_start) * 1000, 2)

        span_map: Dict[str, Dict[str, Any]] = {}
        roots: List[Dict[str, Any]] = []

        for s in spans:
            node = {
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "name": s.name,
                "kind": s.kind.value,
                "agent_id": s.agent_id,
                "start_offset_ms": round((s.start_time - root_start) * 1000, 2),
                "duration_ms": s.duration_ms or 0.0,
                "status": s.status.value,
                "status_message": s.status_message,
                "attributes": s.attributes,
                "events_count": len(s.events),
                "children": [],
            }
            span_map[s.span_id] = node

        for s in spans:
            node = span_map[s.span_id]
            if s.parent_span_id and s.parent_span_id in span_map:
                span_map[s.parent_span_id]["children"].append(node)
            else:
                roots.append(node)

        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "total_duration_ms": total_duration_ms,
            "root_spans": roots,
        }

    def stats(self) -> Dict[str, Any]:
        """Summary metrics across all recorded traces."""
        total_spans = sum(len(spans) for spans in self._traces.values())
        return {
            "total_traces": len(self._traces),
            "total_spans": total_spans,
        }
