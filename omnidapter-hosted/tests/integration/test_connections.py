"""Integration tests for connection management and tenant isolation."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_server.models.connection import Connection, ConnectionStatus
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_list_connections_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_api_key: tuple[str, HostedAPIKey],
    second_api_key: tuple[str, HostedAPIKey],
):
    """Verify that Tenant A cannot see Tenant B's connections."""
    raw_key_a, _ = test_api_key
    raw_key_b, _ = second_api_key

    # Create a connection for Tenant A
    conn_a = Connection(
        id=uuid.uuid4(), provider_key="google", external_id="user_a", status=ConnectionStatus.ACTIVE
    )
    db_session.add(conn_a)
    await db_session.flush()

    owner_a = HostedConnectionOwner(
        id=uuid.uuid4(),
        tenant_id=test_api_key[1].tenant_id,
        connection_id=conn_a.id,
    )
    db_session.add(owner_a)
    await db_session.flush()

    # List as Tenant A (should see 1 connection)
    response = await client.get("/v1/connections", headers={"Authorization": f"Bearer {raw_key_a}"})
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["id"] == str(conn_a.id)

    # List as Tenant B (should see 0 connections)
    response = await client.get("/v1/connections", headers={"Authorization": f"Bearer {raw_key_b}"})
    assert response.status_code == 200
    assert len(response.json()["data"]) == 0


@pytest.mark.asyncio
async def test_get_connection_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_api_key: tuple[str, HostedAPIKey],
    second_api_key: tuple[str, HostedAPIKey],
):
    """Verify that Tenant B cannot fetch Tenant A's connection."""
    raw_key_a, _ = test_api_key
    raw_key_b, _ = second_api_key

    # Create connection for Tenant A
    conn_a = Connection(
        id=uuid.uuid4(), provider_key="google", external_id="user_a", status=ConnectionStatus.ACTIVE
    )
    db_session.add(conn_a)
    await db_session.flush()

    owner_a = HostedConnectionOwner(
        id=uuid.uuid4(), tenant_id=test_api_key[1].tenant_id, connection_id=conn_a.id
    )
    db_session.add(owner_a)
    await db_session.flush()

    # Fetch as Tenant A (200 OK)
    response = await client.get(
        f"/v1/connections/{conn_a.id}", headers={"Authorization": f"Bearer {raw_key_a}"}
    )
    assert response.status_code == 200

    # Fetch as Tenant B (404 Not Found)
    response = await client.get(
        f"/v1/connections/{conn_a.id}", headers={"Authorization": f"Bearer {raw_key_b}"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_connection_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_api_key: tuple[str, HostedAPIKey],
    second_api_key: tuple[str, HostedAPIKey],
):
    """Verify that Tenant B cannot delete Tenant A's connection."""
    raw_key_a, _ = test_api_key
    raw_key_b, _ = second_api_key

    # Create connection for Tenant A
    conn_a = Connection(
        id=uuid.uuid4(), provider_key="google", external_id="user_a", status=ConnectionStatus.ACTIVE
    )
    db_session.add(conn_a)
    await db_session.flush()

    owner_a = HostedConnectionOwner(
        id=uuid.uuid4(), tenant_id=test_api_key[1].tenant_id, connection_id=conn_a.id
    )
    db_session.add(owner_a)
    await db_session.flush()

    # Delete as Tenant B (404 Not Found)
    response = await client.delete(
        f"/v1/connections/{conn_a.id}", headers={"Authorization": f"Bearer {raw_key_b}"}
    )
    assert response.status_code == 404

    # Verify still active
    await db_session.refresh(conn_a)
    assert conn_a.status == ConnectionStatus.ACTIVE

    # Delete as Tenant A (204 No Content)
    response = await client.delete(
        f"/v1/connections/{conn_a.id}", headers={"Authorization": f"Bearer {raw_key_a}"}
    )
    assert response.status_code == 204

    # Verify revoked
    await db_session.refresh(conn_a)
    assert conn_a.status == ConnectionStatus.REVOKED
