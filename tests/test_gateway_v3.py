import pytest
from agent_mesh.gateway import AgentMeshGateway
from agent_mesh.models import ChatCompletionRequest, ChatMessage, Role


@pytest.mark.asyncio
async def test_gateway_distributed_tracing_integration():
    gw = AgentMeshGateway()

    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role=Role.USER, content="Explain quantum entanglement concisely.")],
    )

    resp = await gw.complete(req, tenant_id="acme_corp")
    assert resp.trace_id is not None
    assert resp.cost_usd is not None

    # Verify spans recorded in tracer
    trace = gw.tracer.get_trace(resp.trace_id)
    assert len(trace) >= 3  # root gateway span, guardrail, cache lookup, model inference

    waterfall = gw.tracer.export_waterfall(resp.trace_id)
    assert waterfall is not None
    assert waterfall["trace_id"] == resp.trace_id
    assert waterfall["span_count"] >= 3


@pytest.mark.asyncio
async def test_gateway_dynamic_model_downgrading_under_budget_pressure():
    gw = AgentMeshGateway()

    # Configure tenant with low soft limit ($0.005)
    gw.budget.set_quota(
        tenant_id="budget_tenant",
        max_budget_usd=1.0,
        soft_limit_usd=0.005,
        downgrade_on_soft_limit=True,
        fallback_model="gpt-4o-mini",
    )

    # First request: spend is 0, should use requested model (gpt-4o)
    req1 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role=Role.USER, content="Request number one")],
    )
    resp1 = await gw.complete(req1, tenant_id="budget_tenant")
    assert resp1.effective_model == "gpt-4o"
    assert resp1.downgraded is False

    # Simulate accumulated spend crossing soft limit ($0.005)
    gw.budget.get_or_create_quota("budget_tenant").current_spend_usd = 0.01

    # Second request: should dynamically route to gpt-4o-mini
    req2 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role=Role.USER, content="Request number two after spend limit")],
    )
    resp2 = await gw.complete(req2, tenant_id="budget_tenant")
    assert resp2.effective_model == "gpt-4o-mini"
    assert resp2.downgraded is True
