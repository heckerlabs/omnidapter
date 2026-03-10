"""
Omnidapter — main entrypoint and composition root.

Example usage:
    omni = Omnidapter(
        credential_store=my_store,
        oauth_state_store=my_state_store,
    )
    conn = await omni.connection("conn_123")
    calendar = conn.calendar()
    await calendar.list_calendars()
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from omnidapter.auth.locking import ConnectionLockManager
from omnidapter.auth.oauth import OAuthHelper
from omnidapter.auth.refresh import TokenRefreshManager
from omnidapter.core.connection import Connection
from omnidapter.core.errors import ConnectionNotFoundError
from omnidapter.core.logging import get_logger
from omnidapter.core.metadata import ProviderMetadata
from omnidapter.core.registry import ProviderRegistry
from omnidapter.stores.credentials import CredentialStore
from omnidapter.stores.oauth_state import OAuthStateStore
from omnidapter.transport.retry import RetryPolicy

logger = get_logger("omnidapter")


class Omnidapter:
    """Main entrypoint for the Omnidapter library.

    Args:
        credential_store: The app's credential persistence implementation.
        oauth_state_store: The app's OAuth state persistence implementation.
        auto_refresh: Whether to automatically refresh OAuth tokens on service calls.
        retry_policy: HTTP retry policy (default: RetryPolicy.default()).
        on_credentials_updated: Optional callback invoked after credentials are persisted.
            Signature: (connection_id: str, credentials: StoredCredential) -> None.
            May be sync or async.
        register_builtins: Whether to auto-register built-in providers (default: True).
    """

    def __init__(
        self,
        credential_store: CredentialStore,
        oauth_state_store: OAuthStateStore,
        *,
        auto_refresh: bool = True,
        retry_policy: RetryPolicy | None = None,
        on_credentials_updated: Callable | None = None,
        register_builtins: bool = True,
    ) -> None:
        self._credential_store = credential_store
        self._oauth_state_store = oauth_state_store
        self._auto_refresh = auto_refresh
        self._retry_policy = retry_policy or RetryPolicy.default()
        self._on_credentials_updated = on_credentials_updated

        self._registry = ProviderRegistry()
        self._lock_manager = ConnectionLockManager()

        if register_builtins:
            self._registry.register_builtins()

        self._oauth = OAuthHelper(
            registry=self._registry,
            credential_store=self._credential_store,
            oauth_state_store=self._oauth_state_store,
            on_credentials_updated=self._on_credentials_updated,
        )

        self._refresh_manager = TokenRefreshManager(
            registry=self._registry,
            credential_store=self._credential_store,
            lock_manager=self._lock_manager,
            on_credentials_updated=self._on_credentials_updated,
        )

    @property
    def oauth(self) -> OAuthHelper:
        """Access OAuth flow helpers."""
        return self._oauth

    @property
    def registry(self) -> ProviderRegistry:
        """Access the provider registry."""
        return self._registry

    async def connection(self, connection_id: str) -> Connection:
        """Resolve a connection by ID.

        Fetches credentials from the store, validates them, and returns a Connection object.

        Fails fast: raises ConnectionNotFoundError immediately if no credentials exist.

        Args:
            connection_id: The connection identifier.

        Returns:
            A Connection instance.

        Raises:
            ConnectionNotFoundError: If no credentials exist for this connection_id.
        """
        if self._auto_refresh:
            stored = await self._refresh_manager.ensure_fresh(connection_id)
        else:
            stored = await self._credential_store.get_credentials(connection_id)
            if stored is None:
                raise ConnectionNotFoundError(connection_id)

        return Connection(
            connection_id=connection_id,
            stored_credential=stored,
            registry=self._registry,
            retry_policy=self._retry_policy,
        )

    def register_provider(self, provider: Any) -> None:
        """Register a custom provider.

        Args:
            provider: A provider instance implementing BaseProvider.
        """
        self._registry.register(provider)

    def describe_provider(self, provider_key: str) -> ProviderMetadata:
        """Return metadata for a registered provider.

        Args:
            provider_key: The provider key (e.g., "google", "microsoft").

        Returns:
            ProviderMetadata for introspection.
        """
        return self._registry.describe(provider_key)

    def list_providers(self) -> list[str]:
        """Return all registered provider keys."""
        return self._registry.list_keys()
