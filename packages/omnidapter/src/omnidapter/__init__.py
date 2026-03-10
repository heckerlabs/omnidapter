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
from omnidapter.core.omnidapter import Omnidapter
from omnidapter.core.errors import (
    OmnidapterError,
    AuthError,
    OAuthStateError,
    TokenRefreshError,
    UnsupportedCapabilityError,
    ConnectionNotFoundError,
    InvalidCredentialFormatError,
    ScopeInsufficientError,
    TransportError,
    ProviderAPIError,
    RateLimitError,
)
from omnidapter.auth.models import OAuth2Credentials, ApiKeyCredentials, BasicCredentials
from omnidapter.stores.credentials import StoredCredential, CredentialStore
from omnidapter.stores.oauth_state import OAuthStateStore
from omnidapter.transport.retry import RetryPolicy
from omnidapter.core.metadata import AuthKind, ServiceKind, ProviderMetadata
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.models import (
    CalendarEvent,
    Calendar,
    AvailabilityResponse,
    Attendee,
    Organizer,
    Recurrence,
    ConferenceData,
)
from omnidapter.services.calendar.requests import (
    CreateEventRequest,
    UpdateEventRequest,
    GetAvailabilityRequest,
)
from omnidapter.services.calendar.pagination import Page

__version__ = "0.1.0"

__all__ = [
    "Omnidapter",
    # Errors
    "OmnidapterError",
    "AuthError",
    "OAuthStateError",
    "TokenRefreshError",
    "UnsupportedCapabilityError",
    "ConnectionNotFoundError",
    "InvalidCredentialFormatError",
    "ScopeInsufficientError",
    "TransportError",
    "ProviderAPIError",
    "RateLimitError",
    # Auth
    "OAuth2Credentials",
    "ApiKeyCredentials",
    "BasicCredentials",
    # Stores
    "StoredCredential",
    "CredentialStore",
    "OAuthStateStore",
    # Transport
    "RetryPolicy",
    # Metadata
    "AuthKind",
    "ServiceKind",
    "ProviderMetadata",
    # Calendar
    "CalendarCapability",
    "CalendarEvent",
    "Calendar",
    "AvailabilityResponse",
    "Attendee",
    "Organizer",
    "Recurrence",
    "ConferenceData",
    "CreateEventRequest",
    "UpdateEventRequest",
    "GetAvailabilityRequest",
    "Page",
    # Version
    "__version__",
]
