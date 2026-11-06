"""Data models and schemas for AgentMesh proxy requests and responses."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    role: Role = Role.USER
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="gpt-4o", description="Target model identifier")
    messages: List[ChatMessage]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=1024, ge=1)
    stream: bool = False


class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))
    model: str
    choices: List[Choice]
    usage: Usage
    cached: bool = False
    similarity_score: Optional[float] = None
    pii_redacted: bool = False


class ProxyMetrics(BaseModel):
    requests_total: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    tokens_saved: int = 0
    pii_violations_total: int = 0
    blocked_injections_total: int = 0
