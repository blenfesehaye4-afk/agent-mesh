import pytest
from agent_mesh.router import CircuitBreaker, CircuitState, ProviderRouter


def test_circuit_breaker_trips_on_failures():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_attempt() is True

    cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_attempt() is False


def test_provider_router_failover():
    router = ProviderRouter(providers=["openai-primary", "anthropic-secondary"])

    # Initially selects primary
    assert router.select_healthy_provider() == "openai-primary"

    # Primary fails 3 times
    router.report_failure("openai-primary")
    router.report_failure("openai-primary")
    router.report_failure("openai-primary")

    # Should now failover to secondary
    assert router.select_healthy_provider() == "anthropic-secondary"
