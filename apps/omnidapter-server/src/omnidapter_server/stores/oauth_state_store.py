"""Database-backed OAuthStateStore for the Omnidapter library."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from omnidapter.stores.oauth_state import OAuthStateStore
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.oauth_state import OAuthState

_SESSION_FACTORY_BY_URL: dict[str, async_sessionmaker[AsyncSession]] = {}


def _get_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    factory = _SESSION_FACTORY_BY_URL.get(database_url)
    if factory is None:
        engine = create_async_engine(database_url, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        _SESSION_FACTORY_BY_URL[database_url] = factory
    return factory


def _parse_connection_uuid(payload: dict[str, Any]) -> uuid.UUID:
    connection_id = payload.get("connection_id")
    if not connection_id:
        raise ValueError("OAuth state payload missing connection_id")
    try:
        return uuid.UUID(str(connection_id))
    except (ValueError, AttributeError) as exc:
        raise ValueError("OAuth state payload contains invalid connection_id") from exc


def _build_state_row(
    state_id: str,
    payload: dict[str, Any],
    expires_at: datetime,
    encryption: EncryptionService,
) -> OAuthState:
    provider = payload.get("provider", "")
    redirect_uri = payload.get("redirect_uri", "")
    code_verifier = payload.get("code_verifier")

    pkce_encrypted: str | None = None
    if code_verifier:
        pkce_encrypted = encryption.encrypt(code_verifier)

    meta = {k: v for k, v in payload.items() if k != "code_verifier"}

    return OAuthState(
        id=uuid.uuid4(),
        provider_key=provider,
        connection_id=_parse_connection_uuid(payload),
        state_token=state_id,
        pkce_verifier_encrypted=pkce_encrypted,
        redirect_uri=redirect_uri,
        expires_at=expires_at,
        metadata_=meta,
    )


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_utc = expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_utc = expires_at.astimezone(timezone.utc)
    return expires_utc < datetime.now(timezone.utc)


def _hydrate_payload(row: OAuthState, encryption: EncryptionService) -> dict[str, Any]:
    payload: dict[str, Any] = dict(row.metadata_ or {})
    payload["connection_id"] = str(row.connection_id)
    payload["provider"] = row.provider_key
    payload["redirect_uri"] = row.redirect_uri or ""
    payload["expires_at"] = row.expires_at.isoformat()

    if row.pkce_verifier_encrypted:
        payload["code_verifier"] = encryption.decrypt(row.pkce_verifier_encrypted)
    else:
        payload["code_verifier"] = None

    return payload


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
        state_row = _build_state_row(state_id, payload, expires_at, self._encryption)
        self._session.add(state_row)
        await self._session.commit()

    async def load_state(self, state_id: str) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(OAuthState).where(OAuthState.state_token == state_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        if _is_expired(row.expires_at):
            await self._session.execute(
                delete(OAuthState).where(OAuthState.state_token == state_id)
            )
            await self._session.commit()
            return None

        return _hydrate_payload(row, self._encryption)

    async def delete_state(self, state_id: str) -> None:
        await self._session.execute(delete(OAuthState).where(OAuthState.state_token == state_id))
        await self._session.commit()


class DatabaseURLOAuthStateStore(OAuthStateStore):
    """Database-backed OAuthStateStore using a dedicated database URL."""

    def __init__(self, database_url: str, encryption: EncryptionService) -> None:
        self._session_factory = _get_session_factory(database_url)
        self._encryption = encryption

    async def save_state(
        self,
        state_id: str,
        payload: dict[str, Any],
        expires_at: datetime,
    ) -> None:
        state_row = _build_state_row(state_id, payload, expires_at, self._encryption)
        async with self._session_factory() as session:
            session.add(state_row)
            await session.commit()

    async def load_state(self, state_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(OAuthState).where(OAuthState.state_token == state_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None

            if _is_expired(row.expires_at):
                await session.execute(delete(OAuthState).where(OAuthState.state_token == state_id))
                await session.commit()
                return None

            return _hydrate_payload(row, self._encryption)

    async def delete_state(self, state_id: str) -> None:
        async with self._session_factory() as session:
            await session.execute(delete(OAuthState).where(OAuthState.state_token == state_id))
            await session.commit()
