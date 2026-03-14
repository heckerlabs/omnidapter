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
        connection_id = payload.get("connection_id", "")
        provider = payload.get("provider", "")
        redirect_uri = payload.get("redirect_uri", "")
        code_verifier = payload.get("code_verifier")
        org_id = payload.get("organization_id", "")

        # Encrypt PKCE verifier if present
        pkce_encrypted: str | None = None
        if code_verifier:
            pkce_encrypted = self._encryption.encrypt(code_verifier)

        # Store the full payload as metadata (minus sensitive fields)
        meta = {k: v for k, v in payload.items() if k != "code_verifier"}

        # org_id may or may not be in payload — default to a zero UUID for now
        try:
            org_uuid = uuid.UUID(str(org_id)) if org_id else uuid.UUID(int=0)
        except (ValueError, AttributeError):
            org_uuid = uuid.UUID(int=0)

        try:
            conn_uuid = uuid.UUID(str(connection_id)) if connection_id else uuid.UUID(int=0)
        except (ValueError, AttributeError):
            conn_uuid = uuid.UUID(int=0)

        state_row = OAuthState(
            id=uuid.uuid4(),
            organization_id=org_uuid,
            provider_key=provider,
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
