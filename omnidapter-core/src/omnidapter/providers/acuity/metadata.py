"""Acuity Scheduling provider metadata."""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.booking.capabilities import BookingCapability

ACUITY_PROVIDER_KEY = "acuity"

ACUITY_METADATA = ProviderMetadata(
    provider_key=ACUITY_PROVIDER_KEY,
    display_name="Acuity Scheduling",
    services=[ServiceKind.BOOKING],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://acuityscheduling.com/oauth2/authorize",
        token_endpoint="https://acuityscheduling.com/oauth2/token",
        supports_pkce=False,
        default_scopes=["api-v1"],
        scope_groups=[
            OAuthScopeGroup(
                name="booking",
                description="Full access to Acuity Scheduling",
                scopes=["api-v1"],
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
                BookingCapability.GET_AVAILABILITY,
                BookingCapability.CREATE_BOOKING,
                BookingCapability.CANCEL_BOOKING,
                BookingCapability.RESCHEDULE_BOOKING,
                BookingCapability.UPDATE_BOOKING,
                BookingCapability.LIST_BOOKINGS,
                BookingCapability.GET_BOOKING,
                BookingCapability.CUSTOMER_LOOKUP,
                BookingCapability.CUSTOMER_MANAGEMENT,
                BookingCapability.MULTI_STAFF,
            ]
        ],
    },
    extra={"rate_limit_per_second": 10},
)
