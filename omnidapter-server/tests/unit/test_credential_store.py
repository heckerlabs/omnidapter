"""Unit tests for database credential store."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import ConnectionNotFoundError
from omnidapter.core.metadata import AuthKind
from omnidapter.stores.credentials import StoredCredential
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.stores.credential_store import DatabaseCredentialStore


def _credential() -> StoredCredential:
    return StoredCredential(
        provider_key="google",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token="token", refresh_token="refresh"),
        granted_scopes=["scope-a"],
        provider_account_id="acct-1",
    )


def _connection(*, credentials_encrypted: str | None) -> Connection:
    return Connection(
        id=uuid.uuid4(),
        provider_key="google",
        status=ConnectionStatus.ACTIVE,
        credentials_encrypted=credentials_encrypted,
    )


@pytest.mark.asyncio
async def test_get_credentials_returns_none_when_connection_missing() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    store = DatabaseCredentialStore(session=session, encryption=MagicMock())

    assert await store.get_credentials(str(uuid.uuid4())) is None


@pytest.mark.asyncio
async def test_get_credentials_returns_none_for_invalid_uuid() -> None:
    session = AsyncMock()
    store = DatabaseCredentialStore(session=session, encryption=MagicMock())

    assert await store.get_credentials("invalid-uuid") is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_credentials_returns_none_when_no_encrypted_payload() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = _connection(credentials_encrypted=None)
    session.execute = AsyncMock(return_value=result)
    store = DatabaseCredentialStore(session=session, encryption=MagicMock())

    assert await store.get_credentials(str(uuid.uuid4())) is None


@pytest.mark.asyncio
async def test_get_credentials_decrypts_and_parses() -> None:
    expected = _credential()
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = _connection(credentials_encrypted="encrypted")
    session.execute = AsyncMock(return_value=result)
    encryption = MagicMock()
    encryption.decrypt.return_value = json.dumps(expected.model_dump(mode="json"))
    store = DatabaseCredentialStore(session=session, encryption=encryption)

    actual = await store.get_credentials(str(uuid.uuid4()))

    assert actual is not None
    assert actual.provider_key == "google"
    assert isinstance(actual.credentials, OAuth2Credentials)
    assert actual.credentials.access_token == "token"


@pytest.mark.asyncio
async def test_save_credentials_persists_and_commits() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid.uuid4()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    encryption = MagicMock()
    encryption.encrypt.return_value = "encrypted"
    store = DatabaseCredentialStore(session=session, encryption=encryption)

    await store.save_credentials(str(uuid.uuid4()), _credential())

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
    statement_str = str(session.execute.await_args.args[0])
    assert "granted_scopes" in statement_str
    assert "provider_account_id" in statement_str


@pytest.mark.asyncio
async def test_save_credentials_raises_when_connection_missing() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    encryption = MagicMock()
    encryption.encrypt.return_value = "encrypted"
    store = DatabaseCredentialStore(session=session, encryption=encryption)

    with pytest.raises(ConnectionNotFoundError):
        await store.save_credentials(str(uuid.uuid4()), _credential())

    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_save_credentials_raises_for_invalid_uuid() -> None:
    session = AsyncMock()
    encryption = MagicMock()
    store = DatabaseCredentialStore(session=session, encryption=encryption)

    with pytest.raises(ConnectionNotFoundError):
        await store.save_credentials("invalid-uuid", _credential())

    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_delete_credentials_clears_payload() -> None:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    store = DatabaseCredentialStore(session=session, encryption=MagicMock())

    await store.delete_credentials(str(uuid.uuid4()))

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
    statement_str = str(session.execute.await_args.args[0])
    assert "credentials_encrypted" in statement_str
