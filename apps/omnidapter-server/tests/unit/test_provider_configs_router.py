"""Unit tests for provider config router handlers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from omnidapter_server.dependencies import AuthContext
from omnidapter_server.models.provider_config import ProviderConfig
from omnidapter_server.routers.provider_configs import (
    delete_provider_config,
    get_provider_config,
    list_provider_configs,
    upsert_provider_config,
)
from omnidapter_server.schemas.provider_config import UpsertProviderConfigRequest


class _ScalarResult:
    def __init__(self, *, one: object | None = None, many: list[object] | None = None) -> None:
        self._one = one
        self._many = many or []

    def scalar_one_or_none(self) -> object | None:
        return self._one

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[object]:
        return self._many


def _auth() -> AuthContext:
    return AuthContext(api_key=MagicMock())


def _cfg(provider_key: str = "google") -> ProviderConfig:
    now = datetime.now(timezone.utc)
    return ProviderConfig(
        id=uuid.uuid4(),
        provider_key=provider_key,
        auth_kind="oauth2",
        client_id_encrypted="enc-id",
        client_secret_encrypted="enc-secret",
        scopes=["calendar"],
        is_fallback=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_list_provider_configs() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(many=[_cfg()]))

    response = await list_provider_configs(auth=_auth(), session=session, request_id="req_1")

    assert response["meta"]["request_id"] == "req_1"
    assert response["data"][0].provider_key == "google"


@pytest.mark.asyncio
async def test_get_provider_config_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await get_provider_config(
            provider_key="google",
            auth=_auth(),
            session=session,
            request_id="req_2",
        )

    assert exc_info.value.status_code == 404
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "provider_config_not_found"


@pytest.mark.asyncio
async def test_get_provider_config_success() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=_cfg()))

    response = await get_provider_config(
        provider_key="google",
        auth=_auth(),
        session=session,
        request_id="req_3",
    )

    assert response["meta"]["request_id"] == "req_3"
    assert response["data"].provider_key == "google"


@pytest.mark.asyncio
async def test_upsert_provider_config_requires_encryption_key() -> None:
    encryption = MagicMock()
    encryption._current_key = ""

    with pytest.raises(HTTPException) as exc_info:
        await upsert_provider_config(
            provider_key="google",
            body=UpsertProviderConfigRequest(client_id="id", client_secret="secret"),
            auth=_auth(),
            encryption=encryption,
            session=AsyncMock(),
            request_id="req_4",
        )

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_upsert_provider_config_create_path() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))
    session.commit = AsyncMock()

    async def _refresh(cfg: ProviderConfig) -> None:
        now = datetime.now(timezone.utc)
        cfg.created_at = now
        cfg.updated_at = now

    session.refresh = AsyncMock(side_effect=_refresh)

    encryption = MagicMock()
    encryption._current_key = "configured"
    encryption.encrypt.side_effect = ["enc-id", "enc-secret"]

    response = await upsert_provider_config(
        provider_key="google",
        body=UpsertProviderConfigRequest(client_id="id", client_secret="secret", scopes=["a"]),
        auth=_auth(),
        encryption=encryption,
        session=session,
        request_id="req_5",
    )

    assert response["meta"]["request_id"] == "req_5"
    assert response["data"].provider_key == "google"
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_provider_config_update_path() -> None:
    existing = _cfg("microsoft")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=existing))
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    encryption = MagicMock()
    encryption._current_key = "configured"
    encryption.encrypt.side_effect = ["new-id", "new-secret"]

    response = await upsert_provider_config(
        provider_key="microsoft",
        body=UpsertProviderConfigRequest(client_id="id", client_secret="secret", scopes=None),
        auth=_auth(),
        encryption=encryption,
        session=session,
        request_id="req_6",
    )

    assert response["data"].provider_key == "microsoft"
    assert existing.client_id_encrypted == "new-id"
    assert existing.client_secret_encrypted == "new-secret"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_provider_config_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await delete_provider_config("google", auth=_auth(), session=session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_provider_config_success() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=_cfg()), MagicMock()])
    session.commit = AsyncMock()

    await delete_provider_config("google", auth=_auth(), session=session)

    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()
