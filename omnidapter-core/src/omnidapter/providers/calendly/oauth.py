"""Calendly OAuth2 configuration."""

from __future__ import annotations

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.calendly.metadata import CALENDLY_PROVIDER_KEY


class CalendlyOAuthMixin(OAuthProviderMixin):
    provider_key = CALENDLY_PROVIDER_KEY
    client_id_env_var = "CALENDLY_CLIENT_ID"
    client_secret_env_var = "CALENDLY_CLIENT_SECRET"
    token_endpoint = "https://auth.calendly.com/oauth/token"
    authorization_endpoint = "https://auth.calendly.com/oauth/authorize"
    default_scopes = ["default"]
    supports_pkce = False
