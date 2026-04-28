"""Jobber OAuth2 configuration."""

from __future__ import annotations

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.jobber.metadata import JOBBER_PROVIDER_KEY


class JobberOAuthMixin(OAuthProviderMixin):
    provider_key = JOBBER_PROVIDER_KEY
    client_id_env_var = "JOBBER_CLIENT_ID"
    client_secret_env_var = "JOBBER_CLIENT_SECRET"
    token_endpoint = "https://api.getjobber.com/api/oauth/token"
    authorization_endpoint = "https://api.getjobber.com/api/oauth/authorize"
    default_scopes = ["read_jobs", "write_jobs", "read_clients", "write_clients"]
    supports_pkce = False
