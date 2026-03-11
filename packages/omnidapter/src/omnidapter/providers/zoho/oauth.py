"""
Zoho OAuth2 configuration.
"""

from __future__ import annotations

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.zoho.metadata import ZOHO_PROVIDER_KEY

ZOHO_TOKEN_ENDPOINT = "https://accounts.zoho.com/oauth/v2/token"


class ZohoOAuthMixin(OAuthProviderMixin):
    provider_key = ZOHO_PROVIDER_KEY
    client_id_env_var = "ZOHO_CLIENT_ID"
    client_secret_env_var = "ZOHO_CLIENT_SECRET"
    token_endpoint = ZOHO_TOKEN_ENDPOINT
    authorization_endpoint = "https://accounts.zoho.com/oauth/v2/auth"
    default_scopes = ["ZohoCalendar.calendar.ALL", "ZohoCalendar.event.ALL"]
    supports_pkce = False
    scope_separator = ","
