"""Square Appointments provider metadata."""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.booking.capabilities import BookingCapability

SQUARE_PROVIDER_KEY = "square"

SQUARE_METADATA = ProviderMetadata(
    provider_key=SQUARE_PROVIDER_KEY,
    display_name="Square Appointments",
    services=[ServiceKind.BOOKING],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://connect.squareup.com/oauth2/authorize",
        token_endpoint="https://connect.squareup.com/oauth2/token",
        supports_pkce=True,
        default_scopes=[
            "APPOINTMENTS_READ",
            "APPOINTMENTS_WRITE",
            "CUSTOMERS_READ",
            "CUSTOMERS_WRITE",
        ],
        scope_groups=[
            OAuthScopeGroup(
                name="appointments",
                description="Access to Square Appointments booking data",
                scopes=["APPOINTMENTS_READ", "APPOINTMENTS_WRITE"],
                service_kind=ServiceKind.BOOKING,
            ),
            OAuthScopeGroup(
                name="customers",
                description="Access to Square customer records",
                scopes=["CUSTOMERS_READ", "CUSTOMERS_WRITE"],
                service_kind=ServiceKind.BOOKING,
            ),
        ],
    ),
    capabilities={
        ServiceKind.BOOKING.value: [
            c.value
            for c in [
                BookingCapability.LIST_SERVICES,
                BookingCapability.GET_SERVICE,
                BookingCapability.LIST_STAFF,
                BookingCapability.GET_STAFF,
                BookingCapability.LIST_LOCATIONS,
                BookingCapability.GET_AVAILABILITY,
                BookingCapability.CREATE_BOOKING,
                BookingCapability.CANCEL_BOOKING,
                BookingCapability.RESCHEDULE_BOOKING,
                BookingCapability.UPDATE_BOOKING,
                BookingCapability.LIST_BOOKINGS,
                BookingCapability.GET_BOOKING,
                BookingCapability.CUSTOMER_LOOKUP,
                BookingCapability.CUSTOMER_MANAGEMENT,
                BookingCapability.MULTI_LOCATION,
                BookingCapability.MULTI_STAFF,
            ]
        ],
    },
)
