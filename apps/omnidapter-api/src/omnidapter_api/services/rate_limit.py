"""In-memory rate limiting service (per-organization, sliding window)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from omnidapter_api.models.organization import PlanType


@dataclass
class RateLimitState:
    requests: deque[float] = field(default_factory=deque)


# Global in-memory state: org_id -> RateLimitState
_state: dict[str, RateLimitState] = defaultdict(RateLimitState)
_WINDOW_SECONDS = 60


def check_rate_limit(
    org_id: str,
    plan: str,
    rate_limit_free: int,
    rate_limit_paid: int,
) -> tuple[bool, int, int, float]:
    """Check and record a rate limit hit.

    Returns:
        (allowed, limit, remaining, reset_at)
    """
    limit = rate_limit_paid if plan == PlanType.PAYG else rate_limit_free
    now = time.time()
    window_start = now - _WINDOW_SECONDS

    state = _state[org_id]
    # Evict expired entries
    while state.requests and state.requests[0] < window_start:
        state.requests.popleft()

    current = len(state.requests)
    remaining = max(0, limit - current)

    if current >= limit:
        reset_at = state.requests[0] + _WINDOW_SECONDS if state.requests else now + _WINDOW_SECONDS
        return False, limit, 0, reset_at

    state.requests.append(now)
    remaining = max(0, limit - len(state.requests))
    reset_at = (state.requests[0] + _WINDOW_SECONDS) if state.requests else now + _WINDOW_SECONDS
    return True, limit, remaining, reset_at


def reset_org_state(org_id: str) -> None:
    """Reset rate limit state for an org (for testing)."""
    if org_id in _state:
        del _state[org_id]
