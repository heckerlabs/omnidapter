"""
Automatic token refresh logic.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from omnidapter.core.logging import auth_logger

if TYPE_CHECKING:
    from omnidapter.auth.locking import ConnectionLockManager
    from omnidapter.core.registry import ProviderRegistry
    from omnidapter.stores.credentials import CredentialStore, StoredCredential


class TokenRefreshManager:
    """Manages automatic token refresh with per-connection async locking."""

    def __init__(
        self,
        registry: "ProviderRegistry",
        credential_store: "CredentialStore",
        lock_manager: "ConnectionLockManager",
        on_credentials_updated: Any = None,
    ) -> None:
        self._registry = registry
        self._credential_store = credential_store
        self._lock_manager = lock_manager
        self._on_credentials_updated = on_credentials_updated

    async def ensure_fresh(self, connection_id: str) -> "StoredCredential":
        """Ensure credentials are fresh, refreshing if necessary.

        Uses per-connection async lock to prevent concurrent refresh races.

        Returns:
            Fresh StoredCredential.
        """
        from omnidapter.auth.models import OAuth2Credentials
        from omnidapter.core.metadata import AuthKind

        lock = self._lock_manager.get_or_create(connection_id)
        async with lock:
            stored = await self._credential_store.get_credentials(connection_id)
            if stored is None:
                from omnidapter.core.errors import ConnectionNotFoundError
                raise ConnectionNotFoundError(connection_id)

            # Only refresh OAuth2 credentials
            if stored.auth_kind != AuthKind.OAUTH2:
                return stored

            creds = stored.credentials
            if not isinstance(creds, OAuth2Credentials):
                return stored

            if not creds.is_expired():
                return stored

            if not creds.is_refreshable():
                auth_logger.warning(
                    "Token expired but no refresh_token available: connection_id=%r",
                    connection_id,
                )
                return stored

            auth_logger.info("Refreshing token: connection_id=%r", connection_id)

            provider_impl = self._registry.get(stored.provider_key)
            updated = await provider_impl.refresh_token(stored)

            # Persist updated credentials
            await self._credential_store.save_credentials(connection_id, updated)

            # Fire callback
            if self._on_credentials_updated is not None:
                import inspect
                if inspect.iscoroutinefunction(self._on_credentials_updated):
                    await self._on_credentials_updated(connection_id, updated)
                else:
                    self._on_credentials_updated(connection_id, updated)

            auth_logger.info(
                "Token refreshed successfully: connection_id=%r provider=%r",
                connection_id, stored.provider_key,
            )

            return updated
