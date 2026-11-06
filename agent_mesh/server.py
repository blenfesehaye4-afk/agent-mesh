"""FastAPI Application exposing OpenAI-compatible endpoints with governance & streaming."""

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse

from .gateway import AgentMeshGateway
from .models import ChatCompletionRequest, ChatCompletionResponse
from .streaming import stream_chat_completion

app = FastAPI(
    title="AgentMesh AI Gateway",
    description="High-performance AI agent gateway with semantic caching, PII guardrails, streaming & proxy.",
    version="0.2.0",
)

gateway = AgentMeshGateway()


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "agent-mesh", "version": "0.2.0"}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    tenant = request.headers.get("X-Tenant-ID", "default")
    try:
        response = await gateway.complete(req, tenant_id=tenant)

        # Handle streaming requested
        if req.stream:
            content = response.choices[0].message.content
            return StreamingResponse(
                stream_chat_completion(model=req.model, content=content),
                media_type="text/event-stream",
            )

        return response
    except PermissionError as pe:
        raise HTTPException(status_code=429, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.get("/v1/cache/stats")
async def cache_stats():
    return gateway.cache.stats()


@app.get("/v1/metrics", response_class=PlainTextResponse)
async def metrics():
    m = gateway.metrics
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
    ]
    return "\n".join(lines) + "\n"
