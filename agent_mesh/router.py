"""Multi-provider failover router with Circuit Breaker resilience."""

import time
from enum import Enum
from typing import Callable, Dict, List, Optional


class CircuitState(str, Enum):
    CLOSED = "closed"        # Healthy, traffic flows normally
    OPEN = "open"            # Unhealthy, traffic fast-fails or reroutes
    HALF_OPEN = "half_open"  # Probing single request


class CircuitBreaker:
    """Monitors provider failure rates and trips open to prevent cascading failures."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 10.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitState.CLOSED

    def can_attempt(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN allows single probe

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN


class ProviderRouter:
    """Routes requests to primary provider with automatic failover to healthy alternatives."""

    def __init__(self, providers: List[str]):
        if not providers:
            raise ValueError("At least one provider must be configured")
        self.providers = providers
        self.breakers: Dict[str, CircuitBreaker] = {p: CircuitBreaker() for p in providers}

    def select_healthy_provider(self) -> str:
        """Select the highest-priority healthy provider."""
        for provider in self.providers:
            if self.breakers[provider].can_attempt():
                return provider
        raise RuntimeError("All configured upstream AI providers are currently unavailable (circuits OPEN)")

    def report_success(self, provider: str) -> None:
        if provider in self.breakers:
            self.breakers[provider].record_success()

    def report_failure(self, provider: str) -> None:
        if provider in self.breakers:
            self.breakers[provider].record_failure()
