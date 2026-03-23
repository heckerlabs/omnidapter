"""Unit tests for hosted usage recording."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter_hosted.services.usage import count_monthly_usage, is_billable_endpoint, record_usage


class _ScalarResult:
    def __init__(self, one):
        self._one = one

    def scalar_one(self):
        return self._one


def test_calendar_endpoints_billable():
    assert is_billable_endpoint("calendar.list_events") is True
    assert is_billable_endpoint("calendar.create_event") is True
    assert is_billable_endpoint("calendar.get_availability") is True


def test_non_calendar_not_billable():
    assert is_billable_endpoint("connection.create") is False
    assert is_billable_endpoint("tenant.get") is False
    assert is_billable_endpoint("api_key.create") is False


@pytest.mark.asyncio
async def test_record_usage_creates_record():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    await record_usage(
        tenant_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        endpoint="calendar.list_events",
        provider_key="google",
        response_status=200,
        duration_ms=100,
        session=session,
    )
    session.add.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_record_usage_no_connection():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    await record_usage(
        tenant_id=uuid.uuid4(),
        connection_id=None,
        endpoint="tenant.get",
        provider_key=None,
        response_status=200,
        duration_ms=5,
        session=session,
    )
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_count_monthly_usage_with_explicit_period_start() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(7))

    count = await count_monthly_usage(
        tenant_id=uuid.uuid4(),
        session=session,
        period_start=date(2026, 1, 1),
    )

    assert count == 7
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_count_monthly_usage_none_defaults_to_zero() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(None))

    count = await count_monthly_usage(
        tenant_id=uuid.uuid4(),
        session=session,
        period_start=date(2026, 2, 1),
    )

    assert count == 0
