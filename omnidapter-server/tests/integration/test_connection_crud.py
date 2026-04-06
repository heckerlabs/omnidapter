"""Integration tests for connection CRUD via HTTP."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from omnidapter_server.models.connection import Connection, ConnectionStatus
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_list_connections_empty(client: AsyncClient):
    response = await client.get("/v1/connections")
    assert response.status_code == 200
    data = response.json()
    assert data["data"] == []
    assert data["meta"]["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_list_connections_with_filters(
    client: AsyncClient,
    session: AsyncSession,
):
    # Create some connections directly
    conn1 = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="user1",
        status=ConnectionStatus.ACTIVE,
    )
    conn2 = Connection(
        id=uuid.uuid4(),
        provider_key="microsoft",
        external_id="user2",
        status=ConnectionStatus.NEEDS_REAUTH,
    )
    session.add(conn1)
    session.add(conn2)
    await session.flush()

    # Filter by provider
    response = await client.get("/v1/connections?provider=google")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["provider"] == "google"

    # Filter by status
    response = await client.get("/v1/connections?status=needs_reauth")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["status"] == "needs_reauth"


@pytest.mark.asyncio
async def test_get_connection(
    client: AsyncClient,
    session: AsyncSession,
):
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="my_user",
        status=ConnectionStatus.ACTIVE,
        granted_scopes=["https://www.googleapis.com/auth/calendar"],
        provider_account_id="user@gmail.com",
    )
    session.add(conn)
    await session.flush()

    response = await client.get(f"/v1/connections/{conn.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["id"] == str(conn.id)
    assert data["data"]["provider"] == "google"
    assert data["data"]["external_id"] == "my_user"
    assert data["data"]["status"] == "active"
    assert data["data"]["provider_account_id"] == "user@gmail.com"


@pytest.mark.asyncio
async def test_get_connection_not_found(client: AsyncClient):
    response = await client.get(f"/v1/connections/{uuid.uuid4()}")
    assert response.status_code == 404
    payload = response.json()
    if "error" in payload:
        assert payload["error"]["code"] == "connection_not_found"
    else:
        assert payload["detail"]["code"] == "connection_not_found"


@pytest.mark.asyncio
async def test_delete_connection(
    client: AsyncClient,
    session: AsyncSession,
):
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="to_delete",
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn)
    await session.flush()

    response = await client.delete(f"/v1/connections/{conn.id}")
    assert response.status_code == 204

    # Verify status is revoked
    await session.refresh(conn)
    assert conn.status == ConnectionStatus.REVOKED


@pytest.mark.asyncio
async def test_connection_pagination(
    client: AsyncClient,
    session: AsyncSession,
):
    # Create 5 connections
    for i in range(5):
        conn = Connection(
            id=uuid.uuid4(),
            provider_key="google",
            external_id=f"user_{i}",
            status=ConnectionStatus.ACTIVE,
        )
        session.add(conn)
    await session.flush()

    response = await client.get("/v1/connections?limit=3&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 3
    assert data["meta"]["pagination"]["total"] == 5
    assert data["meta"]["pagination"]["has_more"] is True
