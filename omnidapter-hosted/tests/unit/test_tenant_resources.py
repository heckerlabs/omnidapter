"""Unit tests for hosted tenant resource helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.services.tenant_resources import (
    get_tenant_connection,
    get_tenant_provider_config,
    list_tenant_connections,
)
from omnidapter_server.models.connection import Connection, ConnectionStatus


class _ScalarResult:
    def __init__(self, one: object | None = None, many: list[object] | None = None) -> None:
        self._one = one
        self._many = many or []

    def scalar_one_or_none(self) -> object | None:
        return self._one

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[object]:
        return self._many


@pytest.mark.asyncio
async def test_get_tenant_connection_returns_none_when_owner_missing() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    result = await get_tenant_connection(
        session=session,
        tenant_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_tenant_connection_returns_none_when_connection_missing() -> None:
    owner = HostedConnectionOwner(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
    )
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=owner), _ScalarResult(one=None)])

    result = await get_tenant_connection(
        session=session,
        tenant_id=owner.tenant_id,
        connection_id=owner.connection_id,
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_tenant_connection_returns_both_records() -> None:
    conn = Connection(id=uuid.uuid4(), provider_key="google", status=ConnectionStatus.ACTIVE)
    owner = HostedConnectionOwner(id=uuid.uuid4(), tenant_id=uuid.uuid4(), connection_id=conn.id)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=owner), _ScalarResult(one=conn)])

    result = await get_tenant_connection(
        session=session,
        tenant_id=owner.tenant_id,
        connection_id=conn.id,
    )

    assert result is not None
    assert result.owner is owner
    assert result.connection is conn


@pytest.mark.asyncio
async def test_list_tenant_connections_returns_joined_results() -> None:
    conn = Connection(id=uuid.uuid4(), provider_key="google", status=ConnectionStatus.ACTIVE)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(many=[conn]))

    connections = await list_tenant_connections(session=session, tenant_id=uuid.uuid4())

    assert connections == [conn]


@pytest.mark.asyncio
async def test_get_tenant_provider_config_scoped_lookup() -> None:
    cfg = HostedProviderConfig(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        provider_key="google",
        auth_kind="oauth2",
        client_id_encrypted="enc-id",
        client_secret_encrypted="enc-secret",
        scopes=["a"],
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=cfg))

    result = await get_tenant_provider_config(
        session=session,
        tenant_id=cfg.tenant_id,
        provider_key="google",
    )

    assert result is cfg
