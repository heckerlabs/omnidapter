"""
Connection represents authorization to a provider account.

Services are accessed from a connection.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omnidapter.core.registry import ProviderRegistry
    from omnidapter.services.calendar.interface import CalendarService
    from omnidapter.stores.credentials import StoredCredential
    from omnidapter.transport.hooks import TransportHooks
    from omnidapter.transport.retry import RetryPolicy


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
    ) -> None:
        self._connection_id = connection_id
        self._stored = stored_credential
        self._registry = registry
        self._retry_policy = retry_policy
        self._hooks = hooks

    @property
    def connection_id(self) -> str:
        return self._connection_id

    @property
    def provider_key(self) -> str:
        return self._stored.provider_key

    @property
    def stored_credential(self) -> StoredCredential:
        return self._stored

    def calendar(self) -> CalendarService:
        """Return the calendar service for this connection.

        Raises:
            KeyError: If the provider is not registered.
        """
        provider = self._registry.get(self._stored.provider_key)
        return provider.get_calendar_service(
            connection_id=self._connection_id,
            stored_credential=self._stored,
            retry_policy=self._retry_policy,
            hooks=self._hooks,
        )
