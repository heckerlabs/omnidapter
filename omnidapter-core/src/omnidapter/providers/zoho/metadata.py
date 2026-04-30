"""
Zoho provider metadata (Calendar + CRM).
"""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.crm.capabilities import CrmCapability

ZOHO_PROVIDER_KEY = "zoho"

ZOHO_METADATA = ProviderMetadata(
    provider_key=ZOHO_PROVIDER_KEY,
    display_name="Zoho",
    services=[ServiceKind.CALENDAR, ServiceKind.CRM],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://accounts.zoho.com/oauth/v2/auth",
        token_endpoint="https://accounts.zoho.com/oauth/v2/token",
        supports_pkce=False,
        default_scopes=["ZohoCalendar.calendar.ALL", "ZohoCalendar.event.ALL"],
        scope_groups=[
            OAuthScopeGroup(
                name="calendar",
                description="Full access to Zoho Calendar",
                scopes=["ZohoCalendar.calendar.ALL", "ZohoCalendar.event.ALL"],
            ),
            OAuthScopeGroup(
                name="crm",
                description="Full access to Zoho CRM",
                scopes=["ZohoCRM.modules.ALL", "ZohoCRM.settings.ALL"],
                service_kind=ServiceKind.CRM,
            ),
        ],
    ),
    capabilities={
        ServiceKind.CALENDAR.value: [
            c.value
            for c in [
                CalendarCapability.LIST_CALENDARS,
                CalendarCapability.GET_CALENDAR,
                CalendarCapability.CREATE_CALENDAR,
                CalendarCapability.UPDATE_CALENDAR,
                CalendarCapability.DELETE_CALENDAR,
                CalendarCapability.CREATE_EVENT,
                CalendarCapability.UPDATE_EVENT,
                CalendarCapability.DELETE_EVENT,
                CalendarCapability.GET_EVENT,
                CalendarCapability.LIST_EVENTS,
                CalendarCapability.ATTENDEES,
            ]
        ],
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
