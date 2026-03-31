"""Integration tests for hosted API key authentication and rate limiting."""

from __future__ import annotations

import time
import pytest
from httpx import AsyncClient
from omnidapter_hosted.models.api_key import HostedAPIKey


@pytest.mark.asyncio
async def test_auth_missing_header(client: AsyncClient):
    """Verify that a request with missing Authorization header fails."""
    response = await client.get("/v1/connections")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_auth_invalid_header_format(client: AsyncClient):
    """Verify that a request with invalid Authorization header format fails."""
    response = await client.get(
        "/v1/connections",
        headers={"Authorization": "InvalidFormat key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_auth_invalid_key(client: AsyncClient):
    """Verify that a request with an invalid API key fails."""
    response = await client.get(
        "/v1/connections",
        headers={"Authorization": "Bearer omni_invalid_key_1234567890"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_auth_valid_key(client: AsyncClient, test_api_key: tuple[str, HostedAPIKey]):
    """Verify that a request with a valid API key succeeds."""
    raw_key, api_key_obj = test_api_key
    response = await client.get(
        "/v1/connections",
        headers={"Authorization": f"Bearer {raw_key}"}
    )
    # Success here might be 200 with an empty list or similar
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


@pytest.mark.asyncio
async def test_auth_rate_limiting(client: AsyncClient, test_api_key: tuple[str, HostedAPIKey]):
    """Verify that requests are rate limited."""
    raw_key, _ = test_api_key
    headers = {"Authorization": f"Bearer {raw_key}"}

    # First and second requests should succeed (limit is 2 in conftest)
    for _ in range(2):
        response = await client.get("/v1/connections", headers=headers)
        assert response.status_code == 200

    # Third request should be rate limited
    response = await client.get("/v1/connections", headers=headers)
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "rate_limited"
    # In a real environment, we'd mock the settings to set a very low limit.
    # But for an integration test, we can at least verify headers are present.
