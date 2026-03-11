"""
Shared OAuth2 utilities for provider implementations.

All standard authorization-code + refresh-token flows are implemented here.
Provider oauth.py modules call these helpers, passing only what differs:
provider_key, token_endpoint, and (for Zoho) a comma scope_separator.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import TokenRefreshError
from omnidapter.core.metadata import AuthKind
from omnidapter.stores.credentials import StoredCredential


def build_stored_credential(
    token_data: dict[str, Any],
    provider_key: str,
    scope_separator: str = " ",
) -> StoredCredential:
    """Build a StoredCredential from a standard OAuth2 token response."""
    expires_in = token_data.get("expires_in")
    expires_at = None
    if expires_in is not None:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=int(expires_in))

    scopes_str = token_data.get("scope", "")
    granted_scopes = [s for s in scopes_str.split(scope_separator) if s] if scopes_str else None

    creds = OAuth2Credentials(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_type=token_data.get("token_type", "Bearer"),
        expires_at=expires_at,
        id_token=token_data.get("id_token"),
        raw=token_data,
    )

    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.OAUTH2,
        credentials=creds,
        granted_scopes=granted_scopes,
    )


async def exchange_code(
    provider_key: str,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
    scope_separator: str = " ",
) -> StoredCredential:
    """Exchange an authorization code for tokens."""
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    async with httpx.AsyncClient() as client:
        response = await client.post(token_endpoint, data=data)

    if not response.is_success:
        raise TokenRefreshError(
            f"{provider_key} token exchange failed: {response.status_code} {response.text}",
            provider_key=provider_key,
        )

    return build_stored_credential(response.json(), provider_key, scope_separator)


async def refresh_oauth_token(
    provider_key: str,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    stored: StoredCredential,
    scope_separator: str = " ",
) -> StoredCredential:
    """Refresh an OAuth2 access token using the stored refresh token."""
    creds = stored.credentials
    if not isinstance(creds, OAuth2Credentials) or not creds.refresh_token:
        raise TokenRefreshError(
            "Cannot refresh: no refresh_token available",
            provider_key=provider_key,
        )

    data = {
        "grant_type": "refresh_token",
        "refresh_token": creds.refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_endpoint, data=data)

    if not response.is_success:
        raise TokenRefreshError(
            f"{provider_key} token refresh failed: {response.status_code} {response.text}",
            provider_key=provider_key,
        )

    token_data = response.json()
    if "refresh_token" not in token_data:
        token_data["refresh_token"] = creds.refresh_token

    updated = build_stored_credential(token_data, provider_key, scope_separator)
    return updated.model_copy(update={
        "granted_scopes": stored.granted_scopes,
        "provider_account_id": stored.provider_account_id,
        "provider_config": stored.provider_config,
    })
