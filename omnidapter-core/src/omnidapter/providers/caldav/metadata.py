"""
CalDAV provider metadata.
"""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    ConnectionConfigField,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.calendar.capabilities import CalendarCapability

CALDAV_PROVIDER_KEY = "caldav"

CALDAV_METADATA = ProviderMetadata(
    provider_key=CALDAV_PROVIDER_KEY,
    display_name="CalDAV",
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
            name="server_url",
            label="Server URL",
            description="Your CalDAV server address",
            type="url",
            required=True,
            placeholder="https://caldav.example.com/",
            example="https://caldav.fastmail.com/dav/",
        ),
        ConnectionConfigField(
            name="username",
            label="Username",
            description="Your CalDAV username or email address",
            type="text",
            required=True,
        ),
        ConnectionConfigField(
            name="password",
            label="Password",
            description="Use an app-specific password if available",
            type="password",
            required=True,
        ),
    ],
)
