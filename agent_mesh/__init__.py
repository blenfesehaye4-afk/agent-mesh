"""AgentMesh: High-performance AI agent gateway, semantic cache & proxy."""

from .cache import SemanticCache
from .gateway import AgentMeshGateway
from .guardrails import GuardrailEngine, GuardrailResult
from .limiter import TokenBucketLimiter
from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ProxyMetrics,
    Role,
)
from .router import CircuitBreaker, CircuitState, ProviderRouter
from .schema_validator import SchemaValidationError, StructuredOutputValidator
from .streaming import stream_chat_completion

__version__ = "0.2.0"
__all__ = [
    "AgentMeshGateway",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "CircuitBreaker",
    "CircuitState",
    "GuardrailEngine",
    "GuardrailResult",
    "ProviderRouter",
    "ProxyMetrics",
    "Role",
    "SchemaValidationError",
    "SemanticCache",
    "StructuredOutputValidator",
    "TokenBucketLimiter",
    "stream_chat_completion",
]
