"""
Zoho OAuth2 flow implementation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import TokenRefreshError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers._base import OAuthConfig
from omnidapter.providers.zoho.metadata import ZOHO_PROVIDER_KEY
from omnidapter.stores.credentials import StoredCredential

ZOHO_TOKEN_ENDPOINT = "https://accounts.zoho.com/oauth/v2/token"


def build_zoho_oauth_config(client_id: str, client_secret: str) -> OAuthConfig:
    return OAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        authorization_endpoint="https://accounts.zoho.com/oauth/v2/auth",
        token_endpoint=ZOHO_TOKEN_ENDPOINT,
        default_scopes=["ZohoCalendar.calendar.ALL", "ZohoCalendar.event.ALL"],
        supports_pkce=False,
    )


async def exchange_zoho_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> StoredCredential:
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(ZOHO_TOKEN_ENDPOINT, data=data)

    if not response.is_success:
        raise TokenRefreshError(
            f"Zoho token exchange failed: {response.status_code} {response.text}",
            provider_key=ZOHO_PROVIDER_KEY,
        )

    return _build_stored_credential(response.json())


async def refresh_zoho_token(
    client_id: str,
    client_secret: str,
    stored: StoredCredential,
) -> StoredCredential:
    from omnidapter.auth.models import OAuth2Credentials
    creds = stored.credentials
    if not isinstance(creds, OAuth2Credentials) or not creds.refresh_token:
        raise TokenRefreshError(
            "Cannot refresh: no refresh_token available",
            provider_key=ZOHO_PROVIDER_KEY,
        )

    data = {
        "grant_type": "refresh_token",
        "refresh_token": creds.refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(ZOHO_TOKEN_ENDPOINT, data=data)

    if not response.is_success:
        raise TokenRefreshError(
            f"Zoho token refresh failed: {response.status_code} {response.text}",
            provider_key=ZOHO_PROVIDER_KEY,
        )

    token_data = response.json()
    if "refresh_token" not in token_data:
        token_data["refresh_token"] = creds.refresh_token

    updated = _build_stored_credential(token_data)
    return updated.model_copy(update={
        "granted_scopes": stored.granted_scopes,
        "provider_account_id": stored.provider_account_id,
        "provider_config": stored.provider_config,
    })


def _build_stored_credential(token_data: dict[str, Any]) -> StoredCredential:
    expires_in = token_data.get("expires_in")
    expires_at = None
    if expires_in is not None:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=int(expires_in))

    scopes_str = token_data.get("scope", "")
    granted_scopes = [s for s in scopes_str.split(",") if s] if scopes_str else None

    creds = OAuth2Credentials(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_type=token_data.get("token_type", "Bearer"),
        expires_at=expires_at,
        raw=token_data,
    )

    return StoredCredential(
        provider_key=ZOHO_PROVIDER_KEY,
        auth_kind=AuthKind.OAUTH2,
        credentials=creds,
        granted_scopes=granted_scopes,
    )
