"""Housecall Pro provider metadata."""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    ConnectionConfigField,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.crm.capabilities import CrmCapability

HOUSECALLPRO_PROVIDER_KEY = "housecallpro"

HOUSECALLPRO_METADATA = ProviderMetadata(
    provider_key=HOUSECALLPRO_PROVIDER_KEY,
    display_name="Housecall Pro",
    services=[ServiceKind.BOOKING, ServiceKind.CRM],
    auth_kinds=[AuthKind.API_KEY],
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
        ServiceKind.CRM.value: [
            c.value
            for c in [
                CrmCapability.LIST_CONTACTS,
                CrmCapability.GET_CONTACT,
                CrmCapability.CREATE_CONTACT,
                CrmCapability.UPDATE_CONTACT,
                CrmCapability.DELETE_CONTACT,
                CrmCapability.SEARCH_CONTACTS,
                CrmCapability.LIST_ACTIVITIES,
                CrmCapability.CREATE_ACTIVITY,
                CrmCapability.UPDATE_ACTIVITY,
                CrmCapability.DELETE_ACTIVITY,
                CrmCapability.TAGS,
            ]
        ],
    },
    connection_config_fields=[
        ConnectionConfigField(
            name="api_key",
            label="API Key",
            description="Your Housecall Pro API key from Account Settings → Integrations",
            type="password",
            required=True,
        ),
    ],
)
