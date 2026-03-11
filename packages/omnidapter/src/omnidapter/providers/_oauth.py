"""
Mixin base class for OAuth2 provider implementations.

Providers subclass OAuthProviderMixin and declare their fixed values as class
attributes.  The mixin supplies the standard authorization-code exchange and
refresh-token HTTP logic, so provider subclasses contain no HTTP code at all.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import TokenRefreshError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers._base import OAuthConfig
from omnidapter.stores.credentials import StoredCredential


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

    def get_oauth_config(self) -> OAuthConfig | None:
        if not self._client_id:
            return None
        return OAuthConfig(
            client_id=self._client_id,
            client_secret=self._client_secret,
            authorization_endpoint=self.authorization_endpoint,
            token_endpoint=self.token_endpoint,
            default_scopes=list(self.default_scopes),
            supports_pkce=self.supports_pkce,
            extra_auth_params=dict(self.extra_auth_params),
        )

    def _build_stored_credential(self, token_data: dict[str, Any]) -> StoredCredential:
        expires_in = token_data.get("expires_in")
        expires_at = None
        if expires_in is not None:
            expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=int(expires_in))

        scopes_str = token_data.get("scope", "")
        granted_scopes = [s for s in scopes_str.split(self.scope_separator) if s] if scopes_str else None

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
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier

        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_endpoint, data=data)

        if not response.is_success:
            raise TokenRefreshError(
                f"{self.provider_key} token exchange failed: {response.status_code} {response.text}",
                provider_key=self.provider_key,
            )

        return self._build_stored_credential(response.json())

    async def refresh_token(self, stored: StoredCredential) -> StoredCredential:
        creds = stored.credentials
        if not isinstance(creds, OAuth2Credentials) or not creds.refresh_token:
            raise TokenRefreshError(
                "Cannot refresh: no refresh_token available",
                provider_key=self.provider_key,
            )

        data = {
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_endpoint, data=data)

        if not response.is_success:
            raise TokenRefreshError(
                f"{self.provider_key} token refresh failed: {response.status_code} {response.text}",
                provider_key=self.provider_key,
            )

        token_data = response.json()
        if "refresh_token" not in token_data:
            token_data["refresh_token"] = creds.refresh_token

        updated = self._build_stored_credential(token_data)
        return updated.model_copy(update={
            "granted_scopes": stored.granted_scopes,
            "provider_account_id": stored.provider_account_id,
            "provider_config": stored.provider_config,
        })
