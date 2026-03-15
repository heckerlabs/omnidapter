"""Integration tests for usage recording and free tier enforcement."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from omnidapter_api.models.connection import Connection, ConnectionStatus
from omnidapter_api.models.organization import Organization
from omnidapter_api.models.usage import UsageRecord
from omnidapter_api.services.usage import count_monthly_usage, record_usage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_billable_calls_are_recorded(
    session: AsyncSession,
    org: Organization,
    client: AsyncClient,
):
    """Calendar endpoint calls create usage records."""
    conn = Connection(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        external_id="usage_test",
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn)
    await session.flush()

    with patch("omnidapter_api.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.list_calendars = AsyncMock(return_value=[])
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        await client.get(f"/v1/connections/{conn.id}/calendar/calendars")

    result = await session.execute(select(UsageRecord).where(UsageRecord.organization_id == org.id))
    records = result.scalars().all()
    assert len(records) == 1
    assert records[0].endpoint == "calendar.list_calendars"
    assert records[0].provider_key == "google"
    assert records[0].response_status == 200


@pytest.mark.asyncio
async def test_non_billable_calls_not_recorded_as_usage(
    session: AsyncSession,
    org: Organization,
    client: AsyncClient,
):
    """Connection management calls do not create usage records."""
    response = await client.get("/v1/connections")
    assert response.status_code == 200

    result = await session.execute(select(UsageRecord).where(UsageRecord.organization_id == org.id))
    records = result.scalars().all()
    # No usage records for connection list
    assert len(records) == 0


@pytest.mark.asyncio
async def test_count_monthly_usage(
    session: AsyncSession,
    org: Organization,
):
    """Monthly usage counter works correctly."""
    initial = await count_monthly_usage(org.id, session)

    # Record some usage
    for _ in range(5):
        await record_usage(
            org_id=org.id,
            connection_id=None,
            endpoint="calendar.list_events",
            provider_key="google",
            response_status=200,
            duration_ms=100,
            session=session,
        )

    final = await count_monthly_usage(org.id, session)
    assert final - initial == 5


@pytest.mark.asyncio
async def test_free_tier_enforcement(
    session: AsyncSession,
    org: Organization,
    client: AsyncClient,
):
    """Org over free tier without payment method gets 402."""
    from omnidapter_api.config import Settings

    # Override settings with very low free tier
    def override_settings():
        return Settings(
            omnidapter_database_url="",
            omnidapter_encryption_key="dGVzdC1lbmNyeXB0aW9uLWtleS1pbnRlZ3JhdGlvbiEh",
            omnidapter_free_tier_calls=2,  # Very low limit
        )

    # Create an active connection
    conn = Connection(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        external_id="over_limit_user",
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn)
    await session.flush()

    # Record usage up to (and over) the limit
    for _ in range(3):  # Over the limit of 2
        await record_usage(
            org_id=org.id,
            connection_id=conn.id,
            endpoint="calendar.list_calendars",
            provider_key="google",
            response_status=200,
            duration_ms=100,
            session=session,
        )

    # Now a calendar call should be blocked
    from omnidapter_api.dependencies import get_settings as _get_settings
    from omnidapter_api.main import app

    app.dependency_overrides[_get_settings] = override_settings

    try:
        with patch("omnidapter_api.routers.calendar.Omnidapter") as MockOmni:
            mock_omni_inst = MagicMock()
            mock_conn_obj = MagicMock()
            mock_cal_svc = MagicMock()
            mock_cal_svc.list_calendars = AsyncMock(return_value=[])
            mock_conn_obj.calendar = MagicMock(return_value=mock_cal_svc)
            mock_omni_inst.connection = AsyncMock(return_value=mock_conn_obj)
            MockOmni.return_value = mock_omni_inst

            response = await client.get(f"/v1/connections/{conn.id}/calendar/calendars")
    finally:
        del app.dependency_overrides[_get_settings]

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "usage_limit_exceeded"
