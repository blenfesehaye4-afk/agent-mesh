import pytest
from agent_mesh.telemetry import SpanKind, SpanStatus, Tracer


def test_tracer_span_lifecycle():
    tracer = Tracer()

    with tracer.span(name="root_operation", kind=SpanKind.GATEWAY) as root:
        assert root.trace_id is not None
        assert root.status == SpanStatus.UNSET

        with tracer.span(name="child_llm_call", kind=SpanKind.LLM) as child:
            child.add_event("prompt_sent", {"chars": 120})
            assert child.parent_span_id == root.span_id
            assert child.trace_id == root.trace_id

    assert root.status == SpanStatus.OK
    assert root.duration_ms is not None
    assert root.duration_ms >= 0.0

    trace = tracer.get_trace(root.trace_id)
    assert len(trace) == 2


def test_tracer_error_handling():
    tracer = Tracer()
    trace_id = None

    try:
        with tracer.span(name="failing_operation", kind=SpanKind.TOOL) as span:
            trace_id = span.trace_id
            raise ValueError("Tool execution failed: division by zero")
    except ValueError:
        pass

    trace = tracer.get_trace(trace_id)
    assert len(trace) == 1
    assert trace[0].status == SpanStatus.ERROR
    assert "division by zero" in trace[0].status_message


def test_tracer_waterfall_export():
    tracer = Tracer()

    with tracer.span(name="parent", kind=SpanKind.GATEWAY) as parent:
        with tracer.span(name="child1", kind=SpanKind.AGENT):
            pass
        with tracer.span(name="child2", kind=SpanKind.TOOL):
            pass

    waterfall = tracer.export_waterfall(parent.trace_id)
    assert waterfall is not None
    assert waterfall["trace_id"] == parent.trace_id
    assert waterfall["span_count"] == 3
    assert len(waterfall["root_spans"]) == 1
    assert len(waterfall["root_spans"][0]["children"]) == 2
