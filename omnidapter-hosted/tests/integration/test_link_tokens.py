"""Integration tests for link token issuance and the connect session exchange."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.services.billing import _redis_clients


@pytest_asyncio.fixture(autouse=True)
async def clear_redis_clients():
    _redis_clients.clear()
    yield
    _redis_clients.clear()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_issue_link_token(client: AsyncClient, test_api_key: tuple[str, HostedAPIKey]):
    """Issue an lt_* link token and exchange it for a cs_* session token."""
    raw_key, _ = test_api_key
    headers = {"Authorization": f"Bearer {raw_key}"}

    # Issue a link token
    payload = {
        "end_user_id": "user_123",
        "redirect_uri": "https://example.com/callback",
        "allowed_providers": ["google", "microsoft"],
    }
    response = await client.post("/v1/link-tokens", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()["data"]
    assert "token" in data
    link_token = data["token"]
    assert link_token.startswith("lt_")

    # Exchange the bootstrap token for a session token
    response = await client.post("/connect/session", json={"token": link_token})
    assert response.status_code == 200
    session_data = response.json()["data"]
    assert "session_token" in session_data
    session_token = session_data["session_token"]
    assert session_token.startswith("cs_")
    assert session_data["expires_in"] > 0

    # Bootstrap token is now consumed — second exchange must fail
    response = await client.post("/connect/session", json={"token": link_token})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "token_already_used"

    # Use the session token to list providers
    connect_headers = {"Authorization": f"Bearer {session_token}"}
    response = await client.get("/connect/providers", headers=connect_headers)
    assert response.status_code == 200
    providers = response.json()["providers"]
    assert len(providers) > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_connect_session_invalid_bootstrap_token(client: AsyncClient):
    """POST /connect/session with a garbage token returns 401."""
    response = await client.post("/connect/session", json={"token": "lt_notreal"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "session_expired"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_connect_session_lt_token_rejected_on_connect_endpoints(
    client: AsyncClient, test_api_key: tuple[str, HostedAPIKey]
):
    """An unconsumed lt_* token is rejected on /connect/* endpoints (cs_* required)."""
    raw_key, _ = test_api_key
    headers = {"Authorization": f"Bearer {raw_key}"}

    response = await client.post(
        "/v1/link-tokens",
        json={"end_user_id": "u1", "redirect_uri": "https://example.com/cb"},
        headers=headers,
    )
    assert response.status_code == 201
    link_token = response.json()["data"]["token"]

    # Using the raw lt_* token on /connect/providers must be rejected
    connect_headers = {"Authorization": f"Bearer {link_token}"}
    response = await client.get("/connect/providers", headers=connect_headers)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] in ("unauthenticated", "session_expired")
