from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from omnidapter.auth.kinds import AuthKind
from omnidapter.auth.models import OAuthBeginResult, OAuthStatePayload
from omnidapter.core.errors import OAuthStateError
from omnidapter.core.registry import ProviderRegistry
from omnidapter.stores.credentials import CredentialStore, StoredCredential
from omnidapter.stores.oauth_state import OAuthStateStore


class OAuthManager:
    def __init__(
        self,
        registry: ProviderRegistry,
        credential_store: CredentialStore,
        state_store: OAuthStateStore,
        on_credentials_updated,
    ) -> None:
        self._registry = registry
        self._credential_store = credential_store
        self._state_store = state_store
        self._on_credentials_updated = on_credentials_updated

    async def begin(self, provider: str, connection_id: str, redirect_uri: str) -> OAuthBeginResult:
        state = secrets.token_urlsafe(24)
        code_verifier = secrets.token_urlsafe(48)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=10)
        payload = OAuthStatePayload(
            provider=provider,
            connection_id=connection_id,
            code_verifier=code_verifier,
            created_at=now,
        )
        await self._state_store.save_state(state, payload, expires_at)
        adapter = self._registry.get(provider).oauth_adapter()
        if adapter is None:
            raise OAuthStateError(f"Provider {provider} does not support OAuth")
        url = await adapter.build_authorization_url(connection_id, state, redirect_uri, code_verifier)
        return OAuthBeginResult(authorization_url=url, state=state, expires_at=expires_at)

    async def complete(self, provider: str, connection_id: str, code: str, state: str, redirect_uri: str) -> StoredCredential:
        payload = await self._state_store.load_state(state)
        if payload is None:
            raise OAuthStateError("Unknown OAuth state")
        if payload.provider != provider or payload.connection_id != connection_id:
            raise OAuthStateError("OAuth state mismatch")
        adapter = self._registry.get(provider).oauth_adapter()
        if adapter is None:
            raise OAuthStateError(f"Provider {provider} does not support OAuth")
        token_result = await adapter.exchange_code(code, redirect_uri, payload.code_verifier)
        stored = StoredCredential(
            provider_key=provider,
            auth_kind=AuthKind.OAUTH2,
            credentials=token_result.credentials,
            granted_scopes=token_result.granted_scopes,
            provider_account_id=token_result.provider_account_id,
        )
        await self._credential_store.save_credentials(connection_id, stored)
        if self._on_credentials_updated is not None:
            result = self._on_credentials_updated(connection_id, stored)
            if hasattr(result, "__await__"):
                await result
        await self._state_store.delete_state(state)
        return stored
