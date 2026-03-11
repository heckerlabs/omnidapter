"""
In-memory store implementations — suitable for development and single-process deployments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from omnidapter.stores.credentials import CredentialStore, StoredCredential
from omnidapter.stores.oauth_state import OAuthStateStore


class InMemoryCredentialStore(CredentialStore):
    """In-memory credential store.

    Credentials live for the lifetime of the process. Suitable for development,
    single-process deployments, and as a default when no persistence is needed.
    """

    def __init__(self) -> None:
        self._store: dict[str, StoredCredential] = {}

    async def get_credentials(self, connection_id: str) -> StoredCredential | None:
        return self._store.get(connection_id)

    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None:
        self._store[connection_id] = credentials

    async def delete_credentials(self, connection_id: str) -> None:
        self._store.pop(connection_id, None)


class InMemoryOAuthStateStore(OAuthStateStore):
    """In-memory OAuth state store.

    State lives for the lifetime of the process. Suitable for development,
    single-process deployments, and as a default when no persistence is needed.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._expiry: dict[str, datetime] = {}

    async def save_state(
        self,
        state_id: str,
        payload: dict[str, Any],
        expires_at: datetime,
    ) -> None:
        self._store[state_id] = payload
        self._expiry[state_id] = expires_at

    async def load_state(self, state_id: str) -> dict[str, Any] | None:
        expiry = self._expiry.get(state_id)
        if expiry and datetime.now(tz=timezone.utc) > expiry:
            await self.delete_state(state_id)
            return None
        return self._store.get(state_id)

    async def delete_state(self, state_id: str) -> None:
        self._store.pop(state_id, None)
        self._expiry.pop(state_id, None)
