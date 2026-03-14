"""Unit tests for usage metering and free tier enforcement."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter_api.services.usage import (
    BILLABLE_ENDPOINT_PREFIX,
    is_billable_endpoint,
    record_usage,
)


def test_calendar_endpoints_are_billable():
    assert is_billable_endpoint("calendar.list_events") is True
    assert is_billable_endpoint("calendar.create_event") is True
    assert is_billable_endpoint("calendar.get_event") is True
    assert is_billable_endpoint("calendar.list_calendars") is True
    assert is_billable_endpoint("calendar.delete_event") is True
    assert is_billable_endpoint("calendar.get_availability") is True


def test_non_calendar_endpoints_not_billable():
    assert is_billable_endpoint("connection.create") is False
    assert is_billable_endpoint("connection.list") is False
    assert is_billable_endpoint("provider_config.upsert") is False
    assert is_billable_endpoint("usage.get") is False
    assert is_billable_endpoint("org.get") is False


def test_billable_endpoint_prefix():
    assert BILLABLE_ENDPOINT_PREFIX == "calendar."


@pytest.mark.asyncio
async def test_record_usage_creates_record():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    await record_usage(
        org_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        endpoint="calendar.list_events",
        provider_key="google",
        response_status=200,
        duration_ms=150,
        session=session,
    )
    session.add.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_record_usage_no_connection_id():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    await record_usage(
        org_id=uuid.uuid4(),
        connection_id=None,
        endpoint="usage.get",
        provider_key=None,
        response_status=200,
        duration_ms=10,
        session=session,
    )
    session.add.assert_called_once()
