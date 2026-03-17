"""Hosted billing — rate limiting and free-tier enforcement per tenant."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from omnidapter_hosted.models.tenant import TenantPlan

# In-memory sliding-window rate limiter (per tenant)
# For production, replace with Redis-backed implementation.


@dataclass
class _RateLimitState:
    requests: deque[float] = field(default_factory=deque)


_rl_state: dict[str, _RateLimitState] = defaultdict(_RateLimitState)
_WINDOW_SECONDS = 60


def check_rate_limit(
    tenant_id: str,
    plan: str,
    rate_limit_free: int,
    rate_limit_paid: int,
) -> tuple[bool, int, int, float]:
    """Check and record a rate limit hit.

    Returns:
        (allowed, limit, remaining, reset_at)
    """
    limit = rate_limit_paid if plan == TenantPlan.PAYG else rate_limit_free
    now = time.time()
    window_start = now - _WINDOW_SECONDS

    state = _rl_state[tenant_id]
    while state.requests and state.requests[0] < window_start:
        state.requests.popleft()

    current = len(state.requests)
    if current >= limit:
        reset_at = state.requests[0] + _WINDOW_SECONDS if state.requests else now + _WINDOW_SECONDS
        return False, limit, 0, reset_at

    state.requests.append(now)
    remaining = max(0, limit - len(state.requests))
    reset_at = (state.requests[0] + _WINDOW_SECONDS) if state.requests else now + _WINDOW_SECONDS
    return True, limit, remaining, reset_at


def reset_tenant_state(tenant_id: str) -> None:
    """Reset rate limit state for a tenant (for testing)."""
    if tenant_id in _rl_state:
        del _rl_state[tenant_id]
