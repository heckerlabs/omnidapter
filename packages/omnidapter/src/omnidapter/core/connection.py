from __future__ import annotations

from omnidapter.auth.locking import ConnectionLockManager
from omnidapter.auth.refresh import RefreshManager
from omnidapter.core.errors import ProviderAPIError
from omnidapter.core.registry import ProviderRegistry
from omnidapter.stores.credentials import StoredCredential


class Connection:
    def __init__(
        self,
        connection_id: str,
        credential: StoredCredential,
        registry: ProviderRegistry,
        refresh_manager: RefreshManager,
        locks: ConnectionLockManager,
        auto_refresh: bool,
    ) -> None:
        self.connection_id = connection_id
        self.credential = credential
        self._registry = registry
        self._refresh_manager = refresh_manager
        self._locks = locks
        self._auto_refresh = auto_refresh

    async def _resolve_credential(self) -> StoredCredential:
        if not self._auto_refresh:
            return self.credential
        lock = self._locks.for_connection(self.connection_id)
        async with lock:
            self.credential = await self._refresh_manager.refresh_if_needed(self.connection_id, self.credential)
            return self.credential

    async def call_with_refresh_retry(self, fn):
        await self._resolve_credential()
        try:
            return await fn()
        except ProviderAPIError as exc:
            if exc.status_code != 401 or not self._auto_refresh:
                raise
            lock = self._locks.for_connection(self.connection_id)
            async with lock:
                self.credential = await self._refresh_manager.refresh_if_needed(self.connection_id, self.credential)
            return await fn()

    def calendar(self):
        provider = self._registry.get(self.credential.provider_key)
        base = provider.calendar_service(self.connection_id, self.credential)
        parent = self

        class CalendarProxy:
            async def __getattr__(self, name):  # pragma: no cover
                return getattr(base, name)

            async def list_calendars(self):
                return await parent.call_with_refresh_retry(base.list_calendars)

            async def get_availability(self, calendar_id: str):
                return await parent.call_with_refresh_retry(lambda: base.get_availability(calendar_id))

            async def create_event(self, payload):
                return await parent.call_with_refresh_retry(lambda: base.create_event(payload))

            async def update_event(self, event_id: str, payload):
                return await parent.call_with_refresh_retry(lambda: base.update_event(event_id, payload))

            async def delete_event(self, event_id: str):
                return await parent.call_with_refresh_retry(lambda: base.delete_event(event_id))

            async def get_event(self, event_id: str):
                return await parent.call_with_refresh_retry(lambda: base.get_event(event_id))

            async def list_events_page(self, calendar_id: str, page_token: str | None = None):
                return await parent.call_with_refresh_retry(lambda: base.list_events_page(calendar_id, page_token))

            async def list_events(self, calendar_id: str):
                page_token = None
                while True:
                    page = await self.list_events_page(calendar_id, page_token)
                    for item in page.items:
                        yield item
                    if not page.next_page_token:
                        break
                    page_token = page.next_page_token

        return CalendarProxy()
