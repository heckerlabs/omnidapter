"""Unit tests for database-backed OAuth state stores."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import omnidapter_server.stores.oauth_state_store as store_module
import pytest
from omnidapter_server.models.oauth_state import OAuthState
from omnidapter_server.stores.oauth_state_store import (
    DatabaseOAuthStateStore,
    DatabaseURLOAuthStateStore,
    _build_state_row,
    _hydrate_payload,
    _is_expired,
    _parse_connection_uuid,
)


class _SessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _SessionFactory:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    def __call__(self) -> _SessionContext:
        return _SessionContext(self._session)


def _row(*, expires_at: datetime, encrypted_pkce: str | None = "enc") -> OAuthState:
    return OAuthState(
        id=uuid.uuid4(),
        provider_key="google",
        connection_id=uuid.uuid4(),
        state_token="state_123",
        pkce_verifier_encrypted=encrypted_pkce,
        redirect_uri="https://app.example/cb",
        expires_at=expires_at,
        metadata_={"foo": "bar"},
    )


def test_parse_connection_uuid_valid() -> None:
    conn_id = str(uuid.uuid4())
    parsed = _parse_connection_uuid({"connection_id": conn_id})
    assert parsed == uuid.UUID(conn_id)


def test_parse_connection_uuid_missing_raises() -> None:
    with pytest.raises(ValueError, match="missing connection_id"):
        _parse_connection_uuid({})


def test_parse_connection_uuid_invalid_raises() -> None:
    with pytest.raises(ValueError, match="invalid connection_id"):
        _parse_connection_uuid({"connection_id": "not-a-uuid"})


def test_is_expired_handles_aware_and_naive() -> None:
    assert _is_expired(datetime.now(timezone.utc) - timedelta(seconds=1)) is True
    assert _is_expired(datetime.now(timezone.utc) + timedelta(minutes=5)) is False
    assert _is_expired(datetime.now() + timedelta(days=1)) is False


def test_build_state_row_encrypts_pkce_and_hydrates_payload() -> None:
    encryption = MagicMock()
    encryption.encrypt.return_value = "encrypted-verifier"
    encryption.decrypt.return_value = "plain-verifier"
    conn_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    state_row = _build_state_row(
        state_id="state_abc",
        payload={
            "connection_id": conn_id,
            "provider": "google",
            "redirect_uri": "https://app.example/cb",
            "code_verifier": "plain-verifier",
            "extra": "value",
        },
        expires_at=expires_at,
        encryption=encryption,
    )

    assert state_row.connection_id == uuid.UUID(conn_id)
    assert state_row.pkce_verifier_encrypted == "encrypted-verifier"

    hydrated = _hydrate_payload(state_row, encryption)
    assert hydrated["connection_id"] == conn_id
    assert hydrated["provider"] == "google"
    assert hydrated["code_verifier"] == "plain-verifier"


@pytest.mark.asyncio
async def test_database_store_save_state() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    encryption = MagicMock()
    encryption.encrypt.return_value = "encrypted"

    store = DatabaseOAuthStateStore(session=session, encryption=encryption)
    await store.save_state(
        state_id="state_1",
        payload={
            "connection_id": str(uuid.uuid4()),
            "provider": "google",
            "redirect_uri": "https://app.example/cb",
            "code_verifier": "plain",
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_store_save_state_invalid_connection_id_raises() -> None:
    store = DatabaseOAuthStateStore(session=AsyncMock(), encryption=MagicMock())

    with pytest.raises(ValueError, match="invalid connection_id"):
        await store.save_state(
            state_id="state_2",
            payload={"connection_id": "bad", "provider": "google"},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )


@pytest.mark.asyncio
async def test_database_store_load_state_missing() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    store = DatabaseOAuthStateStore(session=session, encryption=MagicMock())

    payload = await store.load_state("missing")

    assert payload is None


@pytest.mark.asyncio
async def test_database_store_load_state_expired_deletes() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = _row(
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    session.execute = AsyncMock(side_effect=[result, MagicMock()])
    session.commit = AsyncMock()
    store = DatabaseOAuthStateStore(session=session, encryption=MagicMock())

    payload = await store.load_state("expired")

    assert payload is None
    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_store_load_state_valid() -> None:
    encryption = MagicMock()
    encryption.decrypt.return_value = "plain"
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = _row(
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        encrypted_pkce="encrypted",
    )
    session.execute = AsyncMock(return_value=result)
    store = DatabaseOAuthStateStore(session=session, encryption=encryption)

    payload = await store.load_state("state_123")

    assert payload is not None
    assert payload["code_verifier"] == "plain"
    assert payload["foo"] == "bar"


@pytest.mark.asyncio
async def test_database_store_delete_state() -> None:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    store = DatabaseOAuthStateStore(session=session, encryption=MagicMock())

    await store.delete_state("state_3")

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_url_store_uses_factory_sessions() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    encryption = MagicMock()
    encryption.encrypt.return_value = "encrypted"

    with patch.object(store_module, "_get_session_factory", return_value=_SessionFactory(session)):
        store = DatabaseURLOAuthStateStore(
            database_url="postgresql+asyncpg://localhost/state_db",
            encryption=encryption,
        )

        await store.save_state(
            state_id="state_4",
            payload={
                "connection_id": str(uuid.uuid4()),
                "provider": "google",
                "redirect_uri": "https://app.example/cb",
            },
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        loaded = await store.load_state("missing")
        await store.delete_state("state_4")

    assert loaded is None
    session.add.assert_called_once()
    assert session.commit.await_count >= 2
