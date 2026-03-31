"""Integration tests for calendar proxying and tenant isolation."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner

@pytest.fixture
def mock_calendar():
    from omnidapter import Calendar
    cal = MagicMock(spec=Calendar)
    cal.calendar_id = "primary"
    cal.summary = "Test Calendar"
    cal.model_dump = lambda **kw: {
        "calendar_id": "primary",
        "summary": "Test Calendar",
    }
    return cal

@pytest.mark.asyncio
async def test_list_calendars_proxy_isolation(
    client: AsyncClient, 
    db_session: AsyncSession, 
    test_api_key: tuple[str, HostedAPIKey],
    second_api_key: tuple[str, HostedAPIKey],
    mock_calendar
):
    """Verify that Tenant B cannot list Tenant A's calendars."""
    raw_key_a, _ = test_api_key
    raw_key_b, _ = second_api_key
    
    # Create connection for Tenant A
    conn_a = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="user_a",
        status=ConnectionStatus.ACTIVE
    )
    db_session.add(conn_a)
    await db_session.flush()
    
    owner_a = HostedConnectionOwner(
        id=uuid.uuid4(),
        tenant_id=test_api_key[1].tenant_id,
        connection_id=conn_a.id
    )
    db_session.add(owner_a)
    await db_session.flush()

    # Success as Tenant A (200 OK)
    with patch("omnidapter_hosted.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.list_calendars = AsyncMock(return_value=[mock_calendar])
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.get(
            f"/v1/connections/{conn_a.id}/calendars", 
            headers={"Authorization": f"Bearer {raw_key_a}"}
        )
        assert response.status_code == 200
        assert response.json()["data"][0]["calendar_id"] == "primary"

    # Failure as Tenant B (404 Not Found)
    response = await client.get(
        f"/v1/connections/{conn_a.id}/calendars", 
        headers={"Authorization": f"Bearer {raw_key_b}"}
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_create_calendar_proxy_isolation(
    client: AsyncClient, 
    db_session: AsyncSession, 
    test_api_key: tuple[str, HostedAPIKey],
    second_api_key: tuple[str, HostedAPIKey],
    mock_calendar
):
    """Verify that Tenant B cannot create calendars for Tenant A's connection."""
    raw_key_a, _ = test_api_key
    raw_key_b, _ = second_api_key
    
    # Create connection for Tenant A
    conn_a = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="user_a",
        status=ConnectionStatus.ACTIVE
    )
    db_session.add(conn_a)
    await db_session.flush()
    
    owner_a = HostedConnectionOwner(
        id=uuid.uuid4(),
        tenant_id=test_api_key[1].tenant_id,
        connection_id=conn_a.id
    )
    db_session.add(owner_a)
    await db_session.flush()

    # Success as Tenant A (201 Created)
    with patch("omnidapter_hosted.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.create_calendar = AsyncMock(return_value=mock_calendar)
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.post(
            f"/v1/connections/{conn_a.id}/calendars", 
            json={"summary": "New Calendar"},
            headers={"Authorization": f"Bearer {raw_key_a}"}
        )
        assert response.status_code == 201

    # Failure as Tenant B (404 Not Found)
    response = await client.post(
        f"/v1/connections/{conn_a.id}/calendars", 
        json={"summary": "New Calendar"},
        headers={"Authorization": f"Bearer {raw_key_b}"}
    )
    assert response.status_code == 404
