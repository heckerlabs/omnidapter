"""Cal.com OAuth2 configuration."""

from __future__ import annotations

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.calcom.metadata import CALCOM_PROVIDER_KEY


class CalcomOAuthMixin(OAuthProviderMixin):
    provider_key = CALCOM_PROVIDER_KEY
    client_id_env_var = "CALCOM_CLIENT_ID"
    client_secret_env_var = "CALCOM_CLIENT_SECRET"
    token_endpoint = "https://app.cal.com/oauth2/token"
    authorization_endpoint = "https://app.cal.com/oauth2/authorize"
    default_scopes = ["READ_BOOKING", "READ_PROFILE"]
    supports_pkce = True
