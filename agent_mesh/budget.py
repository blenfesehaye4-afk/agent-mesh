"""Intelligent Token Accounting, Cost Governance & Dynamic Model Routing.

Tracks multi-tenant token consumption and USD expenditures, enforces hard and soft
budget ceilings, and performs dynamic cost-aware model downgrading (e.g. flagship
models automatically routing to lightweight efficient models when budget thresholds are crossed).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BudgetExceededError(PermissionError):
    """Raised when a tenant exceeds their allotted spending or token ceiling."""
    pass


# Default pricing per 1,000 tokens: (prompt_cost_usd_per_1k, completion_cost_usd_per_1k)
MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.01, 0.03),
    "claude-3-5-sonnet": (0.003, 0.015),
    "claude-3-haiku": (0.00025, 0.00125),
    "deepseek-chat": (0.00014, 0.00028),
    "default": (0.002, 0.006),
}


class TenantQuota(BaseModel):
    """Spending constraints and usage metrics for a specific tenant."""

    tenant_id: str
    max_budget_usd: float = Field(default=100.0, ge=0.0, description="Hard budget cap in USD")
    soft_limit_usd: float = Field(default=80.0, ge=0.0, description="Soft alert/downgrade ceiling in USD")
    max_tokens: int = Field(default=10_000_000, ge=0, description="Maximum total tokens allowed")
    current_spend_usd: float = Field(default=0.0, ge=0.0, description="Accumulated spending in USD")
    tokens_used: int = Field(default=0, ge=0, description="Accumulated tokens consumed")
    downgrade_on_soft_limit: bool = Field(default=True, description="Automatically downgrade to lightweight model if soft limit passed")
    fallback_model: str = Field(default="gpt-4o-mini", description="Lightweight model to downgrade to when near quota")

    def is_hard_limit_exceeded(self) -> bool:
        return self.current_spend_usd >= self.max_budget_usd or self.tokens_used >= self.max_tokens

    def is_soft_limit_exceeded(self) -> bool:
        return self.current_spend_usd >= self.soft_limit_usd


class BudgetLedger:
    """Enterprise budget governor managing multi-tenant spending limits and cost routing."""

    def __init__(self, default_budget_usd: float = 100.0, default_soft_limit_usd: float = 80.0):
        self.default_budget_usd = default_budget_usd
        self.default_soft_limit_usd = default_soft_limit_usd
        self._quotas: Dict[str, TenantQuota] = {}

    def get_or_create_quota(self, tenant_id: str) -> TenantQuota:
        """Retrieve tenant quota or initialize with default parameters."""
        if tenant_id not in self._quotas:
            self._quotas[tenant_id] = TenantQuota(
                tenant_id=tenant_id,
                max_budget_usd=self.default_budget_usd,
                soft_limit_usd=self.default_soft_limit_usd,
            )
        return self._quotas[tenant_id]

    def set_quota(
        self,
        tenant_id: str,
        max_budget_usd: float,
        soft_limit_usd: Optional[float] = None,
        max_tokens: Optional[int] = None,
        downgrade_on_soft_limit: Optional[bool] = None,
        fallback_model: Optional[str] = None,
    ) -> TenantQuota:
        """Explicitly configure spending parameters for a tenant."""
        quota = self.get_or_create_quota(tenant_id)
        quota.max_budget_usd = max(0.0, max_budget_usd)
        quota.soft_limit_usd = max_budget_usd * 0.8 if soft_limit_usd is None else max(0.0, soft_limit_usd)
        if max_tokens is not None:
            quota.max_tokens = max(0, max_tokens)
        if downgrade_on_soft_limit is not None:
            quota.downgrade_on_soft_limit = downgrade_on_soft_limit
        if fallback_model is not None:
            quota.fallback_model = fallback_model
        return quota

    @staticmethod
    def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute exact USD cost based on token counts and model pricing."""
        prompt_rate, completion_rate = MODEL_PRICING.get(model, MODEL_PRICING["default"])
        cost = (prompt_tokens / 1000.0 * prompt_rate) + (completion_tokens / 1000.0 * completion_rate)
        return round(cost, 6)

    def check_budget(self, tenant_id: str) -> None:
        """Verify tenant is within hard spending bounds prior to inference."""
        quota = self.get_or_create_quota(tenant_id)
        if quota.is_hard_limit_exceeded():
            raise BudgetExceededError(
                f"Tenant '{tenant_id}' has exceeded budget limit (${quota.current_spend_usd:.4f} / ${quota.max_budget_usd:.2f} USD, {quota.tokens_used}/{quota.max_tokens} tokens)."
            )

    def resolve_effective_model(self, tenant_id: str, requested_model: str) -> Tuple[str, bool]:
        """Determine if request should be routed to a cheaper fallback model based on budget status."""
        quota = self.get_or_create_quota(tenant_id)
        if quota.downgrade_on_soft_limit and quota.is_soft_limit_exceeded():
            if requested_model != quota.fallback_model:
                logger.warning(
                    f"Tenant '{tenant_id}' exceeded soft limit (${quota.current_spend_usd:.4f} >= ${quota.soft_limit_usd:.2f}). Downgrading '{requested_model}' -> '{quota.fallback_model}'"
                )
                return quota.fallback_model, True
        return requested_model, False

    def record_usage(
        self,
        tenant_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> Dict[str, Any]:
        """Record token usage, compute incremental cost, and update tenant balance."""
        quota = self.get_or_create_quota(tenant_id)
        cost = self.calculate_cost(model, prompt_tokens, completion_tokens)
        total_tokens = prompt_tokens + completion_tokens

        quota.current_spend_usd = round(quota.current_spend_usd + cost, 6)
        quota.tokens_used += total_tokens

        return {
            "tenant_id": tenant_id,
            "cost_usd": cost,
            "total_spend_usd": quota.current_spend_usd,
            "tokens_used": quota.tokens_used,
            "remaining_budget_usd": max(0.0, round(quota.max_budget_usd - quota.current_spend_usd, 6)),
            "hard_limit_exceeded": quota.is_hard_limit_exceeded(),
            "soft_limit_exceeded": quota.is_soft_limit_exceeded(),
        }

    def get_summary(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Provide detailed usage telemetry across tenants or for a specific tenant."""
        if tenant_id:
            quota = self.get_or_create_quota(tenant_id)
            return quota.model_dump()
        return {tid: q.model_dump() for tid, q in self._quotas.items()}
