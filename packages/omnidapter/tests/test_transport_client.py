"""Unit tests for Omnidapter HTTP transport client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
from omnidapter.transport.client import OmnidapterHttpClient
from omnidapter.transport.retry import RetryPolicy


class TestSharedClientUsage:
    async def test_request_uses_injected_shared_client(self):
        shared_client = MagicMock()
        shared_client.request = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"ok": True},
                request=httpx.Request("GET", "https://api.example.com/ping"),
            )
        )

        client = OmnidapterHttpClient(
            provider_key="test",
            retry_policy=RetryPolicy.no_retry(),
            shared_client=shared_client,
        )
        client._build_client = MagicMock(side_effect=AssertionError("should not build new client"))

        response = await client.request("GET", "https://api.example.com/ping")

        assert response.status_code == 200
        shared_client.request.assert_awaited_once()

    async def test_relative_url_is_resolved_with_base_url_when_shared_client_is_used(self):
        shared_client = MagicMock()
        shared_client.request = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"ok": True},
                request=httpx.Request("GET", "https://api.example.com/v1/ping"),
            )
        )

        client = OmnidapterHttpClient(
            provider_key="test",
            retry_policy=RetryPolicy.no_retry(),
            base_url="https://api.example.com/v1",
            shared_client=shared_client,
        )

        await client.request("GET", "/ping")

        args, _ = shared_client.request.call_args
        assert args[1] == "https://api.example.com/v1/ping"
