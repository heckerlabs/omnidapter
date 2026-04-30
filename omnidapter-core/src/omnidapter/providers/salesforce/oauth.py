"""Salesforce OAuth2 configuration."""

from __future__ import annotations

from typing import Any

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.salesforce.metadata import SALESFORCE_PROVIDER_KEY
from omnidapter.stores.credentials import StoredCredential


class SalesforceOAuthMixin(OAuthProviderMixin):
    provider_key = SALESFORCE_PROVIDER_KEY
    client_id_env_var = "SALESFORCE_CLIENT_ID"
    client_secret_env_var = "SALESFORCE_CLIENT_SECRET"
    token_endpoint = "https://login.salesforce.com/services/oauth2/token"
    authorization_endpoint = "https://login.salesforce.com/services/oauth2/authorize"
    default_scopes = ["api", "refresh_token"]
    supports_pkce = False

    def _build_stored_credential(self, token_data: dict[str, Any]) -> StoredCredential:
        stored = super()._build_stored_credential(token_data)
        instance_url = token_data.get("instance_url")
        if instance_url:
            stored = stored.model_copy(update={"provider_config": {"instance_url": instance_url}})
        return stored
