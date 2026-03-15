"""Database-backed OAuthStateStore for the Omnidapter library.

Stores OAuth state in the oauth_states table with encryption for PKCE verifiers.
The state_id is the state_token column.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from omnidapter.stores.oauth_state import OAuthStateStore
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_api.encryption import EncryptionService
from omnidapter_api.models.connection import Connection
from omnidapter_api.models.oauth_state import OAuthState


class DatabaseOAuthStateStore(OAuthStateStore):
    """Persists OAuth state to Postgres with PKCE verifier encryption."""

    def __init__(self, session: AsyncSession, encryption: EncryptionService) -> None:
        self._session = session
        self._encryption = encryption

    async def save_state(
        self,
        state_id: str,
        payload: dict[str, Any],
        expires_at: datetime,
    ) -> None:
        # Extract known fields from payload
        connection_id = payload.get("connection_id")
        provider = payload.get("provider", "")
        redirect_uri = payload.get("redirect_uri", "")
        code_verifier = payload.get("code_verifier")

        if not connection_id:
            raise ValueError("OAuth state payload is missing connection_id")

        try:
            conn_uuid = uuid.UUID(str(connection_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("OAuth state payload has invalid connection_id") from exc

        conn_result = await self._session.execute(
            select(Connection).where(Connection.id == conn_uuid)
        )
        conn = conn_result.scalar_one_or_none()
        if conn is None:
            raise ValueError(f"Connection {connection_id!r} not found for OAuth state")

        if provider and provider != conn.provider_key:
            raise ValueError("OAuth state provider does not match the connection provider")

        provider_key = provider or conn.provider_key
        if not provider_key:
            raise ValueError("OAuth state payload is missing provider")

        # Encrypt PKCE verifier if present
        pkce_encrypted: str | None = None
        if code_verifier:
            pkce_encrypted = self._encryption.encrypt(code_verifier)

        # Store the full payload as metadata (minus sensitive fields)
        meta = {k: v for k, v in payload.items() if k != "code_verifier"}

        state_row = OAuthState(
            id=uuid.uuid4(),
            organization_id=conn.organization_id,
            provider_key=provider_key,
            connection_id=conn_uuid,
            state_token=state_id,
            pkce_verifier_encrypted=pkce_encrypted,
            redirect_uri=redirect_uri,
            expires_at=expires_at,
            metadata_=meta,
        )
        self._session.add(state_row)
        await self._session.commit()

    async def load_state(self, state_id: str) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(OAuthState).where(OAuthState.state_token == state_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        # Check expiry
        if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            await self._session.execute(
                delete(OAuthState).where(OAuthState.state_token == state_id)
            )
            await self._session.commit()
            return None

        # Reconstruct payload
        payload: dict[str, Any] = dict(row.metadata_ or {})
        payload["connection_id"] = str(row.connection_id)
        payload["provider"] = row.provider_key
        payload["redirect_uri"] = row.redirect_uri or ""
        payload["expires_at"] = row.expires_at.isoformat()

        if row.pkce_verifier_encrypted:
            payload["code_verifier"] = self._encryption.decrypt(row.pkce_verifier_encrypted)
        else:
            payload["code_verifier"] = None

        return payload

    async def delete_state(self, state_id: str) -> None:
        await self._session.execute(delete(OAuthState).where(OAuthState.state_token == state_id))
        await self._session.commit()
