"""
Automatic token refresh logic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from omnidapter.core.logging import auth_logger

if TYPE_CHECKING:
    from omnidapter.core.registry import ProviderRegistry
    from omnidapter.stores.credentials import CredentialStore, StoredCredential


class TokenRefreshManager:
    """Manages automatic token refresh for OAuth2 credentials."""

    def __init__(
        self,
        registry: ProviderRegistry,
        credential_store: CredentialStore,
        on_credentials_updated: Any = None,
    ) -> None:
        self._registry = registry
        self._credential_store = credential_store
        self._on_credentials_updated = on_credentials_updated

    async def ensure_fresh(self, connection_id: str) -> StoredCredential:
        """Ensure credentials are fresh, refreshing if necessary.

        Returns:
            Fresh StoredCredential.
        """
        from omnidapter.auth.models import OAuth2Credentials
        from omnidapter.core.metadata import AuthKind

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
            result = self._on_credentials_updated(connection_id, updated)
            if inspect.isawaitable(result):
                await result

        auth_logger.info(
            "Token refreshed successfully: connection_id=%r provider=%r",
            connection_id, stored.provider_key,
        )

        return updated
