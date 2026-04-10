"""Hosted billing — rate limiting and free-tier enforcement per tenant."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from omnidapter_hosted.config import HostedSettings
from omnidapter_hosted.models.tenant import TenantPlan

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60

_redis_clients: dict[str, Any] = {}
_warned_inmemory = False


@dataclass
class _RateLimitState:
    requests: deque[float] = field(default_factory=deque)


_rl_state: dict[str, _RateLimitState] = defaultdict(_RateLimitState)


def _get_redis_client(redis_url: str) -> Any:
    import redis.asyncio as aioredis

    client = _redis_clients.get(redis_url)
    if client is None:
        client = aioredis.from_url(redis_url, decode_responses=True)
        _redis_clients[redis_url] = client
    return client


def _check_rate_limit_inmemory(
    tenant_id: str,
    limit: int,
) -> tuple[bool, int, int, float]:
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


async def check_rate_limit(
    tenant_id: str,
    plan: str,
    settings: HostedSettings,
) -> tuple[bool, int, int, float]:
    """Check and record a rate limit hit.

    Returns:
        (allowed, limit, remaining, reset_at)
    """
    global _warned_inmemory

    limit = (
        settings.hosted_rate_limit_paid
        if plan == TenantPlan.PAYG
        else settings.hosted_rate_limit_free
    )

    if settings.hosted_rate_limit_redis_url:
        try:
            now = int(time.time())
            window_start = now - (now % _WINDOW_SECONDS)
            reset_at = float(window_start + _WINDOW_SECONDS)
            key = f"{settings.omnidapter_redis_prefix}:rate_limit:fixed_window:{tenant_id}:{window_start}"

            redis_client = _get_redis_client(settings.hosted_rate_limit_redis_url)
            count = int(await redis_client.incr(key))
            if count == 1:
                await redis_client.expire(key, _WINDOW_SECONDS + 1)

            if count > limit:
                return False, limit, 0, reset_at

            remaining = max(0, limit - count)
            return True, limit, remaining, reset_at
        except Exception:  # pragma: no cover - fallback behavior
            logger.exception("Redis-backed rate limiting failed; falling back to in-memory limiter")

    if not _warned_inmemory:
        logger.warning(
            "Using in-memory hosted rate limiter. "
            "Set HOSTED_RATE_LIMIT_REDIS_URL for distributed rate limiting."
        )
        _warned_inmemory = True

    return _check_rate_limit_inmemory(tenant_id, limit)


def reset_tenant_state(tenant_id: str) -> None:
    """Reset rate limit state for a tenant (for testing)."""
    if tenant_id in _rl_state:
        del _rl_state[tenant_id]
