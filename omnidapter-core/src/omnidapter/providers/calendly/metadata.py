"""Calendly provider metadata."""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.booking.capabilities import BookingCapability

CALENDLY_PROVIDER_KEY = "calendly"

CALENDLY_METADATA = ProviderMetadata(
    provider_key=CALENDLY_PROVIDER_KEY,
    display_name="Calendly",
    services=[ServiceKind.BOOKING],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://auth.calendly.com/oauth/authorize",
        token_endpoint="https://auth.calendly.com/oauth/token",
        supports_pkce=False,
        default_scopes=["default"],
        scope_groups=[
            OAuthScopeGroup(
                name="booking",
                description="Access to Calendly scheduling data",
                scopes=["default"],
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
                BookingCapability.LIST_BOOKINGS,
                BookingCapability.CANCEL_BOOKING,
            ]
        ],
    },
)
