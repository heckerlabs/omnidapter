"""Acuity Scheduling OAuth2 configuration."""

from __future__ import annotations

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.acuity.metadata import ACUITY_PROVIDER_KEY


class AcuityOAuthMixin(OAuthProviderMixin):
    provider_key = ACUITY_PROVIDER_KEY
    client_id_env_var = "ACUITY_CLIENT_ID"
    client_secret_env_var = "ACUITY_CLIENT_SECRET"
    token_endpoint = "https://acuityscheduling.com/oauth2/token"
    authorization_endpoint = "https://acuityscheduling.com/oauth2/authorize"
    default_scopes = ["api-v1"]
    supports_pkce = False
