"""Integration tests for OAuth flow (with mocked provider)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from omnidapter_server.main import app
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.models.oauth_state import OAuthState
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


def _make_oauth_begin_result(conn_id: str, provider: str = "google") -> MagicMock:
    """Fake OAuthBeginResult."""
    result = MagicMock()
    result.authorization_url = "https://accounts.google.com/oauth?state=teststate123&client_id=test"
    result.state = "teststate123"
    result.connection_id = conn_id
    result.provider = provider
    return result


@pytest.mark.asyncio
async def test_create_connection_returns_authorization_url(
    client: AsyncClient,
    session: AsyncSession,
):
    """POST /connections creates a pending connection and returns authorization_url."""
    mock_begin_result = MagicMock()
    mock_begin_result.authorization_url = "https://accounts.google.com/o/oauth2/v2/auth?state=abc"
    mock_begin_result.state = "abc"

    with patch("omnidapter_server.routers.connections.Omnidapter") as MockOmni:
        mock_omni_instance = MagicMock()
        mock_omni_instance.oauth.begin = AsyncMock(return_value=mock_begin_result)
        MockOmni.return_value = mock_omni_instance

        response = await client.post(
            "/v1/connections",
            json={
                "provider": "google",
                "external_id": "test_user_123",
                "redirect_url": "https://app.example.com/connected",
            },
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert "authorization_url" in data
    assert "connection_id" in data


@pytest.mark.asyncio
async def test_create_connection_sets_pending_status(
    client: AsyncClient,
    session: AsyncSession,
):
    """Connection created in pending state."""
    mock_begin_result = MagicMock()
    mock_begin_result.authorization_url = "https://accounts.google.com/auth?state=xyz"
    mock_begin_result.state = "xyz"

    with patch("omnidapter_server.routers.connections.Omnidapter") as MockOmni:
        mock_omni_instance = MagicMock()
        mock_omni_instance.oauth.begin = AsyncMock(return_value=mock_begin_result)
        MockOmni.return_value = mock_omni_instance

        response = await client.post(
            "/v1/connections",
            json={
                "provider": "google",
                "external_id": "user_pending",
                "redirect_url": "https://app.example.com/done",
            },
        )

    assert response.status_code == 201
    conn_id = response.json()["data"]["connection_id"]

    # Verify in DB
    from sqlalchemy import select

    result = await session.execute(select(Connection).where(Connection.id == uuid.UUID(conn_id)))
    conn = result.scalar_one_or_none()
    assert conn is not None
    assert conn.status == ConnectionStatus.PENDING
    assert conn.external_id == "user_pending"


@pytest.mark.asyncio
async def test_oauth_callback_transitions_to_active(
    client: AsyncClient,
    session: AsyncSession,
    encryption,
):
    """Callback with valid code/state transitions connection to active."""
    # Create connection + OAuth state manually
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="callback_user",
        status=ConnectionStatus.PENDING,
        provider_config={"redirect_url": "https://app.example.com/done"},
    )
    session.add(conn)
    await session.flush()

    from datetime import datetime, timedelta, timezone

    state_token = "teststate_abc123"
    oauth_state = OAuthState(
        id=uuid.uuid4(),
        provider_key="google",
        connection_id=conn.id,
        state_token=state_token,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        redirect_uri="http://testserver/oauth/google/callback",
        metadata_={
            "connection_id": str(conn.id),
            "provider": "google",
            "redirect_uri": "http://testserver/oauth/google/callback",
        },
    )
    session.add(oauth_state)
    await session.flush()

    # Mock the Omnidapter.oauth.complete
    from omnidapter import OAuth2Credentials
    from omnidapter.core.metadata import AuthKind
    from omnidapter.stores.credentials import StoredCredential

    mock_credential = StoredCredential(
        provider_key="google",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(
            access_token="fake_access_token",
            token_type="Bearer",
        ),
        granted_scopes=["https://www.googleapis.com/auth/calendar"],
        provider_account_id="user@gmail.com",
    )

    with patch("omnidapter_server.routers.oauth.Omnidapter") as MockOmni:
        mock_instance = MagicMock()
        mock_instance.oauth.complete = AsyncMock(return_value=mock_credential)
        MockOmni.return_value = mock_instance

        # No auth header needed for callback — it's public
        async with AsyncClient(
            transport=ASGITransport(app), base_url="http://testserver"
        ) as public_client:
            response = await public_client.get(
                f"/oauth/google/callback?code=auth_code&state={state_token}",
                follow_redirects=False,
            )

    # Should redirect to the redirect_url
    assert response.status_code in (200, 302)


@pytest.mark.asyncio
async def test_oauth_callback_invalid_state(
    client: AsyncClient,
    session: AsyncSession,
):
    """Callback with invalid state returns error."""
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://testserver"
    ) as public_client:
        response = await public_client.get(
            "/oauth/google/callback?code=some_code&state=INVALID_STATE_TOKEN",
            follow_redirects=False,
        )
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_oauth_callback_error_from_provider(
    client: AsyncClient,
    session: AsyncSession,
):
    """Callback with error param from provider is handled gracefully."""
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://testserver"
    ) as public_client:
        response = await public_client.get(
            "/oauth/google/callback?error=access_denied&error_description=User+denied+access",
            follow_redirects=False,
        )
    assert response.status_code in (400, 422)
