"""
Google OAuth2 flow implementation.
"""
from __future__ import annotations

from omnidapter.providers._base import OAuthConfig
from omnidapter.providers._oauth import exchange_code, refresh_oauth_token
from omnidapter.providers.google.metadata import GOOGLE_PROVIDER_KEY
from omnidapter.stores.credentials import StoredCredential

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_google_oauth_config(client_id: str, client_secret: str) -> OAuthConfig:
    return OAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint=GOOGLE_TOKEN_ENDPOINT,
        default_scopes=[
            "https://www.googleapis.com/auth/calendar",
            "openid",
            "email",
        ],
        supports_pkce=True,
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    )


async def exchange_google_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> StoredCredential:
    """Exchange a Google authorization code for tokens."""
    return await exchange_code(
        GOOGLE_PROVIDER_KEY, GOOGLE_TOKEN_ENDPOINT,
        client_id, client_secret, code, redirect_uri, code_verifier,
    )


async def refresh_google_token(
    client_id: str,
    client_secret: str,
    stored: StoredCredential,
) -> StoredCredential:
    """Refresh a Google OAuth2 access token."""
    return await refresh_oauth_token(
        GOOGLE_PROVIDER_KEY, GOOGLE_TOKEN_ENDPOINT,
        client_id, client_secret, stored,
    )
