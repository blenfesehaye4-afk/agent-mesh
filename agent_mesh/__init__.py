"""AgentMesh: High-performance AI agent gateway, service mesh, governance & proxy."""

from .budget import BudgetExceededError, BudgetLedger, TenantQuota
from .cache import SemanticCache
from .gateway import AgentMeshGateway
from .guardrails import GuardrailEngine, GuardrailResult
from .limiter import TokenBucketLimiter
from .mesh import (
    AgentMessageBus,
    AgentNode,
    AgentRegistry,
    AgentStatus,
    MessageEnvelope,
    RoutingStrategy,
)
from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ProxyMetrics,
    Role,
    Usage,
)
from .router import CircuitBreaker, CircuitState, ProviderRouter
from .schema_validator import SchemaValidationError, StructuredOutputValidator
from .streaming import stream_chat_completion
from .telemetry import SpanKind, SpanStatus, Tracer, TraceSpan
from .tool_governor import ApprovalStatus, ApprovalTicket, PermissionLevel, ToolGovernor

__version__ = "0.3.0"
__all__ = [
    "AgentMeshGateway",
    "AgentMessageBus",
    "AgentNode",
    "AgentRegistry",
    "AgentStatus",
    "ApprovalStatus",
    "ApprovalTicket",
    "BudgetExceededError",
    "BudgetLedger",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "Choice",
    "CircuitBreaker",
    "CircuitState",
    "GuardrailEngine",
    "GuardrailResult",
    "MessageEnvelope",
    "PermissionLevel",
    "ProviderRouter",
    "ProxyMetrics",
    "Role",
    "RoutingStrategy",
    "SchemaValidationError",
    "SemanticCache",
    "SpanKind",
    "SpanStatus",
    "StructuredOutputValidator",
    "TenantQuota",
    "TokenBucketLimiter",
    "ToolGovernor",
    "Tracer",
    "TraceSpan",
    "Usage",
    "stream_chat_completion",
]
