"""Unit tests for hosted connections router helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from omnidapter_hosted.dependencies import HostedAuthContext
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.routers.connections import _get_owned_connection_or_404, list_connections
from omnidapter_server.models.connection import Connection, ConnectionStatus


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

    def scalar_one(self) -> int:
        return cast(int, self._one)


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
    key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="key",
        key_hash="hash",
        key_prefix="omni_live_ab",
        is_active=True,
        is_test=False,
        created_at=_now(),
        last_used_at=None,
    )
    return HostedAuthContext(api_key=key, tenant=tenant)


@pytest.mark.asyncio
async def test_get_owned_connection_invalid_id_returns_404() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await _get_owned_connection_or_404(
            connection_id="invalid",
            tenant_id=uuid.uuid4(),
            session=AsyncMock(),
        )

    assert exc_info.value.status_code == 404
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "connection_not_found"


@pytest.mark.asyncio
async def test_get_owned_connection_missing_returns_404() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await _get_owned_connection_or_404(
            connection_id=str(uuid.uuid4()),
            tenant_id=uuid.uuid4(),
            session=session,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_owned_connection_success() -> None:
    conn = Connection(id=uuid.uuid4(), provider_key="google", status=ConnectionStatus.ACTIVE)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=conn))

    result = await _get_owned_connection_or_404(
        connection_id=str(conn.id),
        tenant_id=uuid.uuid4(),
        session=session,
    )

    assert result is conn


@pytest.mark.asyncio
async def test_list_connections_returns_pagination_shape() -> None:
    auth = _auth()
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        status=ConnectionStatus.ACTIVE,
        created_at=_now(),
        updated_at=_now(),
    )
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=1), _ScalarResult(many=[conn])])

    response = await list_connections(
        auth=auth,
        session=session,
        request_id="req_1",
        status=None,
        provider=None,
        limit=50,
        offset=0,
    )

    assert response["meta"]["request_id"] == "req_1"
    assert response["meta"]["pagination"]["total"] == 1
    assert response["data"][0].id == str(conn.id)
