"""Integration tests for Hosted Connect UI (lt_*)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from omnidapter_hosted.config import HostedSettings
from omnidapter_hosted.dependencies import LinkTokenContext, get_link_token_context
from omnidapter_hosted.main import create_app
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_server.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def link_token_client(
    db_session: AsyncSession, test_tenant: Tenant, test_user: HostedUser
) -> AsyncGenerator[AsyncClient, None]:
    """An AsyncClient with get_link_token_context mocked to avoid DB complexity."""

    # Create the context we want to "resolve" to
    mock_context = LinkTokenContext(
        tenant_id=test_tenant.id,
        end_user_id="end_user_123",
        allowed_providers=None,
        redirect_uri="https://client.com/callback",
        link_token_id=uuid.uuid4(),
    )

    settings = HostedSettings()
    settings.jwt_secret = "a" * 32
    settings.omnidapter_google_client_id = "test-google-id"
    settings.omnidapter_google_client_secret = "test-google-secret"
    app = create_app(settings=settings)

    # Override both session and the link token dependency
    async def _get_session_override():
        yield db_session

    async def _get_link_token_context_override():
        return mock_context

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_link_token_context] = _get_link_token_context_override

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer lt_mocked_token"},
    ) as ac:
        yield ac


async def test_list_providers_connect(link_token_client: AsyncClient):
    """Test GET /connect/providers with a mocked link token context."""
    response = await link_token_client.get("/connect/providers")
    assert response.status_code == 200
    providers = response.json()["providers"]
    assert len(providers) > 0
    keys = [p["key"] for p in providers]
    assert "google" in keys
    assert "microsoft" not in keys


async def test_create_connection_connect_oauth_init(link_token_client: AsyncClient):
    """Test POST /connect/connections initiates an OAuth flow."""
    payload = {"provider_key": "google", "redirect_uri": "https://client.com/callback"}
    response = await link_token_client.post("/connect/connections", json=payload)

    assert response.status_code == 201
    data = response.json()["data"]
    assert "connection_id" in data
    assert data["status"] == "pending"
    assert "authorization_url" in data
    assert "accounts.google.com" in data["authorization_url"]


async def test_create_connection_unauthorized(client: AsyncClient):
    """Test GET /connect/providers fails without a token."""
    response = await client.get("/connect/providers")
    assert response.status_code == 401
