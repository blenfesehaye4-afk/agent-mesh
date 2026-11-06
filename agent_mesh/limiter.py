"""Token-bucket rate limiter with per-tenant quota allocation."""

import time
from typing import Dict, Tuple


class TokenBucketLimiter:
    """Token-bucket algorithm regulating API requests and token bandwidth."""

    def __init__(self, capacity: int = 60, refill_rate_per_sec: float = 1.0):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        # tenant_id -> (current_tokens, last_refill_timestamp)
        self.buckets: Dict[str, Tuple[float, float]] = {}

    def allow(self, tenant_id: str, cost: int = 1) -> bool:
        """Evaluate if the tenant has sufficient budget tokens."""
        now = time.time()
        tokens, last_time = self.buckets.get(tenant_id, (self.capacity, now))

        # Refill tokens according to elapsed delta
        elapsed = now - last_time
        tokens = min(self.capacity, tokens + (elapsed * self.refill_rate))

        if tokens >= cost:
            self.buckets[tenant_id] = (tokens - cost, now)
            return True
        else:
            self.buckets[tenant_id] = (tokens, now)
            return False

    def reset(self, tenant_id: str) -> None:
        self.buckets.pop(tenant_id, None)
