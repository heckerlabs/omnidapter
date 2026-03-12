"""
In-memory store implementations for testing — extends the real implementations
with test helpers like seed().
"""

from __future__ import annotations

from omnidapter.stores.credentials import StoredCredential
from omnidapter.stores.memory import InMemoryCredentialStore as _InMemoryCredentialStore
from omnidapter.stores.memory import InMemoryOAuthStateStore


class InMemoryCredentialStore(_InMemoryCredentialStore):
    """In-memory credential store with test helpers."""

    def seed(self, connection_id: str, credentials: StoredCredential) -> None:
        """Seed a credential directly (test helper)."""
        self._store[connection_id] = credentials


__all__ = ["InMemoryCredentialStore", "InMemoryOAuthStateStore"]
