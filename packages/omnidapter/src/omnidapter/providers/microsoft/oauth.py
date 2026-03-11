"""
Microsoft OAuth2 (Azure AD) flow implementation.
"""
from __future__ import annotations

from omnidapter.providers._base import OAuthConfig
from omnidapter.providers._oauth import exchange_code, refresh_oauth_token
from omnidapter.providers.microsoft.metadata import MICROSOFT_PROVIDER_KEY
from omnidapter.stores.credentials import StoredCredential

MS_TOKEN_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


def build_microsoft_oauth_config(client_id: str, client_secret: str) -> OAuthConfig:
    return OAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        authorization_endpoint="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_endpoint=MS_TOKEN_ENDPOINT,
        default_scopes=["Calendars.ReadWrite", "offline_access", "openid", "email"],
        supports_pkce=True,
    )


async def exchange_microsoft_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> StoredCredential:
    return await exchange_code(
        MICROSOFT_PROVIDER_KEY, MS_TOKEN_ENDPOINT,
        client_id, client_secret, code, redirect_uri, code_verifier,
    )


async def refresh_microsoft_token(
    client_id: str,
    client_secret: str,
    stored: StoredCredential,
) -> StoredCredential:
    return await refresh_oauth_token(
        MICROSOFT_PROVIDER_KEY, MS_TOKEN_ENDPOINT,
        client_id, client_secret, stored,
    )
