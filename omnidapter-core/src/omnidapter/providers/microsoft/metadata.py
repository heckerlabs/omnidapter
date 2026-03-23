"""
Microsoft Calendar (Graph API) provider metadata.
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

MICROSOFT_PROVIDER_KEY = "microsoft"

MICROSOFT_METADATA = ProviderMetadata(
    provider_key=MICROSOFT_PROVIDER_KEY,
    display_name="Microsoft Calendar",
    services=[ServiceKind.CALENDAR],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_endpoint="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        supports_pkce=True,
        default_scopes=[
            "Calendars.ReadWrite",
            "offline_access",
            "openid",
            "email",
        ],
        scope_groups=[
            OAuthScopeGroup(
                name="calendar",
                description="Read and write access to Microsoft Calendar",
                scopes=["Calendars.ReadWrite", "offline_access"],
            ),
            OAuthScopeGroup(
                name="calendar_readonly",
                description="Read-only access to Microsoft Calendar",
                scopes=["Calendars.Read", "offline_access"],
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
                CalendarCapability.GET_AVAILABILITY,
                CalendarCapability.CREATE_EVENT,
                CalendarCapability.UPDATE_EVENT,
                CalendarCapability.DELETE_EVENT,
                CalendarCapability.GET_EVENT,
                CalendarCapability.LIST_EVENTS,
                CalendarCapability.CONFERENCE_LINKS,
                CalendarCapability.RECURRENCE,
                CalendarCapability.ATTENDEES,
            ]
        ],
    },
)
