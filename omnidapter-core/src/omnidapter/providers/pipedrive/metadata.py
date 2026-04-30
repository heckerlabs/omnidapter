"""Pipedrive provider metadata."""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.crm.capabilities import CrmCapability

PIPEDRIVE_PROVIDER_KEY = "pipedrive"

PIPEDRIVE_METADATA = ProviderMetadata(
    provider_key=PIPEDRIVE_PROVIDER_KEY,
    display_name="Pipedrive",
    services=[ServiceKind.CRM],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://oauth.pipedrive.com/oauth/authorize",
        token_endpoint="https://oauth.pipedrive.com/oauth/token",
        supports_pkce=False,
        default_scopes=["contacts:full", "deals:full", "notes:full", "organizations:full"],
        scope_groups=[
            OAuthScopeGroup(
                name="crm",
                description="Access to Pipedrive contacts, organizations, deals, and notes",
                scopes=[
                    "contacts:full",
                    "deals:full",
                    "notes:full",
                    "organizations:full",
                    "activities:full",
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
