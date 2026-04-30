"""Pipedrive OAuth2 configuration."""

from __future__ import annotations

from typing import Any

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.pipedrive.metadata import PIPEDRIVE_PROVIDER_KEY
from omnidapter.stores.credentials import StoredCredential


class PipedriveOAuthMixin(OAuthProviderMixin):
    provider_key = PIPEDRIVE_PROVIDER_KEY
    client_id_env_var = "PIPEDRIVE_CLIENT_ID"
    client_secret_env_var = "PIPEDRIVE_CLIENT_SECRET"
    token_endpoint = "https://oauth.pipedrive.com/oauth/token"
    authorization_endpoint = "https://oauth.pipedrive.com/oauth/authorize"
    default_scopes = ["contacts:full", "deals:full", "notes:full", "organizations:full"]
    supports_pkce = False

    def _build_stored_credential(self, token_data: dict[str, Any]) -> StoredCredential:
        stored = super()._build_stored_credential(token_data)
        api_domain = token_data.get("api_domain")
        if api_domain:
            stored = stored.model_copy(update={"provider_config": {"api_domain": api_domain}})
        return stored
