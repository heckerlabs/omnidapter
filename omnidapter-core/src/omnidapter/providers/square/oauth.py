"""Square OAuth2 configuration."""

from __future__ import annotations

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.square.metadata import SQUARE_PROVIDER_KEY


class SquareOAuthMixin(OAuthProviderMixin):
    provider_key = SQUARE_PROVIDER_KEY
    client_id_env_var = "SQUARE_CLIENT_ID"
    client_secret_env_var = "SQUARE_CLIENT_SECRET"
    token_endpoint = "https://connect.squareup.com/oauth2/token"
    authorization_endpoint = "https://connect.squareup.com/oauth2/authorize"
    default_scopes = [
        "APPOINTMENTS_READ",
        "APPOINTMENTS_WRITE",
        "CUSTOMERS_READ",
        "CUSTOMERS_WRITE",
    ]
    supports_pkce = True
