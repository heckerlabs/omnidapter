"""Unit tests for hosted billing and rate limiting."""

from __future__ import annotations

import pytest
from omnidapter_hosted.services.billing import check_rate_limit, reset_tenant_state


@pytest.fixture(autouse=True)
def clean_state():
    tid = "test-tenant-billing"
    reset_tenant_state(tid)
    yield
    reset_tenant_state(tid)


def test_first_request_allowed():
    allowed, limit, remaining, reset_at = check_rate_limit(
        tenant_id="test-tenant-billing",
        plan="free",
        rate_limit_free=10,
        rate_limit_paid=100,
    )
    assert allowed is True
    assert limit == 10
    assert remaining == 9


def test_paid_plan_higher_limit():
    allowed, limit, remaining, reset_at = check_rate_limit(
        tenant_id="test-tenant-billing",
        plan="payg",
        rate_limit_free=60,
        rate_limit_paid=600,
    )
    assert limit == 600


def test_rate_limit_exceeded():
    tid = "test-tenant-rl-exceed"
    reset_tenant_state(tid)
    try:
        for _ in range(3):
            allowed, _, _, _ = check_rate_limit(
                tenant_id=tid, plan="free", rate_limit_free=3, rate_limit_paid=100
            )
            assert allowed is True
        allowed, _, remaining, _ = check_rate_limit(
            tenant_id=tid, plan="free", rate_limit_free=3, rate_limit_paid=100
        )
        assert allowed is False
        assert remaining == 0
    finally:
        reset_tenant_state(tid)


def test_different_tenants_independent():
    t1, t2 = "test-tenant-rl-t1", "test-tenant-rl-t2"
    reset_tenant_state(t1)
    reset_tenant_state(t2)
    try:
        for _ in range(2):
            check_rate_limit(tenant_id=t1, plan="free", rate_limit_free=2, rate_limit_paid=100)
        allowed1, _, _, _ = check_rate_limit(
            tenant_id=t1, plan="free", rate_limit_free=2, rate_limit_paid=100
        )
        allowed2, _, _, _ = check_rate_limit(
            tenant_id=t2, plan="free", rate_limit_free=2, rate_limit_paid=100
        )
        assert allowed1 is False
        assert allowed2 is True
    finally:
        reset_tenant_state(t1)
        reset_tenant_state(t2)
