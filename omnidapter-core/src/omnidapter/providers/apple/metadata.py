"""
Apple Calendar (iCloud CalDAV) provider metadata.
"""

from __future__ import annotations

from omnidapter.core.metadata import AuthKind, ConnectionConfigField, ProviderMetadata, ServiceKind
from omnidapter.services.calendar.capabilities import CalendarCapability

APPLE_PROVIDER_KEY = "apple"

APPLE_METADATA = ProviderMetadata(
    provider_key=APPLE_PROVIDER_KEY,
    display_name="Apple Calendar",
    services=[ServiceKind.CALENDAR],
    auth_kinds=[AuthKind.BASIC],
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
                CalendarCapability.RECURRENCE,
                CalendarCapability.ATTENDEES,
            ]
        ],
    },
    connection_config_fields=[
        ConnectionConfigField(
            name="username",
            label="Apple ID Email",
            description="Your Apple ID email address",
            type="email",
            required=True,
        ),
        ConnectionConfigField(
            name="password",
            label="App-Specific Password",
            description="Generate an app-specific password from your Apple ID security settings",
            type="password",
            required=True,
        ),
    ],
)
