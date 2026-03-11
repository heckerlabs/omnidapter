"""
Microsoft OAuth2 (Azure AD) configuration.
"""

from __future__ import annotations

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.microsoft.metadata import MICROSOFT_PROVIDER_KEY

MS_TOKEN_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


class MicrosoftOAuthMixin(OAuthProviderMixin):
    provider_key = MICROSOFT_PROVIDER_KEY
    token_endpoint = MS_TOKEN_ENDPOINT
    authorization_endpoint = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    default_scopes = ["Calendars.ReadWrite", "offline_access", "openid", "email"]
    supports_pkce = True
