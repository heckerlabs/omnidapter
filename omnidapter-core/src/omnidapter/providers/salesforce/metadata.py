"""Salesforce provider metadata."""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.crm.capabilities import CrmCapability

SALESFORCE_PROVIDER_KEY = "salesforce"

SALESFORCE_METADATA = ProviderMetadata(
    provider_key=SALESFORCE_PROVIDER_KEY,
    display_name="Salesforce",
    services=[ServiceKind.CRM],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://login.salesforce.com/services/oauth2/authorize",
        token_endpoint="https://login.salesforce.com/services/oauth2/token",
        supports_pkce=False,
        default_scopes=["api", "refresh_token"],
        scope_groups=[
            OAuthScopeGroup(
                name="crm",
                description="Full Salesforce API access",
                scopes=["api", "refresh_token"],
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
                CrmCapability.TAGS,
            ]
        ],
    },
)
