"""FastAPI Application exposing OpenAI-compatible endpoints, Service Mesh (A2A), HITL approvals, and Tracing."""

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from .budget import BudgetExceededError, TenantQuota
from .gateway import AgentMeshGateway
from .mesh import AgentNode, AgentStatus, MessageEnvelope
from .models import ChatCompletionRequest, ChatCompletionResponse
from .streaming import stream_chat_completion
from .tool_governor import ApprovalStatus, ApprovalTicket

app = FastAPI(
    title="AgentMesh AI Gateway & Service Mesh",
    description="Enterprise AI Gateway, A2A Agent Service Mesh, HITL Tool Sandbox, Semantic Caching & Tracing.",
    version="0.3.0",
)

gateway = AgentMeshGateway()


# ---------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "agent-mesh", "version": "0.3.0"}


@app.get("/v1/metrics", response_class=PlainTextResponse)
async def metrics():
    m = gateway.metrics
    active_agents = len(gateway.registry.list_agents(alive_only=True))
    trace_stats = gateway.tracer.stats()
    lines = [
        "# HELP agentmesh_requests_total Total number of proxy requests handled",
        "# TYPE agentmesh_requests_total counter",
        f"agentmesh_requests_total {m.requests_total}",
        "# HELP agentmesh_cache_hits_total Number of requests served from semantic cache",
        "# TYPE agentmesh_cache_hits_total counter",
        f"agentmesh_cache_hits_total {m.cache_hits}",
        "# HELP agentmesh_cache_misses_total Number of cache misses dispatched to model",
        "# TYPE agentmesh_cache_misses_total counter",
        f"agentmesh_cache_misses_total {m.cache_misses}",
        "# HELP agentmesh_tokens_saved_total Estimated tokens saved via semantic caching",
        "# TYPE agentmesh_tokens_saved_total counter",
        f"agentmesh_tokens_saved_total {m.tokens_saved}",
        "# HELP agentmesh_pii_violations_total Total count of PII fields masked",
        "# TYPE agentmesh_pii_violations_total counter",
        f"agentmesh_pii_violations_total {m.pii_violations_total}",
        "# HELP agentmesh_spend_usd_total Estimated dollar spend across all tenants",
        "# TYPE agentmesh_spend_usd_total gauge",
        f"agentmesh_spend_usd_total {m.total_spend_usd}",
        "# HELP agentmesh_active_agents_total Number of online alive agents in mesh",
        "# TYPE agentmesh_active_agents_total gauge",
        f"agentmesh_active_agents_total {active_agents}",
        "# HELP agentmesh_traces_total Total number of distributed traces collected",
        "# TYPE agentmesh_traces_total counter",
        f"agentmesh_traces_total {trace_stats['total_traces']}",
    ]
    return "\n".join(lines) + "\n"


@app.get("/v1/cache/stats")
async def cache_stats():
    return gateway.cache.stats()


# ---------------------------------------------------------
# Chat Completions Proxy
# ---------------------------------------------------------

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    tenant = request.headers.get("X-Tenant-ID", "default")
    try:
        response = await gateway.complete(req, tenant_id=tenant)

        # Handle streaming requested
        if req.stream:
            content = response.choices[0].message.content
            return StreamingResponse(
                stream_chat_completion(model=response.model, content=content),
                media_type="text/event-stream",
            )

        return response
    except BudgetExceededError as be:
        raise HTTPException(status_code=402, detail=str(be))
    except PermissionError as pe:
        raise HTTPException(status_code=429, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


# ---------------------------------------------------------
# Agent-to-Agent (A2A) Mesh Endpoints
# ---------------------------------------------------------

@app.post("/v1/mesh/agents", response_model=AgentNode)
async def register_agent(node: AgentNode):
    """Register or update an autonomous agent in the service mesh."""
    return gateway.registry.register(node)


@app.get("/v1/mesh/agents", response_model=List[AgentNode])
async def list_agents(
    alive_only: bool = True,
    capability: Optional[str] = None,
    tool: Optional[str] = None,
):
    """Discover agents matching specific capabilities or tools."""
    return gateway.registry.list_agents(alive_only=alive_only, capability=capability, tool=tool)


@app.delete("/v1/mesh/agents/{agent_id}")
async def deregister_agent(agent_id: str):
    """Remove an agent from the active registry."""
    success = gateway.registry.deregister(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {"status": "deregistered", "agent_id": agent_id}


class HeartbeatPayload(BaseModel):
    current_load: Optional[float] = None
    status: Optional[AgentStatus] = None


@app.post("/v1/mesh/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str, payload: HeartbeatPayload):
    """Refresh agent heartbeat and status."""
    ok = gateway.registry.heartbeat(agent_id, current_load=payload.current_load, status=payload.status)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {"status": "acknowledged", "agent_id": agent_id}


class DirectMessageRequest(BaseModel):
    sender_id: str
    target_id: str
    payload: Dict[str, Any]
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None


@app.post("/v1/mesh/messages/direct")
async def send_direct_message(req: DirectMessageRequest):
    """Send a point-to-point message to another agent's mailbox."""
    try:
        envelope = await gateway.bus.send_direct(
            sender_id=req.sender_id,
            target_id=req.target_id,
            payload=req.payload,
            correlation_id=req.correlation_id,
            trace_id=req.trace_id,
        )
        return envelope
    except LookupError as le:
        raise HTTPException(status_code=404, detail=str(le))
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))


class TopicPublishRequest(BaseModel):
    sender_id: str
    topic: str
    payload: Dict[str, Any]
    trace_id: Optional[str] = None


@app.post("/v1/mesh/messages/publish")
async def publish_topic_message(req: TopicPublishRequest):
    """Broadcast an asynchronous message to all subscribers of a topic."""
    count = await gateway.bus.publish(
        sender_id=req.sender_id,
        topic=req.topic,
        payload=req.payload,
        trace_id=req.trace_id,
    )
    return {"status": "published", "subscribers_notified": count, "topic": req.topic}


@app.get("/v1/mesh/agents/{agent_id}/mailbox")
async def read_mailbox(agent_id: str, timeout: Optional[float] = Query(default=1.0, ge=0.0, le=10.0)):
    """Fetch next incoming message for agent with short timeout."""
    msg = await gateway.bus.receive(agent_id, timeout=timeout)
    if not msg:
        raise HTTPException(status_code=204, detail="No messages available")
    return msg


# ---------------------------------------------------------
# Governance: Budget & Quotas
# ---------------------------------------------------------

@app.get("/v1/governance/budget")
async def get_budget(tenant_id: Optional[str] = None):
    return gateway.budget.get_summary(tenant_id=tenant_id)


class SetQuotaPayload(BaseModel):
    tenant_id: str
    max_budget_usd: float
    soft_limit_usd: Optional[float] = None
    max_tokens: Optional[int] = None
    downgrade_on_soft_limit: Optional[bool] = None
    fallback_model: Optional[str] = None


@app.post("/v1/governance/budget")
async def set_budget_quota(payload: SetQuotaPayload):
    quota = gateway.budget.set_quota(
        tenant_id=payload.tenant_id,
        max_budget_usd=payload.max_budget_usd,
        soft_limit_usd=payload.soft_limit_usd,
        max_tokens=payload.max_tokens,
        downgrade_on_soft_limit=payload.downgrade_on_soft_limit,
        fallback_model=payload.fallback_model,
    )
    return quota


# ---------------------------------------------------------
# Governance: Human-in-the-Loop (HITL) Approvals
# ---------------------------------------------------------

@app.get("/v1/governance/approvals", response_model=List[ApprovalTicket])
async def list_approvals(status: Optional[ApprovalStatus] = None):
    return gateway.governor.list_tickets(status=status)


class ResolveApprovalPayload(BaseModel):
    approver: str = "admin"
    reason: Optional[str] = None


@app.post("/v1/governance/approvals/{ticket_id}/approve")
async def approve_ticket(ticket_id: str, payload: ResolveApprovalPayload):
    ok = gateway.governor.approve(ticket_id, approver=payload.approver)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Pending ticket '{ticket_id}' not found or already resolved")
    return {"status": "approved", "ticket_id": ticket_id, "approver": payload.approver}


@app.post("/v1/governance/approvals/{ticket_id}/reject")
async def reject_ticket(ticket_id: str, payload: ResolveApprovalPayload):
    reason = payload.reason or "Rejected by human administrator"
    ok = gateway.governor.reject(ticket_id, reason=reason, approver=payload.approver)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Pending ticket '{ticket_id}' not found or already resolved")
    return {"status": "rejected", "ticket_id": ticket_id, "approver": payload.approver, "reason": reason}


class EvaluateToolPayload(BaseModel):
    agent_id: str
    tool_name: str
    arguments: Dict[str, Any] = {}


@app.post("/v1/governance/tools/evaluate")
async def evaluate_tool(payload: EvaluateToolPayload):
    level, reason = gateway.governor.evaluate(payload.agent_id, payload.tool_name, payload.arguments)
    return {
        "permission_level": level.value,
        "reason": reason,
        "requires_hitl": (level.value == "high_risk"),
    }


# ---------------------------------------------------------
# Distributed Tracing
# ---------------------------------------------------------

@app.get("/v1/traces/{trace_id}")
async def get_trace(trace_id: str):
    waterfall = gateway.tracer.export_waterfall(trace_id)
    if not waterfall:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")
    return waterfall


@app.get("/v1/traces")
async def trace_stats():
    return gateway.tracer.stats()
