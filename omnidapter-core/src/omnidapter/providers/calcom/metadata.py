"""Cal.com provider metadata."""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.booking.capabilities import BookingCapability

CALCOM_PROVIDER_KEY = "calcom"

CALCOM_METADATA = ProviderMetadata(
    provider_key=CALCOM_PROVIDER_KEY,
    display_name="Cal.com",
    services=[ServiceKind.BOOKING],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://app.cal.com/oauth2/authorize",
        token_endpoint="https://app.cal.com/oauth2/token",
        supports_pkce=True,
        default_scopes=["READ_BOOKING", "READ_PROFILE"],
        scope_groups=[
            OAuthScopeGroup(
                name="booking_read",
                description="Read access to Cal.com bookings and event types",
                scopes=["READ_BOOKING", "READ_PROFILE"],
                service_kind=ServiceKind.BOOKING,
            ),
            OAuthScopeGroup(
                name="booking_write",
                description="Write access to Cal.com bookings",
                scopes=["WRITE_BOOKING"],
                service_kind=ServiceKind.BOOKING,
            ),
        ],
    ),
    capabilities={
        ServiceKind.BOOKING.value: [
            c.value
            for c in [
                BookingCapability.LIST_SERVICES,
                BookingCapability.LIST_STAFF,
                BookingCapability.GET_AVAILABILITY,
                BookingCapability.CREATE_BOOKING,
                BookingCapability.CANCEL_BOOKING,
                BookingCapability.RESCHEDULE_BOOKING,
                BookingCapability.UPDATE_BOOKING,
                BookingCapability.LIST_BOOKINGS,
                BookingCapability.MULTI_LOCATION,
                BookingCapability.MULTI_STAFF,
                BookingCapability.MULTI_SERVICE,
            ]
        ],
    },
)
