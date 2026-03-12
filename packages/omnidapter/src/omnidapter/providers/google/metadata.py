"""
Google Calendar provider metadata.
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

GOOGLE_PROVIDER_KEY = "google"

GOOGLE_METADATA = ProviderMetadata(
    provider_key=GOOGLE_PROVIDER_KEY,
    display_name="Google Calendar",
    services=[ServiceKind.CALENDAR],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        supports_pkce=True,
        default_scopes=[
            "https://www.googleapis.com/auth/calendar",
            "openid",
            "email",
        ],
        scope_groups=[
            OAuthScopeGroup(
                name="calendar",
                description="Full access to Google Calendar",
                scopes=["https://www.googleapis.com/auth/calendar"],
            ),
            OAuthScopeGroup(
                name="calendar_readonly",
                description="Read-only access to Google Calendar",
                scopes=["https://www.googleapis.com/auth/calendar.readonly"],
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
