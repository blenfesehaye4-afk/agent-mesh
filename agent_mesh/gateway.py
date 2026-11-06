"""Core AgentMesh gateway orchestrating guardrails, caching, budgeting, tracing, and agent mesh."""

import time
import uuid
from typing import Optional

from .budget import BudgetLedger
from .cache import SemanticCache
from .guardrails import GuardrailEngine
from .limiter import TokenBucketLimiter
from .mesh import AgentMessageBus, AgentRegistry
from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ProxyMetrics,
    Role,
    Usage,
)
from .telemetry import SpanKind, SpanStatus, Tracer
from .tool_governor import ToolGovernor


class AgentMeshGateway:
    """Enterprise AI Gateway providing proxying, semantic caching, governance, and mesh telemetry."""

    def __init__(
        self,
        cache: Optional[SemanticCache] = None,
        limiter: Optional[TokenBucketLimiter] = None,
        tracer: Optional[Tracer] = None,
        budget: Optional[BudgetLedger] = None,
        governor: Optional[ToolGovernor] = None,
        registry: Optional[AgentRegistry] = None,
    ):
        self.cache = cache or SemanticCache(similarity_threshold=0.85)
        self.limiter = limiter or TokenBucketLimiter(capacity=100, refill_rate_per_sec=10.0)
        self.tracer = tracer or Tracer()
        self.budget = budget or BudgetLedger()
        self.governor = governor or ToolGovernor()
        self.registry = registry or AgentRegistry()
        self.bus = AgentMessageBus(self.registry)
        self.metrics = ProxyMetrics()

    async def complete(self, request: ChatCompletionRequest, tenant_id: str = "default") -> ChatCompletionResponse:
        self.metrics.requests_total += 1
        trace_id = request.trace_id or f"tr-{uuid.uuid4().hex[:12]}"

        root_span = self.tracer.start_span(
            name="gateway_completion",
            kind=SpanKind.GATEWAY,
            trace_id=trace_id,
            attributes={"tenant_id": tenant_id, "model": request.model},
        )

        try:
            # 1. Budget Allowance Check
            self.budget.check_budget(tenant_id)
            effective_model, downgraded = self.budget.resolve_effective_model(tenant_id, request.model)

            # 2. Rate Limiting Check
            if not self.limiter.allow(tenant_id, cost=1):
                raise PermissionError(f"Rate limit exceeded for tenant '{tenant_id}'.")

            # 3. Extract and inspect user prompt
            user_messages = [m for m in request.messages if m.role == Role.USER]
            last_prompt = user_messages[-1].content if user_messages else ""

            # 4. Safety Guardrails Check
            guard_span = self.tracer.start_span(
                name="guardrail_sanitization",
                kind=SpanKind.GATEWAY,
                trace_id=trace_id,
                parent_span_id=root_span.span_id,
            )
            guard_res = GuardrailEngine.sanitize(last_prompt)
            if guard_res.is_blocked:
                self.metrics.blocked_injections_total += 1
                guard_span.finish(SpanStatus.ERROR, guard_res.block_reason)
                raise ValueError(f"Request blocked by safety guardrails: {guard_res.block_reason}")

            if guard_res.violations:
                self.metrics.pii_violations_total += len(guard_res.violations)
            guard_span.finish(SpanStatus.OK)

            sanitized_prompt = guard_res.sanitized_text

            # 5. Semantic Vector Cache Check
            cache_span = self.tracer.start_span(
                name="semantic_cache_lookup",
                kind=SpanKind.CACHE,
                trace_id=trace_id,
                parent_span_id=root_span.span_id,
            )
            cached_result = self.cache.query(sanitized_prompt)
            if cached_result is not None:
                cached_text, sim_score = cached_result
                self.metrics.cache_hits += 1
                saved = len(sanitized_prompt.split()) + len(cached_text.split())
                self.metrics.tokens_saved += saved
                cache_span.finish(SpanStatus.OK)
                root_span.finish(SpanStatus.OK)

                return ChatCompletionResponse(
                    id=f"chatcmpl-cache-{uuid.uuid4().hex[:8]}",
                    model=effective_model,
                    choices=[Choice(index=0, message=ChatMessage(role=Role.ASSISTANT, content=cached_text))],
                    usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                    cached=True,
                    similarity_score=sim_score,
                    pii_redacted=bool(guard_res.violations),
                    trace_id=trace_id,
                    effective_model=effective_model,
                    cost_usd=0.0,
                    downgraded=downgraded,
                )

            cache_span.finish(SpanStatus.OK)
            self.metrics.cache_misses += 1

            # 6. Model Inference Dispatch (Simulated or Upstream Provider)
            infer_span = self.tracer.start_span(
                name="model_inference",
                kind=SpanKind.LLM,
                trace_id=trace_id,
                parent_span_id=root_span.span_id,
                attributes={"effective_model": effective_model, "downgraded": downgraded},
            )
            response_text = f"Synthesized intelligent response for: '{sanitized_prompt[:40]}...'"
            prompt_toks = max(1, len(sanitized_prompt.split()))
            comp_toks = max(1, len(response_text.split()))
            infer_span.finish(SpanStatus.OK)

            # 7. Record Spend in Budget Ledger
            usage_rec = self.budget.record_usage(
                tenant_id=tenant_id,
                model=effective_model,
                prompt_tokens=prompt_toks,
                completion_tokens=comp_toks,
            )
            self.metrics.total_spend_usd = round(self.metrics.total_spend_usd + usage_rec["cost_usd"], 6)

            # 8. Populate Semantic Cache
            self.cache.store(sanitized_prompt, response_text)
            root_span.finish(SpanStatus.OK)

            return ChatCompletionResponse(
                id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
                model=effective_model,
                choices=[Choice(index=0, message=ChatMessage(role=Role.ASSISTANT, content=response_text))],
                usage=Usage(
                    prompt_tokens=prompt_toks,
                    completion_tokens=comp_toks,
                    total_tokens=prompt_toks + comp_toks,
                ),
                cached=False,
                similarity_score=None,
                pii_redacted=bool(guard_res.violations),
                trace_id=trace_id,
                effective_model=effective_model,
                cost_usd=usage_rec["cost_usd"],
                downgraded=downgraded,
            )

        except Exception as e:
            root_span.finish(SpanStatus.ERROR, str(e))
            raise
