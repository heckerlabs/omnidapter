"""Jobber provider metadata."""

from __future__ import annotations

from omnidapter.core.metadata import (
    AuthKind,
    OAuthMetadata,
    OAuthScopeGroup,
    ProviderMetadata,
    ServiceKind,
)
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.crm.capabilities import CrmCapability

JOBBER_PROVIDER_KEY = "jobber"

JOBBER_METADATA = ProviderMetadata(
    provider_key=JOBBER_PROVIDER_KEY,
    display_name="Jobber",
    services=[ServiceKind.BOOKING, ServiceKind.CRM],
    auth_kinds=[AuthKind.OAUTH2],
    oauth=OAuthMetadata(
        authorization_endpoint="https://api.getjobber.com/api/oauth/authorize",
        token_endpoint="https://api.getjobber.com/api/oauth/token",
        supports_pkce=False,
        default_scopes=["read_jobs", "write_jobs", "read_clients", "write_clients"],
        scope_groups=[
            OAuthScopeGroup(
                name="jobs",
                description="Access to Jobber jobs and scheduling",
                scopes=["read_jobs", "write_jobs"],
                service_kind=ServiceKind.BOOKING,
            ),
            OAuthScopeGroup(
                name="clients",
                description="Access to Jobber client records",
                scopes=["read_clients", "write_clients"],
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
        ServiceKind.CRM.value: [
            c.value
            for c in [
                CrmCapability.LIST_CONTACTS,
                CrmCapability.GET_CONTACT,
                CrmCapability.CREATE_CONTACT,
                CrmCapability.UPDATE_CONTACT,
                CrmCapability.DELETE_CONTACT,
                CrmCapability.SEARCH_CONTACTS,
                CrmCapability.LIST_COMPANIES,
                CrmCapability.GET_COMPANY,
                CrmCapability.CREATE_COMPANY,
                CrmCapability.UPDATE_COMPANY,
                CrmCapability.LIST_ACTIVITIES,
                CrmCapability.CREATE_ACTIVITY,
                CrmCapability.UPDATE_ACTIVITY,
                CrmCapability.DELETE_ACTIVITY,
            ]
        ],
    },
    extra={"transport": "graphql"},
)
