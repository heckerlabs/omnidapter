"""Unit tests for hosted billing and rate limiting."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from omnidapter_hosted.config import HostedSettings
from omnidapter_hosted.services.billing import check_rate_limit, reset_tenant_state


@pytest.fixture(autouse=True)
def clean_state():
    tid = "test-tenant-billing"
    reset_tenant_state(tid)
    yield
    reset_tenant_state(tid)


@pytest.mark.asyncio
async def test_first_request_allowed():
    allowed, limit, remaining, reset_at = await check_rate_limit(
        tenant_id="test-tenant-billing",
        plan="free",
        settings=HostedSettings(hosted_rate_limit_free=10, hosted_rate_limit_paid=100),
    )
    assert allowed is True
    assert limit == 10
    assert remaining == 9


@pytest.mark.asyncio
async def test_paid_plan_higher_limit():
    allowed, limit, remaining, reset_at = await check_rate_limit(
        tenant_id="test-tenant-billing",
        plan="payg",
        settings=HostedSettings(hosted_rate_limit_free=60, hosted_rate_limit_paid=600),
    )
    assert limit == 600


@pytest.mark.asyncio
async def test_rate_limit_exceeded():
    tid = "test-tenant-rl-exceed"
    reset_tenant_state(tid)
    settings = HostedSettings(hosted_rate_limit_free=3, hosted_rate_limit_paid=100)
    try:
        for _ in range(3):
            allowed, _, _, _ = await check_rate_limit(tenant_id=tid, plan="free", settings=settings)
            assert allowed is True
        allowed, _, remaining, _ = await check_rate_limit(
            tenant_id=tid, plan="free", settings=settings
        )
        assert allowed is False
        assert remaining == 0
    finally:
        reset_tenant_state(tid)


@pytest.mark.asyncio
async def test_different_tenants_independent():
    t1, t2 = "test-tenant-rl-t1", "test-tenant-rl-t2"
    reset_tenant_state(t1)
    reset_tenant_state(t2)
    settings = HostedSettings(hosted_rate_limit_free=2, hosted_rate_limit_paid=100)
    try:
        for _ in range(2):
            await check_rate_limit(tenant_id=t1, plan="free", settings=settings)
        allowed1, _, _, _ = await check_rate_limit(tenant_id=t1, plan="free", settings=settings)
        allowed2, _, _, _ = await check_rate_limit(tenant_id=t2, plan="free", settings=settings)
        assert allowed1 is False
        assert allowed2 is True
    finally:
        reset_tenant_state(t1)
        reset_tenant_state(t2)


@pytest.mark.asyncio
async def test_rate_limit_uses_redis_fixed_window_when_configured():
    redis_client = AsyncMock()
    redis_client.incr.return_value = 1

    with patch(
        "omnidapter_hosted.services.billing._get_redis_client",
        return_value=redis_client,
    ):
        allowed, limit, remaining, reset_at = await check_rate_limit(
            tenant_id="test-tenant-redis",
            plan="free",
            settings=HostedSettings(
                hosted_rate_limit_free=10,
                hosted_rate_limit_paid=100,
                hosted_rate_limit_redis_url="redis://localhost:6379/0",
            ),
        )

    assert allowed is True
    assert limit == 10
    assert remaining == 9
    redis_client.incr.assert_awaited_once()
    redis_client.expire.assert_awaited_once()
