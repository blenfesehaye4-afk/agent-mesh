import time
import pytest
from agent_mesh.limiter import TokenBucketLimiter


def test_rate_limiter_allows_under_capacity():
    limiter = TokenBucketLimiter(capacity=5, refill_rate_per_sec=1.0)
    tenant = "client_alpha"

    # Consume all 5 tokens
    for _ in range(5):
        assert limiter.allow(tenant, cost=1) is True

    # 6th should be rejected
    assert limiter.allow(tenant, cost=1) is False
