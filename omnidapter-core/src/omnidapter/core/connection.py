"""
Connection represents authorization to a provider account.

Services are accessed from a connection.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

from omnidapter.core.metadata import ServiceKind

if TYPE_CHECKING:
    import httpx

    from omnidapter.core.registry import ProviderRegistry
    from omnidapter.services.booking.interface import BookingService
    from omnidapter.services.calendar.interface import CalendarService
    from omnidapter.stores.credentials import StoredCredential
    from omnidapter.transport.hooks import TransportHooks
    from omnidapter.transport.retry import RetryPolicy

_S = TypeVar("_S")


class Connection:
    """Represents an authorized connection to a provider account.

    Services are accessed through a connection:

        conn = await omni.connection("conn_123")
        calendar = conn.calendar()
        await calendar.list_calendars()
    """

    def __init__(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        registry: ProviderRegistry,
        retry_policy: RetryPolicy | None = None,
        hooks: TransportHooks | None = None,
        credential_resolver: Callable[[str], Awaitable[StoredCredential]] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._connection_id = connection_id
        self._stored = stored_credential
        self._registry = registry
        self._retry_policy = retry_policy
        self._hooks = hooks
        self._credential_resolver = credential_resolver
        self._http_client = http_client

    @property
    def connection_id(self) -> str:
        return self._connection_id

    @property
    def provider_key(self) -> str:
        return self._stored.provider_key

    @property
    def stored_credential(self) -> StoredCredential:
        return self._stored

    def supports(self, service: ServiceKind) -> bool:
        """Return True if the provider for this connection supports the given service."""
        provider = self._registry.get(self._stored.provider_key)
        return service in provider.metadata.services

    def _configure_service_runtime(self, service: _S) -> _S:
        service_runtime: Any = service

        if self._credential_resolver is not None:
            service_runtime._credential_resolver = self._credential_resolver

        if self._http_client is not None:
            transport = getattr(service_runtime, "_http", None)
            set_shared_client = getattr(transport, "set_shared_client", None)
            if callable(set_shared_client):
                set_shared_client(self._http_client)

        return service

    @overload
    def service(self, kind: Literal[ServiceKind.CALENDAR]) -> CalendarService: ...

    @overload
    def service(self, kind: Literal[ServiceKind.BOOKING]) -> BookingService: ...

    @overload
    def service(self, kind: ServiceKind) -> Any: ...

    def service(self, kind: ServiceKind) -> Any:
        """Return the service for this connection.

        Raises:
            UnsupportedCapabilityError: If the provider does not support *kind*.
            ServiceAuthorizationError: If the connection was not authorized for *kind*.
            Use ``conn.supports(kind)`` to check provider support first.
        """
        if not self.supports(kind):
            from omnidapter.core.errors import UnsupportedCapabilityError

            raise UnsupportedCapabilityError(
                f"Provider {self._stored.provider_key!r} does not support {kind.value!r}. "
                f"Check conn.supports(ServiceKind.{kind.name}) before calling conn.service().",
                provider_key=self._stored.provider_key,
                capability=kind,
            )
        granted = self._stored.granted_services
        if granted is not None and kind not in granted:
            from omnidapter.core.errors import ServiceAuthorizationError

            raise ServiceAuthorizationError(
                f"Connection was not authorized for service {kind.value!r}. "
                "Re-authorize the connection and request the required service.",
                required_services=[kind.value],
                granted_services=[s.value for s in granted],
            )
        provider = self._registry.get(self._stored.provider_key)
        svc = provider.get_service(
            kind,
            connection_id=self._connection_id,
            stored_credential=self._stored,
            retry_policy=self._retry_policy,
            hooks=self._hooks,
        )
        return self._configure_service_runtime(svc)

    def calendar(self) -> CalendarService:
        """Return the calendar service for this connection.

        Raises:
            UnsupportedCapabilityError: If the provider does not support calendars.
            Use ``conn.supports(ServiceKind.CALENDAR)`` to check first.
        """
        return self.service(ServiceKind.CALENDAR)

    def booking(self) -> BookingService:
        """Return the booking service for this connection.

        Raises:
            UnsupportedCapabilityError: If the provider does not support bookings.
            ScopeInsufficientError: If the connection was not authorized for booking.
            Use ``conn.supports(ServiceKind.BOOKING)`` to check first.
        """
        return self.service(ServiceKind.BOOKING)
