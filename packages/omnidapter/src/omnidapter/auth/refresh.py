from __future__ import annotations

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import TokenRefreshError
from omnidapter.core.registry import ProviderRegistry
from omnidapter.stores.credentials import CredentialStore, StoredCredential


class RefreshManager:
    def __init__(self, registry: ProviderRegistry, credential_store: CredentialStore, on_credentials_updated) -> None:
        self._registry = registry
        self._credential_store = credential_store
        self._on_credentials_updated = on_credentials_updated

    async def refresh_if_needed(self, connection_id: str, credential: StoredCredential) -> StoredCredential:
        if not isinstance(credential.credentials, OAuth2Credentials):
            return credential
        if not credential.credentials.is_expired():
            return credential
        adapter = self._registry.get(credential.provider_key).oauth_adapter()
        if adapter is None:
            raise TokenRefreshError(f"Provider {credential.provider_key} cannot refresh tokens")
        refreshed = await adapter.refresh(credential)
        await self._credential_store.save_credentials(connection_id, refreshed)
        if self._on_credentials_updated is not None:
            result = self._on_credentials_updated(connection_id, refreshed)
            if hasattr(result, "__await__"):
                await result
        return refreshed
