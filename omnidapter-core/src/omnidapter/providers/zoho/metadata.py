"""
Zoho provider metadata (Calendar + Bookings).
"""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.calendar.capabilities import CalendarCapability

ZOHO_PROVIDER_KEY = "zoho"

ZOHO_METADATA = ProviderMetadata(
    provider_key=ZOHO_PROVIDER_KEY,
    display_name="Zoho",
    services=[ServiceKind.CALENDAR, ServiceKind.BOOKING],
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
                service_kind=ServiceKind.CALENDAR,
            ),
            OAuthScopeGroup(
                name="bookings",
                description="Full access to Zoho Bookings",
                scopes=["zohobookings.data.CREATE"],
                service_kind=ServiceKind.BOOKING,
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
        ServiceKind.BOOKING.value: [
            c.value
            for c in [
                BookingCapability.LIST_SERVICES,
                BookingCapability.GET_SERVICE,
                BookingCapability.LIST_STAFF,
                BookingCapability.GET_STAFF,
                BookingCapability.GET_AVAILABILITY,
                BookingCapability.CREATE_BOOKING,
                BookingCapability.CANCEL_BOOKING,
                BookingCapability.RESCHEDULE_BOOKING,
                BookingCapability.UPDATE_BOOKING,
                BookingCapability.LIST_BOOKINGS,
                BookingCapability.GET_BOOKING,
                BookingCapability.CUSTOMER_LOOKUP,
            ]
        ],
    },
)
