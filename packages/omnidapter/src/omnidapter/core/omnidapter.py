from __future__ import annotations

import logging

from omnidapter.auth.locking import ConnectionLockManager
from omnidapter.auth.oauth import OAuthManager
from omnidapter.auth.refresh import RefreshManager
from omnidapter.core.connection import Connection
from omnidapter.core.errors import ConnectionNotFoundError
from omnidapter.core.registry import ProviderRegistry
from omnidapter.providers.caldav.provider import CaldavProvider
from omnidapter.providers.google.provider import GoogleProvider
from omnidapter.providers.microsoft.provider import MicrosoftProvider
from omnidapter.providers.zoho.provider import ZohoProvider
from omnidapter.stores.credentials import CredentialStore
from omnidapter.stores.oauth_state import OAuthStateStore
from omnidapter.transport.retry import RetryPolicy


class Omnidapter:
    def __init__(
        self,
        credential_store: CredentialStore,
        oauth_state_store: OAuthStateStore,
        auto_refresh: bool = True,
        retry_policy: RetryPolicy | None = None,
        on_credentials_updated=None,
        register_builtin: bool = True,
    ) -> None:
        self._logger = logging.getLogger("omnidapter")
        self._credential_store = credential_store
        self._auto_refresh = auto_refresh
        self.retry_policy = retry_policy or RetryPolicy.default()
        self.registry = ProviderRegistry()
        if register_builtin:
            for p in (GoogleProvider(), MicrosoftProvider(), CaldavProvider(), ZohoProvider()):
                self.registry.register(p)
                self._logger.info("Registered provider %s", p.key)
        self._locks = ConnectionLockManager()
        self._refresh = RefreshManager(self.registry, credential_store, on_credentials_updated)
        self.oauth = OAuthManager(self.registry, credential_store, oauth_state_store, on_credentials_updated)

    async def connection(self, connection_id: str) -> Connection:
        stored = await self._credential_store.get_credentials(connection_id)
        if stored is None:
            raise ConnectionNotFoundError(connection_id)
        return Connection(
            connection_id=connection_id,
            credential=stored,
            registry=self.registry,
            refresh_manager=self._refresh,
            locks=self._locks,
            auto_refresh=self._auto_refresh,
        )

    def describe_provider(self, provider_key: str):
        return self.registry.describe(provider_key)
