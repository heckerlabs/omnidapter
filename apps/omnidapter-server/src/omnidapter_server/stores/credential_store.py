"""Database-backed CredentialStore for the Omnidapter library.

Credentials are encrypted at rest using AES-256-GCM.
The connection_id maps to a Connection.id in the database.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from omnidapter.stores.credentials import CredentialStore, StoredCredential
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection


class DatabaseCredentialStore(CredentialStore):
    """Persists credentials to Postgres with encryption at rest."""

    def __init__(self, session: AsyncSession, encryption: EncryptionService) -> None:
        self._session = session
        self._encryption = encryption

    async def get_credentials(self, connection_id: str) -> StoredCredential | None:
        conn_uuid = uuid.UUID(connection_id)
        result = await self._session.execute(select(Connection).where(Connection.id == conn_uuid))
        conn = result.scalar_one_or_none()
        if conn is None or conn.credentials_encrypted is None:
            return None

        raw = self._encryption.decrypt(conn.credentials_encrypted)
        data: dict[str, Any] = json.loads(raw)
        return StoredCredential.model_validate(data)

    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None:
        conn_uuid = uuid.UUID(connection_id)
        raw = json.dumps(credentials.model_dump(mode="json"))
        encrypted = self._encryption.encrypt(raw)

        # Extract metadata from credentials for top-level fields
        granted_scopes = credentials.granted_scopes
        provider_account_id = credentials.provider_account_id

        values: dict = {
            "credentials_encrypted": encrypted,
            "updated_at": datetime.now(timezone.utc),
        }
        if granted_scopes is not None:
            values["granted_scopes"] = granted_scopes
        if provider_account_id is not None:
            values["provider_account_id"] = provider_account_id

        await self._session.execute(
            update(Connection).where(Connection.id == conn_uuid).values(**values)
        )
        await self._session.commit()

    async def delete_credentials(self, connection_id: str) -> None:
        conn_uuid = uuid.UUID(connection_id)
        await self._session.execute(
            update(Connection).where(Connection.id == conn_uuid).values(credentials_encrypted=None)
        )
        await self._session.commit()
