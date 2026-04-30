"""HubSpot OAuth2 configuration."""

from __future__ import annotations

from omnidapter.providers._oauth import OAuthProviderMixin
from omnidapter.providers.hubspot.metadata import HUBSPOT_PROVIDER_KEY


class HubspotOAuthMixin(OAuthProviderMixin):
    provider_key = HUBSPOT_PROVIDER_KEY
    client_id_env_var = "HUBSPOT_CLIENT_ID"
    client_secret_env_var = "HUBSPOT_CLIENT_SECRET"
    token_endpoint = "https://api.hubapi.com/oauth/v1/token"
    authorization_endpoint = "https://app.hubspot.com/oauth/authorize"
    default_scopes = [
        "crm.objects.contacts.read",
        "crm.objects.contacts.write",
        "crm.objects.companies.read",
        "crm.objects.companies.write",
        "crm.objects.deals.read",
        "crm.objects.deals.write",
        "crm.objects.notes.read",
        "crm.objects.notes.write",
    ]
    supports_pkce = False
