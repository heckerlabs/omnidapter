"""
Omnidapter — provider-agnostic async integration library.

Quick start:
    from omnidapter import Omnidapter
    from omnidapter.transport.retry import RetryPolicy

    omni = Omnidapter(
        credential_store=my_store,
        oauth_state_store=my_state_store,
    )
    conn = await omni.connection("conn_123")
    calendar = conn.calendar()

    async for event in calendar.list_events(calendar_id="primary"):
        print(event.summary)
"""

from omnidapter.auth.models import (
    ApiKeyCredentials,
    BaseCredentials,
    BasicCredentials,
    OAuth2Credentials,
)
from omnidapter.core.errors import (
    AuthError,
    ConnectionNotFoundError,
    CustomerResolutionError,
    InvalidCredentialFormatError,
    OAuthStateError,
    OmnidapterError,
    ProviderAPIError,
    ProviderNotConfiguredError,
    RateLimitError,
    ScopeInsufficientError,
    SlotUnavailableError,
    TokenRefreshError,
    TransportError,
    UnsupportedCapabilityError,
)
from omnidapter.core.metadata import AuthKind, ProviderMetadata, ServiceKind
from omnidapter.core.omnidapter import Omnidapter
from omnidapter.core.registry import ProviderRegistry
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.models import (
    AvailabilitySlot,
    Booking,
    BookingCustomer,
    BookingCustomerCreate,
    BookingLocation,
    BookingStatus,
    ServiceType,
    StaffMember,
)
from omnidapter.services.booking.requests import (
    CreateBookingRequest,
    FindCustomerRequest,
    ListBookingsRequest,
    RescheduleBookingRequest,
    UpdateBookingRequest,
)
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.models import (
    Attendee,
    AvailabilityResponse,
    Calendar,
    CalendarEvent,
    ConferenceData,
    EventStatus,
    Organizer,
    Recurrence,
)
from omnidapter.services.calendar.requests import (
    CreateCalendarRequest,
    CreateEventRequest,
    GetAvailabilityRequest,
    UpdateCalendarRequest,
    UpdateEventRequest,
)
from omnidapter.stores.credentials import CredentialStore, StoredCredential
from omnidapter.stores.memory import InMemoryCredentialStore, InMemoryOAuthStateStore
from omnidapter.stores.oauth_state import OAuthStateStore
from omnidapter.transport.retry import RetryPolicy

__version__ = "0.1.0"

__all__ = [
    "Omnidapter",
    # Errors
    "OmnidapterError",
    "AuthError",
    "OAuthStateError",
    "ProviderNotConfiguredError",
    "TokenRefreshError",
    "UnsupportedCapabilityError",
    "ConnectionNotFoundError",
    "InvalidCredentialFormatError",
    "ScopeInsufficientError",
    "SlotUnavailableError",
    "CustomerResolutionError",
    "TransportError",
    "ProviderAPIError",
    "RateLimitError",
    # Auth
    "BaseCredentials",
    "OAuth2Credentials",
    "ApiKeyCredentials",
    "BasicCredentials",
    # Stores
    "StoredCredential",
    "CredentialStore",
    "OAuthStateStore",
    "InMemoryCredentialStore",
    "InMemoryOAuthStateStore",
    # Transport
    "RetryPolicy",
    # Registry
    "ProviderRegistry",
    # Metadata
    "AuthKind",
    "ServiceKind",
    "ProviderMetadata",
    # Booking
    "BookingCapability",
    "BookingStatus",
    "BookingCustomer",
    "BookingCustomerCreate",
    "StaffMember",
    "ServiceType",
    "BookingLocation",
    "AvailabilitySlot",
    "Booking",
    "CreateBookingRequest",
    "UpdateBookingRequest",
    "RescheduleBookingRequest",
    "ListBookingsRequest",
    "FindCustomerRequest",
    # Calendar
    "CalendarCapability",
    "CalendarEvent",
    "EventStatus",
    "Calendar",
    "AvailabilityResponse",
    "Attendee",
    "Organizer",
    "Recurrence",
    "ConferenceData",
    "CreateCalendarRequest",
    "CreateEventRequest",
    "UpdateCalendarRequest",
    "UpdateEventRequest",
    "GetAvailabilityRequest",
    # Version
    "__version__",
]
