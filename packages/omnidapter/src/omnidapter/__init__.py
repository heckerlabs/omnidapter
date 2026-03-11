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
    InvalidCredentialFormatError,
    OAuthStateError,
    OmnidapterError,
    ProviderAPIError,
    RateLimitError,
    ScopeInsufficientError,
    TokenRefreshError,
    TransportError,
    UnsupportedCapabilityError,
)
from omnidapter.core.metadata import AuthKind, ProviderMetadata, ServiceKind
from omnidapter.core.omnidapter import Omnidapter
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.models import (
    Attendee,
    AvailabilityResponse,
    Calendar,
    CalendarEvent,
    ConferenceData,
    Organizer,
    Recurrence,
)
from omnidapter.services.calendar.pagination import Page
from omnidapter.services.calendar.requests import (
    CreateEventRequest,
    GetAvailabilityRequest,
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
    "TokenRefreshError",
    "UnsupportedCapabilityError",
    "ConnectionNotFoundError",
    "InvalidCredentialFormatError",
    "ScopeInsufficientError",
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
