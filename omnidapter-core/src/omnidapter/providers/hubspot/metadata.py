"""HubSpot provider metadata."""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.crm.capabilities import CrmCapability

HUBSPOT_PROVIDER_KEY = "hubspot"

HUBSPOT_METADATA = ProviderMetadata(
    provider_key=HUBSPOT_PROVIDER_KEY,
    display_name="HubSpot",
    services=[ServiceKind.CRM],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://app.hubspot.com/oauth/authorize",
        token_endpoint="https://api.hubapi.com/oauth/v1/token",
        supports_pkce=False,
        default_scopes=[
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "crm.objects.companies.read",
            "crm.objects.companies.write",
            "crm.objects.deals.read",
            "crm.objects.deals.write",
            "crm.objects.notes.read",
            "crm.objects.notes.write",
        ],
        scope_groups=[
            OAuthScopeGroup(
                name="crm",
                description="Access to HubSpot CRM contacts, companies, deals, and notes",
                scopes=[
                    "crm.objects.contacts.read",
                    "crm.objects.contacts.write",
                    "crm.objects.companies.read",
                    "crm.objects.companies.write",
                    "crm.objects.deals.read",
                    "crm.objects.deals.write",
                    "crm.objects.notes.read",
                    "crm.objects.notes.write",
                ],
                service_kind=ServiceKind.CRM,
            ),
        ],
    ),
    capabilities={
        ServiceKind.CRM.value: [
            c.value
            for c in [
                CrmCapability.LIST_CONTACTS,
                CrmCapability.GET_CONTACT,
                CrmCapability.CREATE_CONTACT,
                CrmCapability.UPDATE_CONTACT,
                CrmCapability.DELETE_CONTACT,
                CrmCapability.SEARCH_CONTACTS,
                CrmCapability.LIST_COMPANIES,
                CrmCapability.GET_COMPANY,
                CrmCapability.CREATE_COMPANY,
                CrmCapability.UPDATE_COMPANY,
                CrmCapability.DELETE_COMPANY,
                CrmCapability.LIST_DEALS,
                CrmCapability.GET_DEAL,
                CrmCapability.CREATE_DEAL,
                CrmCapability.UPDATE_DEAL,
                CrmCapability.DELETE_DEAL,
                CrmCapability.LIST_ACTIVITIES,
                CrmCapability.CREATE_ACTIVITY,
                CrmCapability.UPDATE_ACTIVITY,
                CrmCapability.DELETE_ACTIVITY,
            ]
        ],
    },
)
