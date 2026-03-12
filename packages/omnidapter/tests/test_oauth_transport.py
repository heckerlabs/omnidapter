"""Unit tests for OAuth transport integration in OAuthProviderMixin."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import ProviderAPIError, TokenRefreshError, TransportError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.hooks import TransportHooks
from omnidapter.transport.retry import RetryPolicy


class DummyOAuthProvider(OAuthProviderMixin):
    provider_key = "dummy"
    token_endpoint = "https://provider.example/token"
    authorization_endpoint = "https://provider.example/auth"
    default_scopes = ["scope.read"]

    def __init__(self) -> None:
        self._client_id = "cid"
        self._client_secret = "csecret"


def _stored(provider_key: str = "dummy", refresh_token: str | None = "rt-123") -> StoredCredential:
    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(
            access_token="old-access",
            refresh_token=refresh_token,
            expires_at=datetime.now(tz=timezone.utc) - timedelta(minutes=30),
        ),
    )


class TestOAuthTransportConfig:
    def test_configure_oauth_transport_applies_to_http_client(self):
        provider = DummyOAuthProvider()
        policy = RetryPolicy.no_retry()
        hooks = TransportHooks()
        shared_client = MagicMock()

        provider.configure_oauth_transport(
            retry_policy=policy,
            hooks=hooks,
            http_client=shared_client,
        )

        http = provider._oauth_http()
        assert http._retry_policy is policy
        assert http._hooks is hooks
        assert http._shared_client is shared_client


class TestOAuthTransportErrors:
    async def test_exchange_wraps_transport_errors(self):
        provider = DummyOAuthProvider()
        mock_http = MagicMock()
        mock_http.request = AsyncMock(side_effect=TransportError("network down"))
        provider._oauth_http = MagicMock(return_value=mock_http)

        with pytest.raises(TokenRefreshError, match="token exchange failed") as exc:
            await provider.exchange_code_for_tokens(
                connection_id="conn-1",
                code="code-abc",
                redirect_uri="https://app.example/cb",
            )

        assert isinstance(exc.value.cause, TransportError)
        mock_http.request.assert_awaited_once()

    async def test_refresh_wraps_provider_api_errors(self):
        provider = DummyOAuthProvider()
        mock_http = MagicMock()
        mock_http.request = AsyncMock(
            side_effect=ProviderAPIError(
                "token endpoint failed",
                provider_key="dummy",
                status_code=500,
                correlation_id="corr-1",
            )
        )
        provider._oauth_http = MagicMock(return_value=mock_http)

        with pytest.raises(TokenRefreshError, match="token refresh failed") as exc:
            await provider.refresh_token(_stored())

        assert isinstance(exc.value.cause, ProviderAPIError)
        mock_http.request.assert_awaited_once()


class TestOAuthTransportSuccess:
    async def test_refresh_preserves_refresh_token_when_omitted(self):
        provider = DummyOAuthProvider()
        response = MagicMock()
        response.json.return_value = {
            "access_token": "new-access",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        mock_http = MagicMock()
        mock_http.request = AsyncMock(return_value=response)
        provider._oauth_http = MagicMock(return_value=mock_http)

        updated = await provider.refresh_token(_stored(refresh_token="persist-me"))

        assert isinstance(updated.credentials, OAuth2Credentials)
        assert updated.credentials.access_token == "new-access"
        assert updated.credentials.refresh_token == "persist-me"
