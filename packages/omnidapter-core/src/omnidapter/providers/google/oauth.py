"""
Google OAuth2 configuration.
"""

from __future__ import annotations

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.google.metadata import GOOGLE_PROVIDER_KEY

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleOAuthMixin(OAuthProviderMixin):
    provider_key = GOOGLE_PROVIDER_KEY
    client_id_env_var = "GOOGLE_CLIENT_ID"
    client_secret_env_var = "GOOGLE_CLIENT_SECRET"
    token_endpoint = GOOGLE_TOKEN_ENDPOINT
    authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    default_scopes = [
        "https://www.googleapis.com/auth/calendar",
        "openid",
        "email",
    ]
    supports_pkce = True
    extra_auth_params = {"access_type": "offline", "prompt": "consent"}
