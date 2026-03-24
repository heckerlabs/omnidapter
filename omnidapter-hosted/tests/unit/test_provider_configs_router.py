"""Unit tests for hosted provider config routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from omnidapter_hosted.dependencies import HostedAuthContext
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.routers.provider_configs import (
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _auth() -> HostedAuthContext:
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Acme",
        plan="free",
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="key",
        key_hash="hash",
        key_prefix="omni_key_abcd",
        is_active=True,
        created_at=_now(),
        last_used_at=None,
    )
    return HostedAuthContext(api_key=api_key, tenant=tenant)


def _cfg(tenant_id: uuid.UUID) -> HostedProviderConfig:
    return HostedProviderConfig(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider_key="google",
        auth_kind="oauth2",
        client_id_encrypted="enc-id",
        client_secret_encrypted="enc-secret",
        scopes=["a"],
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.mark.asyncio
async def test_list_provider_configs_returns_tenant_rows() -> None:
    auth = _auth()
    cfg = _cfg(auth.tenant_id)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(many=[cfg]))

    response = await list_provider_configs(auth=auth, session=session, request_id="req_1")

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
async def test_upsert_provider_config_create() -> None:
    auth = _auth()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _refresh(obj: object) -> None:
        obj.created_at = _now()  # type: ignore[attr-defined]
        obj.updated_at = _now()  # type: ignore[attr-defined]

    session.refresh = AsyncMock(side_effect=_refresh)
    encryption = MagicMock()
    encryption.encrypt.side_effect = ["enc-id", "enc-secret"]

    response = await upsert_provider_config(
        provider_key="google",
        body=UpsertProviderConfigRequest(client_id="id", client_secret="secret", scopes=["a"]),
        auth=auth,
        encryption=encryption,
        session=session,
        request_id="req_3",
    )

    assert response["meta"]["request_id"] == "req_3"
    assert response["data"].provider_key == "google"
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_provider_config_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await delete_provider_config(
            provider_key="google",
            auth=_auth(),
            session=session,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_provider_config_success() -> None:
    auth = _auth()
    cfg = _cfg(auth.tenant_id)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=cfg), MagicMock()])
    session.commit = AsyncMock()

    await delete_provider_config(provider_key="google", auth=auth, session=session)

    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()
