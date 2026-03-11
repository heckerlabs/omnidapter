"""
Mixin base class for OAuth2 provider implementations.

Providers subclass OAuthProviderMixin and declare their fixed values as class
attributes.  The mixin supplies the standard authorization-code exchange and
refresh-token HTTP logic, so provider subclasses contain no HTTP code at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import httpx

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import (
    ProviderAPIError,
    ProviderNotConfiguredError,
    RateLimitError,
    TokenRefreshError,
    TransportError,
)
from omnidapter.core.metadata import AuthKind
from omnidapter.providers._base import OAuthConfig
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.client import OmnidapterHttpClient
from omnidapter.transport.hooks import TransportHooks
from omnidapter.transport.retry import RetryPolicy


class OAuthProviderMixin:
    """Standard OAuth2 authorization-code + refresh-token flow.

    Subclasses must declare as class attributes:
        provider_key: str
        token_endpoint: str
        authorization_endpoint: str
        default_scopes: list[str]
        supports_pkce: bool

    Optional class attributes (with defaults):
        extra_auth_params: dict[str, str]  (default {})
        scope_separator: str               (default " ")
        client_id_env_var: str | None      (default None)
        client_secret_env_var: str | None  (default None)

    Instances must expose:
        self._client_id: str
        self._client_secret: str
    """

    provider_key: str
    token_endpoint: str
    authorization_endpoint: str
    default_scopes: list[str] = []
    supports_pkce: bool = False
    extra_auth_params: dict[str, str] = {}
    scope_separator: str = " "
    client_id_env_var: str | None = None
    client_secret_env_var: str | None = None
    _client_id: str | None
    _client_secret: str | None
    _oauth_retry_policy: RetryPolicy | None = None
    _oauth_hooks: TransportHooks | None = None
    _oauth_http_client: httpx.AsyncClient | None = None

    def get_oauth_config(self) -> OAuthConfig | None:
        client_id, client_secret = self._oauth_client_credentials()
        return OAuthConfig(
            client_id=client_id,
            client_secret=client_secret,
            authorization_endpoint=self.authorization_endpoint,
            token_endpoint=self.token_endpoint,
            default_scopes=list(self.default_scopes),
            supports_pkce=self.supports_pkce,
            extra_auth_params=dict(self.extra_auth_params),
            scope_separator=self.scope_separator,
        )

    def _oauth_client_credentials(self) -> tuple[str, str]:
        self._ensure_oauth_configured()
        client_id = self._client_id
        client_secret = self._client_secret
        if client_id is None or client_secret is None:
            # Defensive guard for type checkers; _ensure_oauth_configured handles this in practice.
            missing = self._missing_configuration_fields()
            raise ProviderNotConfiguredError(
                f"Provider {self.provider_key!r} is missing OAuth configuration",
                provider_key=self.provider_key,
                missing_fields=missing,
            )
        return cast(str, client_id), cast(str, client_secret)

    def configure_oauth_transport(
        self,
        *,
        retry_policy: RetryPolicy | None = None,
        hooks: TransportHooks | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Attach transport configuration for OAuth token calls."""
        self._oauth_retry_policy = retry_policy
        self._oauth_hooks = hooks
        self._oauth_http_client = http_client

    def _oauth_http(self) -> OmnidapterHttpClient:
        return OmnidapterHttpClient(
            provider_key=self.provider_key,
            retry_policy=self._oauth_retry_policy,
            hooks=self._oauth_hooks,
            shared_client=self._oauth_http_client,
        )

    @staticmethod
    def _is_missing(value: str | None) -> bool:
        return value is None or not value.strip()

    def _missing_configuration_fields(self) -> list[str]:
        missing: list[str] = []
        if self._is_missing(getattr(self, "_client_id", None)):
            missing.append(self.client_id_env_var or "client_id")
        if self._is_missing(getattr(self, "_client_secret", None)):
            missing.append(self.client_secret_env_var or "client_secret")
        return missing

    def _ensure_oauth_configured(self) -> None:
        missing = self._missing_configuration_fields()
        if not missing:
            return
        missing_text = ", ".join(missing)
        raise ProviderNotConfiguredError(
            (
                f"Provider {self.provider_key!r} supports OAuth2 but is not configured. "
                f"Missing: {missing_text}. Set these env vars or pass client_id/client_secret "
                f"to {self.__class__.__name__}(...)."
            ),
            provider_key=self.provider_key,
            missing_fields=missing,
        )

    def _build_stored_credential(self, token_data: dict[str, Any]) -> StoredCredential:
        expires_in = token_data.get("expires_in")
        expires_at = None
        if expires_in is not None:
            expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=int(expires_in))

        scopes_str = token_data.get("scope", "")
        granted_scopes = (
            [s for s in scopes_str.split(self.scope_separator) if s] if scopes_str else None
        )

        creds = OAuth2Credentials(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=expires_at,
            id_token=token_data.get("id_token"),
            raw=token_data,
        )

        return StoredCredential(
            provider_key=self.provider_key,
            auth_kind=AuthKind.OAUTH2,
            credentials=creds,
            granted_scopes=granted_scopes,
        )

    async def exchange_code_for_tokens(
        self,
        connection_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> StoredCredential:
        client_id, client_secret = self._oauth_client_credentials()

        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier

        try:
            response = await self._oauth_http().request("POST", self.token_endpoint, data=data)
        except (ProviderAPIError, RateLimitError, TransportError) as exc:
            raise TokenRefreshError(
                f"{self.provider_key} token exchange failed: {exc}",
                provider_key=self.provider_key,
                cause=exc,
            ) from exc

        return self._build_stored_credential(response.json())

    async def refresh_token(self, stored: StoredCredential) -> StoredCredential:
        client_id, client_secret = self._oauth_client_credentials()

        creds = stored.credentials
        if not isinstance(creds, OAuth2Credentials) or not creds.refresh_token:
            raise TokenRefreshError(
                "Cannot refresh: no refresh_token available",
                provider_key=self.provider_key,
            )

        data = {
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        try:
            response = await self._oauth_http().request("POST", self.token_endpoint, data=data)
        except (ProviderAPIError, RateLimitError, TransportError) as exc:
            raise TokenRefreshError(
                f"{self.provider_key} token refresh failed: {exc}",
                provider_key=self.provider_key,
                cause=exc,
            ) from exc

        token_data = response.json()
        if "refresh_token" not in token_data:
            token_data["refresh_token"] = creds.refresh_token

        updated = self._build_stored_credential(token_data)
        return updated.model_copy(
            update={
                "granted_scopes": stored.granted_scopes,
                "provider_account_id": stored.provider_account_id,
                "provider_config": stored.provider_config,
            }
        )
