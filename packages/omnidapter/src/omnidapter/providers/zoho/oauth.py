"""
Zoho OAuth2 flow implementation.
"""
from __future__ import annotations

from omnidapter.providers._base import OAuthConfig
from omnidapter.providers._oauth import exchange_code, refresh_oauth_token
from omnidapter.providers.zoho.metadata import ZOHO_PROVIDER_KEY
from omnidapter.stores.credentials import StoredCredential

ZOHO_TOKEN_ENDPOINT = "https://accounts.zoho.com/oauth/v2/token"

_SCOPE_SEP = ","


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
    return await exchange_code(
        ZOHO_PROVIDER_KEY, ZOHO_TOKEN_ENDPOINT,
        client_id, client_secret, code, redirect_uri, code_verifier,
        scope_separator=_SCOPE_SEP,
    )


async def refresh_zoho_token(
    client_id: str,
    client_secret: str,
    stored: StoredCredential,
) -> StoredCredential:
    return await refresh_oauth_token(
        ZOHO_PROVIDER_KEY, ZOHO_TOKEN_ENDPOINT,
        client_id, client_secret, stored,
        scope_separator=_SCOPE_SEP,
    )
