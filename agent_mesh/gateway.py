"""Core AgentMesh gateway orchestrating guardrails, caching, and completions."""

import time
import uuid
from typing import Optional

from .cache import SemanticCache
from .guardrails import GuardrailEngine
from .limiter import TokenBucketLimiter
from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ProxyMetrics,
    Role,
    Usage,
)


class AgentMeshGateway:
    """Enterprise AI Gateway providing proxying, semantic caching, and governance."""

    def __init__(
        self,
        cache: Optional[SemanticCache] = None,
        limiter: Optional[TokenBucketLimiter] = None,
    ):
        self.cache = cache or SemanticCache(similarity_threshold=0.85)
        self.limiter = limiter or TokenBucketLimiter(capacity=100, refill_rate_per_sec=10.0)
        self.metrics = ProxyMetrics()

    async def complete(self, request: ChatCompletionRequest, tenant_id: str = "default") -> ChatCompletionResponse:
        self.metrics.requests_total += 1

        # 1. Rate Limiting Check
        if not self.limiter.allow(tenant_id, cost=1):
            raise PermissionError(f"Rate limit exceeded for tenant '{tenant_id}'.")

        # 2. Extract and inspect user prompt
        user_messages = [m for m in request.messages if m.role == Role.USER]
        if not user_messages:
            last_prompt = ""
        else:
            last_prompt = user_messages[-1].content

        guard_res = GuardrailEngine.sanitize(last_prompt)
        if guard_res.is_blocked:
            self.metrics.blocked_injections_total += 1
            raise ValueError(f"Request blocked by safety guardrails: {guard_res.block_reason}")

        if guard_res.violations:
            self.metrics.pii_violations_total += len(guard_res.violations)

        sanitized_prompt = guard_res.sanitized_text

        # 3. Semantic Vector Cache Check
        cached_result = self.cache.query(sanitized_prompt)
        if cached_result is not None:
            cached_text, sim_score = cached_result
            self.metrics.cache_hits += 1
            saved = len(sanitized_prompt.split()) + len(cached_text.split())
            self.metrics.tokens_saved += saved

            return ChatCompletionResponse(
                id=f"chatcmpl-cache-{uuid.uuid4().hex[:8]}",
                model=request.model,
                choices=[Choice(index=0, message=ChatMessage(role=Role.ASSISTANT, content=cached_text))],
                usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                cached=True,
                similarity_score=sim_score,
                pii_redacted=bool(guard_res.violations),
            )

        # 4. Model Inference Dispatch (Simulated intelligent generation or upstream LLM)
        self.metrics.cache_misses += 1
        response_text = f"Synthesized intelligent response for: '{sanitized_prompt[:40]}...'"
        prompt_toks = max(1, len(sanitized_prompt.split()))
        comp_toks = max(1, len(response_text.split()))

        # 5. Populate Semantic Cache
        self.cache.store(sanitized_prompt, response_text)

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            model=request.model,
            choices=[Choice(index=0, message=ChatMessage(role=Role.ASSISTANT, content=response_text))],
            usage=Usage(
                prompt_tokens=prompt_toks,
                completion_tokens=comp_toks,
                total_tokens=prompt_toks + comp_toks,
            ),
            cached=False,
            similarity_score=None,
            pii_redacted=bool(guard_res.violations),
        )
