"""Integration tests for link token issuance and verification."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.services.auth import generate_hosted_api_key
from omnidapter_hosted.services.billing import _redis_clients
from omnidapter_server.database import get_session

@pytest_asyncio.fixture(autouse=True)
async def clear_redis_clients():
    _redis_clients.clear()
    yield
    _redis_clients.clear()

@pytest.mark.asyncio
async def test_issue_link_token(client: AsyncClient, test_api_key: tuple[str, HostedAPIKey]):
    """Verify that a link token can be issued via the Integration API."""
    raw_key, _ = test_api_key
    headers = {"Authorization": f"Bearer {raw_key}"}
    
    # Issue a link token
    payload = {
        "end_user_id": "user_123",
        "redirect_uri": "https://example.com/callback",
        "allowed_providers": ["google", "microsoft"]
    }
    response = await client.post("/v1/link-tokens", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()["data"]
    assert "token" in data
    assert data["token"].startswith("lt_")
    
    # Verify the link token via Connect UI providers endpoint
    link_token = data["token"]
    connect_headers = {"Authorization": f"Bearer {link_token}"}
    
    # Initiate connection
    payload = {"provider_key": "google"}
    response = await client.post("/connect/connections", json=payload, headers=connect_headers)
    assert response.status_code == 201
    data = response.json()["data"]
    assert "authorization_url" in data
    assert data["authorization_url"].startswith("http")
