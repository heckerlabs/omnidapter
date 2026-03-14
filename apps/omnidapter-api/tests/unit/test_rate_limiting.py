"""Unit tests for rate limiting logic."""

from __future__ import annotations

import time

import pytest
from omnidapter_api.services.rate_limit import check_rate_limit, reset_org_state


@pytest.fixture(autouse=True)
def clean_state():
    """Clean rate limit state before each test."""
    org_id = "test-org-rate-limit"
    reset_org_state(org_id)
    yield
    reset_org_state(org_id)


def test_first_request_allowed():
    allowed, limit, remaining, reset_at = check_rate_limit(
        org_id="test-org-rate-limit",
        plan="free",
        rate_limit_free=10,
        rate_limit_paid=100,
    )
    assert allowed is True
    assert limit == 10
    assert remaining == 9


def test_free_tier_uses_free_limit():
    allowed, limit, remaining, reset_at = check_rate_limit(
        org_id="test-org-rate-limit",
        plan="free",
        rate_limit_free=60,
        rate_limit_paid=300,
    )
    assert limit == 60


def test_paid_tier_uses_paid_limit():
    allowed, limit, remaining, reset_at = check_rate_limit(
        org_id="test-org-rate-limit",
        plan="payg",
        rate_limit_free=60,
        rate_limit_paid=300,
    )
    assert limit == 300


def test_rate_limit_exceeded():
    org_id = "test-org-rate-limit-exceed"
    reset_org_state(org_id)
    try:
        limit = 3
        for _ in range(limit):
            allowed, _, _, _ = check_rate_limit(
                org_id=org_id,
                plan="free",
                rate_limit_free=limit,
                rate_limit_paid=100,
            )
            assert allowed is True

        # Next request should be denied
        allowed, _, remaining, _ = check_rate_limit(
            org_id=org_id,
            plan="free",
            rate_limit_free=limit,
            rate_limit_paid=100,
        )
        assert allowed is False
        assert remaining == 0
    finally:
        reset_org_state(org_id)


def test_different_orgs_have_separate_limits():
    org1 = "test-org-rl-1"
    org2 = "test-org-rl-2"
    reset_org_state(org1)
    reset_org_state(org2)
    try:
        limit = 2
        # Exhaust org1
        for _ in range(limit):
            check_rate_limit(org_id=org1, plan="free", rate_limit_free=limit, rate_limit_paid=100)

        allowed1, _, _, _ = check_rate_limit(
            org_id=org1, plan="free", rate_limit_free=limit, rate_limit_paid=100
        )
        allowed2, _, _, _ = check_rate_limit(
            org_id=org2, plan="free", rate_limit_free=limit, rate_limit_paid=100
        )
        assert allowed1 is False
        assert allowed2 is True  # org2 is independent
    finally:
        reset_org_state(org1)
        reset_org_state(org2)


def test_rate_limit_headers_returned():
    org_id = "test-org-rl-headers"
    reset_org_state(org_id)
    try:
        allowed, limit, remaining, reset_at = check_rate_limit(
            org_id=org_id,
            plan="free",
            rate_limit_free=60,
            rate_limit_paid=300,
        )
        assert isinstance(limit, int)
        assert isinstance(remaining, int)
        assert isinstance(reset_at, float)
        assert reset_at > time.time()
    finally:
        reset_org_state(org_id)
